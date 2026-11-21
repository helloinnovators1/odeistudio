import { describe, expect, it, vi } from "vitest";
import {
  NexusChatTransportError,
  sendNexusChat,
  sendNexusChatStream,
  sendNexusChatInspection,
  createNexusConversation,
  deleteNexusConversation,
  listNexusConversations,
  getNexusConversation,
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

  it("binds a chat response to a durable owner-scoped conversation", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(okResponse({
      conversation_persisted: true,
      conversation_id: "conversation-1",
    }));
    const result = await sendNexusChat({ ...base, conversationId: "conversation-1" }, fetcher);
    expect(result.conversation_persisted).toBe(true);
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toMatchObject({
      conversation_id: "conversation-1",
    });
  });

  it("creates, lists and loads durable conversations using bearer-only requests", async () => {
    const item = {
      conversation_id: "conversation-1",
      organization_id: "org-a",
      project_id: "project-a",
      title: "First chat",
      messages: [{
        message_id: "message-1", role: "user", content: "Hello",
        created_at: "2026-11-21T00:00:00Z",
      }],
      version: 1,
      created_at: "2026-11-21T00:00:00Z",
      updated_at: "2026-11-21T00:00:00Z",
    };
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(item), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ conversations: [{ conversation_id: item.conversation_id, title: item.title, version: item.version, message_count: 1, updated_at: item.updated_at }], limit: 30 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(item), { status: 200 }));
    const created = await createNexusConversation(base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken, "First chat", fetcher);
    const listed = await listNexusConversations(base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken, fetcher);
    const loaded = await getNexusConversation(base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken, "conversation-1", fetcher);
    expect(created.conversation_id).toBe("conversation-1");
    expect(listed).toHaveLength(1);
    expect(loaded.messages[0].content).toBe("Hello");
    for (const [, init] of fetcher.mock.calls) {
      expect(init?.credentials).toBe("omit");
      expect(init?.cache).toBe("no-store");
      expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
    }
  });

  it("deletes only the selected owner-scoped conversation and requires confirmation", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      conversation_id: "conversation-1", deleted: true,
    }), { status: 200 }));
    await expect(deleteNexusConversation(base.apiBaseUrl, base.organizationId, base.projectId, base.accessToken, "conversation-1", fetcher)).resolves.toBeUndefined();
    expect(fetcher.mock.calls[0][1]?.method).toBe("DELETE");
    expect(fetcher.mock.calls[0][1]?.credentials).toBe("omit");
  });

  it("parses incremental SSE deltas and validates durable completion", async () => {
    const events = [
      'event: status\ndata: {"status":"generating"}\n\n',
      'event: delta\ndata: {"delta":"Hello "}\n\n',
      'event: delta\ndata: {"delta":"world"}\n\n',
      'event: done\ndata: {"model":"test-model","conversation_id":"chat-one","conversation_persisted":true,"read_only":true,"tools_executed":0}\n\n',
    ].join("");
    const encoded = new TextEncoder().encode(events);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      new ReadableStream<Uint8Array>({ start(controller) {
        controller.enqueue(encoded.slice(0, 31));
        controller.enqueue(encoded.slice(31));
        controller.close();
      } }),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    ));
    let answer = "";
    const result = await sendNexusChatStream(
      { ...base, conversationId: "chat-one" },
      (delta) => { answer += delta; },
      fetcher,
    );
    expect(answer).toBe("Hello world");
    expect(result.conversation_persisted).toBe(true);
    const [url, init] = fetcher.mock.calls[0];
    expect(String(url)).toContain("/nexus/chat/stream");
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
  });

  it("parses CRLF-delimited SSE and rejects oversized event blocks", async () => {
    const crlf = [
      `event: delta\r\ndata: ${JSON.stringify({ delta: "hello" })}\r\n\r\n`,
      `event: done\r\ndata: ${JSON.stringify({ model: "test", conversation_id: "chat-one", conversation_persisted: true, read_only: true, tools_executed: 0 })}\r\n\r\n`,
    ].join("");
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(crlf, {
      status: 200, headers: { "Content-Type": "text/event-stream" },
    }));
    let answer = "";
    await sendNexusChatStream({ ...base, conversationId: "chat-one" }, (delta) => { answer += delta; }, fetcher);
    expect(answer).toBe("hello");
    const oversized = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      `event: delta\\ndata: ${"x".repeat(70_000)}\\n\\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    ));
    await expect(sendNexusChatStream(
      { ...base, conversationId: "chat-one" }, () => undefined, oversized,
    )).rejects.toThrow("oversized stream event");
  });
  it("rejects stream errors and completion events for a different conversation", async () => {
    const makeResponse = (payload: string) => new Response(payload, {
      status: 200, headers: { "Content-Type": "text/event-stream" },
    });
    const errorFetcher = vi.fn<typeof fetch>().mockResolvedValue(makeResponse(
      'event: error\ndata: {"message":"NEXUS failed"}\n\n',
    ));
    await expect(sendNexusChatStream(
      { ...base, conversationId: "chat-one" }, () => undefined, errorFetcher,
    )).rejects.toThrow("NEXUS failed");
    const mismatchFetcher = vi.fn<typeof fetch>().mockResolvedValue(makeResponse(
      'event: done\ndata: {"model":"test","conversation_id":"other-chat","conversation_persisted":true,"read_only":true,"tools_executed":0}\n\n',
    ));
    await expect(sendNexusChatStream(
      { ...base, conversationId: "chat-one" }, () => undefined, mismatchFetcher,
    )).rejects.toThrow("invalid stream completion contract");
  });

  it("sends explicit read-only attached-excerpt inspection requests and validates tool provenance", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      answer: "The attached file defines hello().", model: "test-model", read_only: true,
      tools_executed: 2, tool_names: ["list_attached_excerpts", "read_attached_excerpt"],
      conversation_persisted: true, conversation_id: "conversation-1",
    }), { status: 200 }));
    const result = await sendNexusChatInspection({
      ...base, conversationId: "conversation-1",
      workspaceFiles: [{ path: "src/main.py", content: "def hello(): pass" }],
    }, fetcher);
    expect(result.tools_executed).toBe(2);
    expect(result.tool_names).toContain("read_attached_excerpt");
    expect(String(fetcher.mock.calls[0][0])).toContain("/nexus/chat/inspect");
    expect(fetcher.mock.calls[0][1]?.credentials).toBe("omit");
    const unsafe = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      answer: "x", model: "test", read_only: true, tools_executed: 1,
      tool_names: ["run_shell"], conversation_persisted: true, conversation_id: "conversation-1",
    }), { status: 200 }));
    await expect(sendNexusChatInspection({
      ...base, conversationId: "conversation-1", workspaceFiles: [{ path: "src/main.py", content: "x" }],
    }, unsafe)).rejects.toThrow("invalid inspection response contract");
  });

  it("accepts only a persisted review-only proposal from attached-file tool inspection", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      answer: "I prepared a patch proposal.", model: "test-model", read_only: true,
      tools_executed: 1, tool_names: ["propose_attached_file_change"],
      conversation_persisted: true, conversation_id: "conversation-1",
      patch_proposal: {
        proposal_id: "proposal-1", title: "Update selected file", status: "pending",
        version: 0, file_count: 1, created_at: "2026-11-21T00:00:00Z",
        updated_at: "2026-11-21T00:00:00Z", can_decide: true, application_enabled: false,
      },
    }), { status: 200 }));
    const result = await sendNexusChatInspection({
      ...base, conversationId: "conversation-1",
      workspaceFiles: [{ path: "src/main.py", content: "print('old')" }],
    }, fetcher);
    expect(result.patch_proposal?.proposal_id).toBe("proposal-1");
    const unsafe = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      answer: "x", model: "test", read_only: true, tools_executed: 1,
      tool_names: ["propose_attached_file_change"], conversation_persisted: true,
      conversation_id: "conversation-1",
      patch_proposal: {
        proposal_id: "proposal-1", title: "Unsafe", status: "pending",
        version: 0, file_count: 1, created_at: "now", updated_at: "now",
        can_decide: true, application_enabled: true,
      },
    }), { status: 200 }));
    await expect(sendNexusChatInspection({
      ...base, conversationId: "conversation-1",
      workspaceFiles: [{ path: "src/main.py", content: "x" }],
    }, unsafe)).rejects.toThrow("invalid inspection response contract");
  });

  it("requires explicit attached excerpts before repository inspection", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(sendNexusChatInspection({ ...base, conversationId: "chat-one" }, fetcher))
      .rejects.toThrow("Attach between one and five");
    expect(fetcher).not.toHaveBeenCalled();
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

  it("enforces server-aligned per-message, per-file and combined input bounds before network access", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(sendNexusChat({
      ...base, messages: [{ role: "user", content: "x".repeat(8_001) }],
    }, fetcher)).rejects.toThrow("1 to 8,000");
    await expect(sendNexusChat({
      ...base, workspaceFiles: [{ path: "large.txt", content: "x".repeat(8_001) }],
    }, fetcher)).rejects.toThrow("at most 8,000");
    await expect(sendNexusChat({
      ...base,
      messages: [{ role: "user", content: "x".repeat(8_000) }],
      workspaceFiles: [{ path: "large.txt", content: "y".repeat(8_000) },
        { path: "second.txt", content: "z".repeat(8_000) },
        { path: "third.txt", content: "w".repeat(8_000) },
        { path: "fourth.txt", content: "v".repeat(8_000) },
        { path: "fifth.txt", content: "u".repeat(8_000) }],
    }, fetcher)).rejects.toThrow("40,000 characters");
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
