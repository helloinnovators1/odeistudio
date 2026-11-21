export interface NexusChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface NexusWorkspaceExcerpt {
  path: string;
  content: string;
}

export interface NexusChatRequest {
  apiBaseUrl: string;
  organizationId: string;
  projectId: string;
  accessToken: string;
  messages: NexusChatMessage[];
  workspaceFiles?: NexusWorkspaceExcerpt[];
  cloudModelConsent: true;
  signal?: AbortSignal;
  conversationId?: string;
}

export interface NexusChatResponse {
  answer: string;
  model: string;
  read_only: true;
  tools_executed: 0;
  conversation_persisted: boolean;
  conversation_id?: string | null;
}

export class NexusChatTransportError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "NexusChatTransportError";
  }
}

const MAX_RESPONSE_CHARS = 32_000;

function normalizeApiBaseUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new TypeError("A valid NEXUS API base URL is required.");
  }
  const localHttp = url.protocol === "http:" &&
    (url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "[::1]");
  if ((url.protocol !== "https:" && !localHttp) ||
      url.username || url.password || url.search || url.hash) {
    throw new TypeError("NEXUS API must use HTTPS (or loopback HTTP) without URL credentials or query parameters.");
  }
  return url.toString().replace(/\/+$/, "");
}

function requireIdentifier(value: string, label: string): string {
  const clean = value.trim();
  if (!clean || clean.length > 128) {
    throw new TypeError(`${label} must contain 1 to 128 characters.`);
  }
  return clean;
}

export async function sendNexusChat(
  request: NexusChatRequest,
  fetcher: typeof fetch = fetch,
): Promise<NexusChatResponse> {
  const apiBaseUrl = normalizeApiBaseUrl(request.apiBaseUrl);
  const organizationId = requireIdentifier(request.organizationId, "Organization ID");
  const projectId = requireIdentifier(request.projectId, "Project ID");
  const accessToken = request.accessToken.trim();
  if (!accessToken || accessToken.length > 16_384) {
    throw new TypeError("A valid in-memory access token is required.");
  }
  if (request.cloudModelConsent !== true) {
    throw new TypeError("Explicit cloud-model consent is required.");
  }
  if (!Array.isArray(request.messages) || request.messages.length < 1 || request.messages.length > 20) {
    throw new TypeError("Conversation must contain between 1 and 20 messages.");
  }
  let totalCharacters = 0;
  for (const message of request.messages) {
    if (
      !message || !["user", "assistant"].includes(message.role) ||
      typeof message.content !== "string" || !message.content.trim() ||
      message.content.length > 8_000
    ) {
      throw new TypeError("Each message must have a valid role and contain 1 to 8,000 characters.");
    }
    totalCharacters += message.content.length;
  }
  if (request.messages[request.messages.length - 1]?.role !== "user") {
    throw new TypeError("The final conversation message must be from the user.");
  }
  const workspaceFiles = request.workspaceFiles ?? [];
  if (!Array.isArray(workspaceFiles) || workspaceFiles.length > 5) {
    throw new TypeError("At most five workspace excerpts may be sent.");
  }
  for (const file of workspaceFiles) {
    if (
      !file || typeof file.path !== "string" || !file.path.trim() || file.path.length > 1_024 ||
      typeof file.content !== "string" || file.content.length > 8_000
    ) {
      throw new TypeError("Each workspace excerpt must have a valid path and at most 8,000 characters.");
    }
    totalCharacters += file.path.length + file.content.length;
  }
  if (totalCharacters > 40_000) {
    throw new TypeError("Combined conversation and workspace context exceeds 40,000 characters.");
  }

  const response = await fetcher(
    `${apiBaseUrl}/api/v1/organizations/${encodeURIComponent(organizationId)}/projects/${encodeURIComponent(projectId)}/nexus/chat`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        messages: request.messages,
        workspace_files: request.workspaceFiles ?? [],
        cloud_model_consent: true,
        ...(request.conversationId ? { conversation_id: request.conversationId } : {}),
      }),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: request.signal,
    },
  );

  const raw = await response.text();
  if (raw.length > MAX_RESPONSE_CHARS) {
    throw new NexusChatTransportError("NEXUS returned an oversized response.", response.status);
  }
  let payload: Record<string, unknown> = {};
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      payload = parsed as Record<string, unknown>;
    }
  } catch {
    throw new NexusChatTransportError("NEXUS returned an invalid response.", response.status);
  }

  if (!response.ok) {
    const code = typeof payload.code === "string" ? payload.code : undefined;
    const safeMessages: Record<string, string> = {
      CLOUD_MODEL_CONSENT_REQUIRED: "Explicit cloud-model consent is required.",
      PROJECT_STORE_UNAVAILABLE: "Project authorization is temporarily unavailable.",
      MODEL_NOT_CONFIGURED: "The NEXUS model provider is not configured.",
      NEXUS_CHAT_UNAVAILABLE: "NEXUS chat is temporarily unavailable.",
    };
    throw new NexusChatTransportError(
      safeMessages[code ?? ""] ?? "NEXUS could not complete the chat request.",
      response.status,
      code,
    );
  }

  if (
    typeof payload.answer !== "string" || !payload.answer.trim() ||
    typeof payload.model !== "string" || payload.read_only !== true ||
    payload.tools_executed !== 0 || typeof payload.conversation_persisted !== "boolean" ||
    (request.conversationId && (payload.conversation_persisted !== true || payload.conversation_id !== request.conversationId))
  ) {
    throw new NexusChatTransportError("NEXUS returned an unexpected response contract.", response.status);
  }
  return payload as unknown as NexusChatResponse;
}


export interface NexusConversationMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface NexusConversationSummary {
  conversation_id: string;
  title: string;
  version: number;
  message_count: number;
  updated_at: string;
}

export interface NexusConversation {
  conversation_id: string;
  organization_id: string;
  project_id: string;
  title: string;
  messages: NexusConversationMessage[];
  version: number;
  created_at: string;
  updated_at: string;
}

async function conversationRequest(
  apiBaseUrlValue: string,
  organizationIdValue: string,
  projectIdValue: string,
  accessTokenValue: string,
  path: string,
  method: "GET" | "POST" | "DELETE",
  body?: unknown,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<Record<string, unknown>> {
  const base = normalizeApiBaseUrl(apiBaseUrlValue);
  const organizationId = requireIdentifier(organizationIdValue, "Organization ID");
  const projectId = requireIdentifier(projectIdValue, "Project ID");
  const token = accessTokenValue.trim();
  if (!token || token.length > 16_384) throw new TypeError("A valid in-memory access token is required.");
  const response = await fetcher(
    `${base}/api/v1/organizations/${encodeURIComponent(organizationId)}/projects/${encodeURIComponent(projectId)}/nexus/conversations${path}`,
    {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal,
    },
  );
  const raw = await response.text();
  if (raw.length > 7_000_000) throw new NexusChatTransportError("NEXUS returned oversized conversation data.", response.status);
  let payload: Record<string, unknown>;
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid");
    payload = parsed as Record<string, unknown>;
  } catch {
    throw new NexusChatTransportError("NEXUS returned invalid conversation data.", response.status);
  }
  if (!response.ok) {
    const detail = payload.detail && typeof payload.detail === "object"
      ? payload.detail as Record<string, unknown> : payload;
    const code = typeof detail.code === "string" ? detail.code : undefined;
    throw new NexusChatTransportError(
      code === "CONVERSATION_NOT_FOUND" ? "Conversation was not found."
        : code === "CONVERSATION_VERSION_CONFLICT" ? "Conversation changed. Reload its history."
        : "NEXUS could not access conversation history.",
      response.status, code,
    );
  }
  return payload;
}

function validateConversation(value: unknown): NexusConversation {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new NexusChatTransportError("NEXUS returned an invalid conversation.", 200);
  }
  const item = value as Record<string, unknown>;
  if (
    typeof item.conversation_id !== "string" || !item.conversation_id ||
    typeof item.organization_id !== "string" || typeof item.project_id !== "string" ||
    typeof item.title !== "string" || !Array.isArray(item.messages) ||
    item.messages.length > 200 || typeof item.version !== "number" || !Number.isInteger(item.version) ||
    typeof item.created_at !== "string" || typeof item.updated_at !== "string"
  ) throw new NexusChatTransportError("NEXUS returned an invalid conversation contract.", 200);
  const messages = item.messages.map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new NexusChatTransportError("NEXUS returned an invalid conversation message.", 200);
    }
    const message = entry as Record<string, unknown>;
    if (
      typeof message.message_id !== "string" ||
      (message.role !== "user" && message.role !== "assistant") ||
      typeof message.content !== "string" || message.content.length > 16_000 ||
      typeof message.created_at !== "string"
    ) throw new NexusChatTransportError("NEXUS returned an invalid conversation message.", 200);
    return message as unknown as NexusConversationMessage;
  });
  return { ...item, messages } as unknown as NexusConversation;
}

export async function createNexusConversation(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, title: string, fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<NexusConversation> {
  const payload = await conversationRequest(
    apiBaseUrl, organizationId, projectId, accessToken, "", "POST",
    { title: title.trim().slice(0, 120) }, signal, fetcher,
  );
  return validateConversation(payload);
}

export async function listNexusConversations(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, fetcher: typeof fetch = fetch,
): Promise<NexusConversationSummary[]> {
  const payload = await conversationRequest(
    apiBaseUrl, organizationId, projectId, accessToken, "?limit=30", "GET",
    undefined, undefined, fetcher,
  );
  if (!Array.isArray(payload.conversations) || payload.conversations.length > 30) {
    throw new NexusChatTransportError("NEXUS returned an invalid conversation list.", 200);
  }
  return payload.conversations.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new NexusChatTransportError("NEXUS returned an invalid conversation summary.", 200);
    }
    const item = value as Record<string, unknown>;
    if (
      typeof item.conversation_id !== "string" || !item.conversation_id ||
      typeof item.title !== "string" || typeof item.version !== "number" || !Number.isInteger(item.version) ||
      typeof item.message_count !== "number" || !Number.isInteger(item.message_count) || item.message_count < 0 ||
      typeof item.updated_at !== "string"
    ) throw new NexusChatTransportError("NEXUS returned an invalid conversation summary.", 200);
    return item as unknown as NexusConversationSummary;
  });
}

export async function getNexusConversation(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, conversationId: string, fetcher: typeof fetch = fetch,
): Promise<NexusConversation> {
  const id = requireIdentifier(conversationId, "Conversation ID");
  const payload = await conversationRequest(
    apiBaseUrl, organizationId, projectId, accessToken,
    `/${encodeURIComponent(id)}`, "GET", undefined, undefined, fetcher,
  );
  return validateConversation(payload);
}


export async function deleteNexusConversation(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, conversationId: string, fetcher: typeof fetch = fetch,
): Promise<void> {
  const id = requireIdentifier(conversationId, "Conversation ID");
  const payload = await conversationRequest(
    apiBaseUrl, organizationId, projectId, accessToken,
    "/" + encodeURIComponent(id), "DELETE", undefined, undefined, fetcher,
  );
  if (payload.conversation_id !== id || payload.deleted !== true) {
    throw new NexusChatTransportError("NEXUS did not confirm conversation deletion.", 200);
  }
}


export interface NexusChatStreamResult {
  model: string;
  conversation_id: string;
  conversation_persisted: true;
}

export async function sendNexusChatStream(
  request: NexusChatRequest,
  onDelta: (delta: string) => void,
  fetcher: typeof fetch = fetch,
): Promise<NexusChatStreamResult> {
  const apiBaseUrl = normalizeApiBaseUrl(request.apiBaseUrl);
  const organizationId = requireIdentifier(request.organizationId, "Organization ID");
  const projectId = requireIdentifier(request.projectId, "Project ID");
  const conversationId = requireIdentifier(request.conversationId ?? "", "Conversation ID");
  const accessToken = request.accessToken.trim();
  if (!accessToken || accessToken.length > 16_384) throw new TypeError("A valid in-memory access token is required.");
  if (request.cloudModelConsent !== true) throw new TypeError("Explicit cloud-model consent is required.");
  if (!Array.isArray(request.messages) || request.messages.length < 1 || request.messages.length > 20) {
    throw new TypeError("Conversation must contain between 1 and 20 messages.");
  }
  let totalCharacters = 0;
  for (const message of request.messages) {
    if (!message || !["user", "assistant"].includes(message.role) ||
        typeof message.content !== "string" || !message.content.trim() ||
        message.content.length > 8_000) {
      throw new TypeError("Each message must have a valid role and contain 1 to 8,000 characters.");
    }
    totalCharacters += message.content.length;
  }
  if (request.messages.at(-1)?.role !== "user") throw new TypeError("The final conversation message must be from the user.");
  const workspaceFiles = request.workspaceFiles ?? [];
  if (!Array.isArray(workspaceFiles) || workspaceFiles.length > 5) throw new TypeError("At most five workspace excerpts may be sent.");
  for (const file of workspaceFiles) {
    if (!file || typeof file.path !== "string" || !file.path.trim() || file.path.length > 1_024 ||
        typeof file.content !== "string" || file.content.length > 8_000) {
      throw new TypeError("Each workspace excerpt must have a valid path and at most 8,000 characters.");
    }
    totalCharacters += file.path.length + file.content.length;
  }
  if (totalCharacters > 40_000) throw new TypeError("Combined conversation and workspace context exceeds 40,000 characters.");

  const response = await fetcher(
    `${apiBaseUrl}/api/v1/organizations/${encodeURIComponent(organizationId)}/projects/${encodeURIComponent(projectId)}/nexus/chat/stream`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        messages: request.messages,
        workspace_files: workspaceFiles,
        cloud_model_consent: true,
        conversation_id: conversationId,
      }),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: request.signal,
    },
  );

  if (!response.ok) {
    const raw = await response.text();
    let payload: Record<string, unknown> = {};
    try {
      const parsed: unknown = raw ? JSON.parse(raw) : {};
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) payload = parsed as Record<string, unknown>;
    } catch { /* Use a safe generic error. */ }
    const detail = payload.detail && typeof payload.detail === "object"
      ? payload.detail as Record<string, unknown> : payload;
    const code = typeof detail.code === "string" ? detail.code : undefined;
    throw new NexusChatTransportError(
      code === "MODEL_NOT_CONFIGURED" ? "The NEXUS model provider is not configured."
        : code === "CONVERSATION_VERSION_CONFLICT" ? "Conversation changed. Reload its history."
        : "NEXUS could not start the streamed response.",
      response.status, code,
    );
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream") || !response.body) {
    throw new NexusChatTransportError("NEXUS did not return an event stream.", response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let totalOutput = 0;
  let result: NexusChatStreamResult | null = null;
  function dispatch(block: string): void {
    let eventName = "message";
    const data: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    let payload: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(data.join("\n"));
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid");
      payload = parsed as Record<string, unknown>;
    } catch {
      throw new NexusChatTransportError("NEXUS returned a malformed stream event.", response.status);
    }
    if (eventName === "delta") {
      if (typeof payload.delta !== "string") throw new NexusChatTransportError("NEXUS returned an invalid text delta.", response.status);
      totalOutput += payload.delta.length;
      if (totalOutput > 16_000) throw new NexusChatTransportError("NEXUS streamed an oversized response.", response.status);
      onDelta(payload.delta);
    } else if (eventName === "error") {
      throw new NexusChatTransportError(
        typeof payload.message === "string" ? payload.message : "NEXUS streaming failed.",
        response.status,
      );
    } else if (eventName === "done") {
      if (
        typeof payload.model !== "string" ||
        payload.conversation_id !== conversationId ||
        payload.conversation_persisted !== true ||
        payload.read_only !== true || payload.tools_executed !== 0
      ) throw new NexusChatTransportError("NEXUS returned an invalid stream completion contract.", response.status);
      result = {
        model: payload.model,
        conversation_id: conversationId,
        conversation_persisted: true,
      };
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");
      if (buffer.length > 65_536 && !buffer.includes("\n\n")) {
        throw new NexusChatTransportError("NEXUS returned an oversized stream event.", response.status);
      }
      let boundary = buffer.indexOf("\n\n");
      if (boundary > 65_536) throw new NexusChatTransportError("NEXUS returned an oversized stream event.", response.status);
      while (boundary >= 0) {
        dispatch(buffer.slice(0, boundary).replace(/\r$/, ""));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
        if (boundary > 65_536) throw new NexusChatTransportError("NEXUS returned an oversized stream event.", response.status);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) dispatch(buffer);
  } catch (cause) {
    try { await reader.cancel(); } catch { /* The stream may already be closed. */ }
    throw cause;
  } finally {
    reader.releaseLock();
  }
  if (!result) throw new NexusChatTransportError("NEXUS stream ended without a completion event.", response.status);
  return result;
}
