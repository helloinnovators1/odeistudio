import { describe, expect, it, vi } from "vitest";

import { generateNexusPatchDraft } from "./nexus-patches";

const base = {
  apiBaseUrl: "https://api.example.test",
  organizationId: "org-a",
  projectId: "project-a",
  accessToken: "ephemeral-token",
  task: "Change the greeting",
  path: "src/greeting.py",
  content: "def greet(name):\\n    return f\"Hello {name}\"\\n",
};

function draft() {
  return {
    path: base.path,
    mode: "preview_only",
    writes_performed: false,
    base_sha256: "a".repeat(64),
    result_sha256: "b".repeat(64),
    replacement_content: "def greet(name):\\n    return f\"Welcome {name}\"\\n",
    unified_diff: "@@ -1 +1 @@\\n-Hello\\n+Welcome",
    model: "test-model",
  };
}

describe("NEXUS patch draft transport", () => {
  it("sends a consented single-file request without cookies and validates preview-only output", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(draft()), { status: 200 }));
    const result = await generateNexusPatchDraft(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      base.task, base.path, base.content, undefined, fetcher,
    );
    expect(result.mode).toBe("preview_only");
    expect(result.writes_performed).toBe(false);
    const [url, init] = fetcher.mock.calls[0];
    expect(String(url)).toContain("/nexus/patch-drafts");
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      task: base.task, path: base.path, cloud_model_consent: true,
    });
  });

  it("rejects unsafe paths and malformed or write-enabled server responses", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      ...draft(), writes_performed: true,
    }), { status: 200 }));
    await expect(generateNexusPatchDraft(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      base.task, "../.env", base.content, undefined, fetcher,
    )).rejects.toThrow("safe relative file path");
    await expect(generateNexusPatchDraft(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      base.task, base.path, base.content, undefined, fetcher,
    )).rejects.toThrow("invalid patch draft contract");
  });

  it("maps protected-path failures to a safe user-facing error", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: "PATCH_PATH_REJECTED", message: "private server details" },
    }), { status: 422 }));
    await expect(generateNexusPatchDraft(
      base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken,
      base.task, base.path, base.content, undefined, fetcher,
    )).rejects.toThrow("protected and cannot be proposed");
  });
});
