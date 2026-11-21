import { describe, expect, it, vi } from "vitest";
import {
  approveNexusPatchProposal,
  createNexusPatchApplyCapability,
  getNexusPatchProposal,
  listNexusPatchProposals,
  rejectNexusPatchProposal,
} from "./nexus-patch-proposals";

const base = {
  api: "https://api.example.test",
  org: "org-1",
  project: "project-1",
  token: "ephemeral-token",
};
const summary = {
  proposal_id: "proposal-1", title: "Fix active file", status: "pending",
  version: 0, file_count: 1, created_at: "2026-11-21T00:00:00Z",
  updated_at: "2026-11-21T00:00:00Z",
};
const detail = {
  ...summary,
  can_decide: true,
  application_enabled: false,
  files: [{
    path: "src/main.py", operation: "update",
    base_sha256: "a".repeat(64), result_sha256: "b".repeat(64),
    content: "print('updated')", unified_diff: "@@ -1 +1 @@",
  }],
};

describe("NEXUS patch proposal browser client", () => {
  it("lists and loads tenant-scoped proposals using bearer-only no-store requests", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        proposals: [summary], limit: 30, can_decide: true,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(detail), { status: 200 }));
    const listed = await listNexusPatchProposals(base.api, base.org, base.project, base.token, fetcher);
    const loaded = await getNexusPatchProposal(base.api, base.org, base.project, base.token, "proposal-1", fetcher);
    expect(listed.proposals[0].proposal_id).toBe("proposal-1");
    expect(loaded.files[0].unified_diff).toContain("@@");
    for (const [, init] of fetcher.mock.calls) {
      expect(init?.credentials).toBe("omit");
      expect(init?.cache).toBe("no-store");
      expect(init?.redirect).toBe("error");
      expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
    }
  });

  it("records owner decisions but never advertises local application", async () => {
    const approved = { ...summary, status: "approved", version: 1, decision_recorded: true, application_enabled: false };
    const rejected = { ...summary, status: "rejected", version: 1, decision_recorded: true, application_enabled: false };
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(approved), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(rejected), { status: 200 }));
    const a = await approveNexusPatchProposal(base.api, base.org, base.project, base.token, "proposal-1", 0, fetcher);
    const r = await rejectNexusPatchProposal(base.api, base.org, base.project, base.token, "proposal-1", 0, fetcher);
    expect(a.status).toBe("approved");
    expect(r.status).toBe("rejected");
    expect(fetcher.mock.calls[0][1]?.method).toBe("POST");
    expect(fetcher.mock.calls[0][0]).toContain("/proposal-1/approve");
    expect(fetcher.mock.calls[1][0]).toContain("/proposal-1/reject");
  });

  it("rejects invalid decision payloads and oversized response bodies", async () => {
    const invalid = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      ...summary, decision_recorded: true, application_enabled: true,
    }), { status: 200 }));
    await expect(approveNexusPatchProposal(base.api, base.org, base.project, base.token, "proposal-1", 0, invalid))
      .rejects.toThrow("invalid proposal decision contract");
    const oversized = vi.fn<typeof fetch>().mockResolvedValue(new Response("x".repeat(8_500_001), { status: 200 }));
    await expect(listNexusPatchProposals(base.api, base.org, base.project, base.token, oversized))
      .rejects.toThrow("oversized patch proposal response");
  });
});


describe("NEXUS signed local apply capability", () => {
  it("requests a short-lived capability bound to the approved proposal and companion challenge", async () => {
    const challenge = "C".repeat(43);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      capability: "signed-capability",
      expires_at: Math.floor(Date.now() / 1000) + 60,
      workspace_id: "workspace_1234567890123456",
      companion_challenge: challenge,
      proposal_id: "proposal-1",
      proposal_version: 2,
      patch_sha256: "f".repeat(64),
      application_enabled: false,
    }), { status: 200 }));
    const result = await createNexusPatchApplyCapability(
      base.api, base.org, base.project, base.token,
      "proposal-1", 2, "workspace_1234567890123456", challenge, fetcher,
    );
    expect(result.capability).toBe("signed-capability");
    const request = fetcher.mock.calls[0][0] as Request;
    expect(request.url).toContain("/proposal-1/apply-capability");
    expect(request.headers.get("Authorization")).toBe("Bearer ephemeral-token");
    expect(await request.json()).toEqual({
      expected_version: 2,
      workspace_id: "workspace_1234567890123456",
      companion_challenge: challenge,
      confirm_apply: true,
    });
  });

  it("rejects a capability bound to another local workspace", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      capability: "signed-capability",
      expires_at: 1_900_000_000,
      workspace_id: "other-workspace",
      companion_challenge: "C".repeat(43),
      proposal_id: "proposal-1",
      proposal_version: 2,
      patch_sha256: "f".repeat(64),
      application_enabled: false,
    }), { status: 200 }));
    await expect(createNexusPatchApplyCapability(
      base.api, base.org, base.project, base.token,
      "proposal-1", 2, "workspace_1234567890123456", "C".repeat(43), fetcher,
    )).rejects.toThrow("invalid local apply capability");
  });
});
