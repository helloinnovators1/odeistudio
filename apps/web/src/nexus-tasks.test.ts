import { describe, expect, it, vi } from "vitest";

import {
  approveNexusTask,
  cancelNexusTask,
  createNexusTask,
  getNexusTask,
} from "./nexus-tasks";

const base = {
  apiBaseUrl: "https://api.example.test",
  organizationId: "org-a",
  projectId: "project-a",
  accessToken: "ephemeral-token",
};

function task(status = "awaiting_approval") {
  return {
    task_id: "task-one",
    organization_id: "org-a",
    project_id: "project-a",
    owner_id: "identity-owner-key",
    goal: "Add robust tests",
    status,
    plan: "1. Inspect the affected module\n2. Propose focused tests",
    version: status === "approved" ? 2 : 1,
    created_at: "2026-11-21T00:00:00Z",
    updated_at: "2026-11-21T00:00:00Z",
  };
}

describe("NEXUS task transport", () => {
  it("creates an approval-ready task with explicit cloud consent", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(task()), { status: 200 }));
    const result = await createNexusTask(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      "Add robust tests", "Selected file excerpt", undefined, fetcher,
    );
    expect(result.status).toBe("awaiting_approval");
    const [url, init] = fetcher.mock.calls[0];
    expect(String(url)).toBe("https://api.example.test/api/v1/organizations/org-a/projects/project-a/tasks");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      task: "Add robust tests",
      project_context: "Selected file excerpt",
      cloud_model_consent: true,
    });
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
  });

  it("loads and approves tasks using optimistic versions", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(task()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(task("approved")), { status: 200 }));
    const loaded = await getNexusTask(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken, "task-one", fetcher,
    );
    const approved = await approveNexusTask(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      loaded.task_id, loaded.version, fetcher,
    );
    expect(approved.status).toBe("approved");
    expect(fetcher.mock.calls[1][1]?.method).toBe("POST");
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({ expected_version: 1 });
  });

  it("cancels tasks and maps owner-only approval failures safely", async () => {
    const cancelFetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(task("cancelled")), { status: 200 }));
    const cancelled = await cancelNexusTask(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      "task-one", 1, cancelFetcher,
    );
    expect(cancelled.status).toBe("cancelled");
    const forbidden = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: "PROJECT_OWNER_APPROVAL_REQUIRED", message: "internal details" },
    }), { status: 403 }));
    await expect(approveNexusTask(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      "task-one", 1, forbidden,
    )).rejects.toThrow("Only the project owner can approve this plan.");
  });
});
