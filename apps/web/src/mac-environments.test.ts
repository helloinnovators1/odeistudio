import { describe, expect, it, vi } from "vitest";
import {
  createMacEnvironmentDraft, getMacEnvironment, promoteMacEnvironment,
  submitMacEnvironment, updateMacEnvironmentDraft,
} from "./mac-environments";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

describe("MAC environment transport", () => {
  it("uses bearer authentication without ambient credentials", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({
      environment: { environment: "staging", active_version: 0, latest_version: 1, versions: [] },
    }));
    await getMacEnvironment("https://api.example.test/", "staging", "ephemeral-token", fetcher);
    const [url, init] = fetcher.mock.calls[0]!;
    expect(url).toBe("https://api.example.test/api/v1/mac/environments/staging");
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    expect(init?.redirect).toBe("error");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
  });

  it("creates a first draft and appends a revision with an optimistic version", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ revision: { version: 1, status: "draft" } }, 201))
      .mockResolvedValueOnce(response({ revision: { version: 2, status: "draft" } }, 201));
    await createMacEnvironmentDraft("https://api.example.test", "staging", "token",
      { replicas: 2 }, "Initial", undefined, fetcher);
    await createMacEnvironmentDraft("https://api.example.test", "staging", "token",
      { replicas: 3 }, "Scale", 1, fetcher);
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({
      config: { replicas: 3 }, change_summary: "Scale", expected_latest_version: 1,
    });
  });

  it("uses revision compare-and-set bodies for submission and promotion", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ environment: {} }))
      .mockResolvedValueOnce(response({ environment: {} }));
    await submitMacEnvironment("https://api.example.test", "production", "token", 4, 4, fetcher);
    await promoteMacEnvironment("https://api.example.test", "production", "token", 4, 4, 2, fetcher);
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({
      version: 4, expected_latest_version: 4,
    });
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({
      version: 4, expected_latest_version: 4, expected_active_version: 2,
    });
  });

  it("uses PUT for draft edits and rejects invalid version inputs", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ environment: {} }));
    await updateMacEnvironmentDraft("https://api.example.test", "staging", "token",
      2, 2, { replicas: 3 }, "Update", fetcher);
    expect(fetcher.mock.calls[0]?.[1]?.method).toBe("PUT");
    await expect(submitMacEnvironment("https://api.example.test", "staging", "token", 0, 1, fetcher))
      .rejects.toThrow("valid revision");
  });

  it("blocks insecure non-loopback origins and invalid environments before sending tokens", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(getMacEnvironment("http://api.example.test", "staging", "token", fetcher))
      .rejects.toThrow("must use HTTPS");
    await expect(getMacEnvironment("https://api.example.test", "unknown", "token", fetcher))
      .rejects.toThrow("Invalid MAC environment");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("maps API authorization failures and bounds response sizes", async () => {
    const denied = vi.fn<typeof fetch>().mockResolvedValue(response({
      detail: { message: "The verified operator lacks MAC permission." },
    }, 403));
    await expect(getMacEnvironment("https://api.example.test", "staging", "token", denied))
      .rejects.toThrow("The verified operator lacks MAC permission.");
    const oversized = vi.fn<typeof fetch>().mockResolvedValue(new Response("x".repeat(256_001)));
    await expect(getMacEnvironment("https://api.example.test", "staging", "token", oversized))
      .rejects.toThrow("oversized response");
  });
});
