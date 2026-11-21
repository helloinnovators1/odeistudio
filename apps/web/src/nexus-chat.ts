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
}

export interface NexusChatResponse {
  answer: string;
  model: string;
  read_only: true;
  tools_executed: 0;
  conversation_persisted: false;
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
  if (request.messages.at(-1)?.role !== "user") {
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
    payload.tools_executed !== 0 || payload.conversation_persisted !== false
  ) {
    throw new NexusChatTransportError("NEXUS returned an unexpected response contract.", response.status);
  }
  return payload as unknown as NexusChatResponse;
}
