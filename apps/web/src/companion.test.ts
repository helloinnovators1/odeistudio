import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyApprovedWorkspacePatch,
  createWorkspaceApplyChallenge,
  previewWorkspacePatch,
} from "./companion";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("previewWorkspacePatch", () => {
  it("sends SHA-256 base hashes and validates a preview-only response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      workspace_id: "workspace-1",
      mode: "preview_only",
      writes_performed: false,
      files: [{
        path: "main.py",
        operation: "update",
        base_sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        result_sha256: "0".repeat(64),
        content: "next",
        unified_diff: "-abc\\n+next\\n",
      }],
      total_content_bytes: 4,
      total_diff_bytes: 10,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await previewWorkspacePatch(
      "session-token",
      "workspace-1",
      { "main.py": "next" },
      { "main.py": "abc" },
    );

    expect(result.mode).toBe("preview_only");
    expect(result.writes_performed).toBe(false);
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(request.url).toContain("/v1/workspaces/workspace-1/patch-proposals");
    expect(request.headers.get("Authorization")).toBe("Bearer session-token");
    expect(await request.json()).toEqual({
      changes: { "main.py": "next" },
      expected_base_hashes: {
        "main.py": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      },
    });
  });

  it("uses a null base hash for a new file", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      workspace_id: "workspace-1",
      mode: "preview_only",
      writes_performed: false,
      files: [{
        path: "new.py",
        operation: "create",
        base_sha256: null,
        result_sha256: "0".repeat(64),
        content: "new",
        unified_diff: "+new\\n",
      }],
      total_content_bytes: 3,
      total_diff_bytes: 4,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await previewWorkspacePatch(
      "session-token", "workspace-1", { "new.py": "new" }, { "new.py": null },
    );

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(await request.json()).toEqual({
      changes: { "new.py": "new" },
      expected_base_hashes: { "new.py": null },
    });
  });

  it("rejects a missing base snapshot before making a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(previewWorkspacePatch(
      "session-token", "workspace-1", { "main.py": "next" }, {},
    )).rejects.toThrow("matching base content");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a response that claims writes were performed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      workspace_id: "workspace-1",
      mode: "preview_only",
      writes_performed: true,
      files: [],
      total_content_bytes: 0,
      total_diff_bytes: 0,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(previewWorkspacePatch(
      "session-token", "workspace-1", { "main.py": "next" }, { "main.py": "abc" },
    )).rejects.toThrow("invalid patch preview response");
  });
});


describe("signed companion patch application", () => {
  it("requests a fresh challenge using the paired local session", async () => {
    const challenge = "C".repeat(43);
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      workspace_id: "workspace-1", challenge, expires_in: 60,
    }), { status: 200 }));
    const result = await createWorkspaceApplyChallenge(
      "local-session", "workspace-1", fetchMock,
    );
    expect(result.challenge).toBe(challenge);
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(request.url).toContain("/v1/workspaces/workspace-1/apply-challenge");
    expect(request.headers.get("Authorization")).toBe("Bearer local-session");
  });

  it("sends only the signed single-file approval to the selected workspace", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      workspace_id: "workspace-1",
      proposal_id: "proposal-1",
      proposal_version: 2,
      applied: true,
      files: [{
        path: "main.py", operation: "update",
        result_sha256: "b".repeat(64), applied: true, durability_confirmed: true,
      }],
    }), { status: 200 }));
    const file = {
      path: "main.py", operation: "update" as const,
      base_sha256: "a".repeat(64), result_sha256: "b".repeat(64),
      content: "print('new')", unified_diff: "-old\\n+new\\n",
    };
    const result = await applyApprovedWorkspacePatch(
      "local-session", "workspace-1", {
        organizationId: "org-1", projectId: "project-1",
        proposalId: "proposal-1", proposalVersion: 2,
        challenge: "C".repeat(43), capability: "signed-capability", file,
      },
      fetchMock,
    );
    expect(result.applied).toBe(true);
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toContain("/v1/workspaces/workspace-1/apply-patch");
    expect(request.headers.get("Authorization")).toBe("Bearer local-session");
    expect(await request.json()).toMatchObject({
      organization_id: "org-1",
      project_id: "project-1",
      proposal_id: "proposal-1",
      proposal_version: 2,
      capability: "signed-capability",
      files: [{ path: "main.py", operation: "update" }],
    });
  });

  it("rejects a response for a different proposal or workspace", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      workspace_id: "other-workspace",
      proposal_id: "proposal-1",
      proposal_version: 2,
      applied: true,
      files: [{
        path: "main.py", operation: "update",
        result_sha256: "b".repeat(64), applied: true,
      }],
    }), { status: 200 }));
    const file = {
      path: "main.py", operation: "update" as const,
      base_sha256: "a".repeat(64), result_sha256: "b".repeat(64),
      content: "new", unified_diff: "",
    };
    await expect(applyApprovedWorkspacePatch(
      "local-session", "workspace-1", {
        organizationId: "org-1", projectId: "project-1",
        proposalId: "proposal-1", proposalVersion: 2,
        challenge: "C".repeat(43), capability: "signed-capability", file,
      },
      fetchMock,
    )).rejects.toThrow("invalid patch application result");
  });
});
