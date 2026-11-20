import { describe, expect, it, vi } from "vitest";
import {
  NexusChatTransportError,
  sendNexusChat,
  type NexusChatRequest,
} from "./nexus-chat";

const base: NexusChatRequest = {
  apiBaseUrl: "https://api.example.test/",
  organizationId: "org-a",
  projectId: "project-a",
  accessToken: "ephemeral-token",
  messages: [{ role: "user", content: "Explain this project." }],
  cloudModelConsent: true,
};

function okResponse(overrides: Record<string, unknown> = {}) {
  return new Response(JSON.stringify({
    answer: "This is a read-only explanation.",
    model: "test-model",
    read_only: true,
    tools_executed: 0,
    conversation_persisted: false,
    ...overrides,
  }), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("NEXUS chat transport", () => {
  it("sends the authenticated, consented project-scoped request without credentials or caching", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(okResponse());
    const result = await sendNexusChat(base, fetcher);
    expect(result.answer).toContain("read-only");
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("https://api.example.test/api/v1/organizations/org-a/projects/project-a/nexus/chat");
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    expect(init?.redirect).toBe("error");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
    expect(JSON.parse(String(init?.body))).toMatchObject({ cloud_model_consent: true });
  });

  it("allows HTTP only for loopback development endpoints", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(okResponse());
    await sendNexusChat({ ...base, apiBaseUrl: "http://127.0.0.1:8000" }, fetcher);
    expect(fetcher).toHaveBeenCalledOnce();
    await expect(sendNexusChat({ ...base, apiBaseUrl: "http://api.example.test" }, fetcher))
      .rejects.toThrow("must use HTTPS");
  });

  it("rejects URL credentials and malformed resource identifiers before network access", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(sendNexusChat({ ...base, apiBaseUrl: "https://user:pass@example.test" }, fetcher))
      .rejects.toThrow("without URL credentials");
    await expect(sendNexusChat({ ...base, projectId: " " }, fetcher)).rejects.toThrow("Project ID");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("requires explicit consent, a bounded conversation and a final user message", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(sendNexusChat({ ...base, cloudModelConsent: false as true }, fetcher))
      .rejects.toThrow("Explicit cloud-model consent");
    await expect(sendNexusChat({
      ...base, messages: [{ role: "assistant", content: "Not a user turn" }],
    }, fetcher)).rejects.toThrow("final conversation message");
    await expect(sendNexusChat({ ...base, messages: Array(21).fill(base.messages[0]) }, fetcher))
      .rejects.toThrow("between 1 and 20");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("limits selected workspace excerpts", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(sendNexusChat({
      ...base, workspaceFiles: Array(6).fill({ path: "a.txt", content: "x" }),
    }, fetcher)).rejects.toThrow("At most five");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("maps server errors to safe messages without echoing response bodies", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({ code: "MODEL_NOT_CONFIGURED", detail: "private provider diagnostics" }),
      { status: 503 },
    ));
    await expect(sendNexusChat(base, fetcher)).rejects.toMatchObject({
      name: "NexusChatTransportError",
      status: 503,
      code: "MODEL_NOT_CONFIGURED",
      message: "The NEXUS model provider is not configured.",
    } satisfies Partial<NexusChatTransportError>);
  });

  it("rejects malformed and oversized success contracts", async () => {
    const malformed = vi.fn<typeof fetch>().mockResolvedValue(okResponse({ tools_executed: 1 }));
    await expect(sendNexusChat(base, malformed)).rejects.toThrow("unexpected response contract");
    const oversized = vi.fn<typeof fetch>().mockResolvedValue(new Response("x".repeat(32_001), { status: 200 }));
    await expect(sendNexusChat(base, oversized)).rejects.toThrow("oversized response");
  });
});
