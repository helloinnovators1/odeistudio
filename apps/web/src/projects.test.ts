import { describe, expect, it, vi } from "vitest";
import {
  createNexusProject,
  listNexusProjects,
  NexusProjectTransportError,
} from "./projects";

const project = {
  project_id: "project-a",
  organization_id: "org-a",
  name: "Studio",
  description: "Main workspace",
  status: "active",
  owner: { issuer: "https://identity.example.test", subject: "user-a" },
  created_at: "2026-11-21T00:00:00+00:00",
  updated_at: "2026-11-21T00:00:00+00:00",
};

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("NEXUS project transport", () => {
  it("lists server-authorized projects with an in-memory bearer and no ambient credentials", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ projects: [project], limit: 100 }));
    const result = await listNexusProjects("https://api.example.test/", "org-a", "ephemeral-token", fetcher);
    expect(result.projects[0]).toMatchObject({ project_id: "project-a", name: "Studio" });
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("https://api.example.test/api/v1/organizations/org-a/projects");
    expect(init?.method).toBe("GET");
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    expect(init?.redirect).toBe("error");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
  });

  it("rejects cross-organization and malformed project responses", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({
      projects: [{ ...project, organization_id: "org-other" }], limit: 100,
    }));
    await expect(listNexusProjects("https://api.example.test", "org-a", "token", fetcher))
      .rejects.toThrow("unexpected project-list contract");
  });

  it("rejects duplicate project IDs and more than the server's maximum", async () => {
    const duplicate = vi.fn<typeof fetch>().mockResolvedValue(response({
      projects: [project, project], limit: 100,
    }));
    await expect(listNexusProjects("https://api.example.test", "org-a", "token", duplicate))
      .rejects.toThrow("duplicate project identities");
    const excessive = vi.fn<typeof fetch>().mockResolvedValue(response({
      projects: Array.from({ length: 101 }, (_, i) => ({ ...project, project_id: `p-${i}` })),
      limit: 100,
    }));
    await expect(listNexusProjects("https://api.example.test", "org-a", "token", excessive))
      .rejects.toThrow("unexpected project-list contract");
  });

  it("creates a project with bounded input and validates the returned organization", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(project, 201));
    const result = await createNexusProject(
      "https://api.example.test", "org-a", "token",
      { name: "  Studio  ", description: " Main workspace " }, fetcher,
    );
    expect(result.project_id).toBe("project-a");
    const [, init] = fetcher.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Studio", description: "Main workspace" });
  });

  it("rejects invalid inputs before network access", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(listNexusProjects("http://api.example.test", "org-a", "token", fetcher))
      .rejects.toThrow("must use HTTPS");
    await expect(listNexusProjects("https://api.example.test", " ", "token", fetcher))
      .rejects.toThrow("Organization ID");
    await expect(createNexusProject("https://api.example.test", "org-a", "token",
      { name: " ".repeat(2) }, fetcher)).rejects.toThrow("Project name");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("maps server errors to safe messages without reflecting response details", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({
      detail: { code: "ORGANIZATION_ACCESS_DENIED", message: "private internal details" },
    }, 403));
    await expect(listNexusProjects("https://api.example.test", "org-a", "token", fetcher))
      .rejects.toMatchObject({
        name: "NexusProjectTransportError",
        status: 403,
        code: "ORGANIZATION_ACCESS_DENIED",
        message: "You do not have active access to this organization.",
      } satisfies Partial<NexusProjectTransportError>);
  });

  it("rejects oversized and non-JSON responses", async () => {
    const oversized = vi.fn<typeof fetch>().mockResolvedValue(new Response("x".repeat(128_001), { status: 200 }));
    await expect(listNexusProjects("https://api.example.test", "org-a", "token", oversized))
      .rejects.toThrow("oversized project response");
    const invalid = vi.fn<typeof fetch>().mockResolvedValue(new Response("<html>oops</html>", { status: 502 }));
    await expect(listNexusProjects("https://api.example.test", "org-a", "token", invalid))
      .rejects.toThrow("invalid project response");
  });
});
