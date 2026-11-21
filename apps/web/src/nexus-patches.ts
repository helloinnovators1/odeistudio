import { NexusChatTransportError } from "./nexus-chat";

export interface NexusPatchDraft {
  path: string;
  mode: "preview_only";
  writes_performed: false;
  base_sha256: string;
  result_sha256: string;
  replacement_content: string;
  unified_diff: string;
  model: string;
}

export async function generateNexusPatchDraft(
  apiBaseUrl: string,
  organizationId: string,
  projectId: string,
  accessToken: string,
  task: string,
  path: string,
  content: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<NexusPatchDraft> {
  const token = accessToken.trim();
  if (!token || token.length > 16_384 || /[\r\n]/.test(token)) {
    throw new TypeError("A valid in-memory access token is required.");
  }
  const goal = task.trim();
  if (!goal || goal.length > 8_000) throw new TypeError("Patch task must contain 1 to 8,000 characters.");
  if (!path.trim() || path.length > 1_024 || path.startsWith("/") || path.includes("\\")) {
    throw new TypeError("Select a safe relative file path.");
  }
  if (!content || new TextEncoder().encode(content).byteLength > 40_000) {
    throw new TypeError("Select a non-empty text file of at most 40 KB.");
  }
  const base = new URL(apiBaseUrl);
  const localHttp = base.protocol === "http:" &&
    (base.hostname === "localhost" || base.hostname === "127.0.0.1" || base.hostname === "[::1]");
  if ((base.protocol !== "https:" && !localHttp) || base.username || base.password || base.search || base.hash) {
    throw new TypeError("NEXUS API must use HTTPS (or loopback HTTP) without URL credentials or query parameters.");
  }
  const response = await fetcher(
    `${base.toString().replace(/\/+$/, "")}/api/v1/organizations/${encodeURIComponent(organizationId)}/projects/${encodeURIComponent(projectId)}/nexus/patch-drafts`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        task: goal, path, content, cloud_model_consent: true,
      }),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal,
    },
  );
  const raw = await response.text();
  if (raw.length > 1_200_000) throw new NexusChatTransportError("NEXUS returned an oversized patch draft.", response.status);
  let payload: Record<string, unknown>;
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid");
    payload = parsed as Record<string, unknown>;
  } catch {
    throw new NexusChatTransportError("NEXUS returned invalid patch draft data.", response.status);
  }
  if (!response.ok) {
    const detail = payload.detail && typeof payload.detail === "object"
      ? payload.detail as Record<string, unknown> : payload;
    const code = typeof detail.code === "string" ? detail.code : undefined;
    const messages: Record<string, string> = {
      CLOUD_MODEL_CONSENT_REQUIRED: "Explicit cloud-model consent is required.",
      PATCH_PATH_REJECTED: "This file path is protected and cannot be proposed for editing.",
      PATCH_DRAFT_FAILED: "NEXUS could not produce a valid patch draft.",
      MODEL_NOT_CONFIGURED: "The NEXUS model provider is not configured.",
    };
    throw new NexusChatTransportError(
      messages[code ?? ""] ?? "NEXUS could not generate a patch draft.",
      response.status, code,
    );
  }
  if (
    payload.path !== path || payload.mode !== "preview_only" ||
    payload.writes_performed !== false ||
    typeof payload.base_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(payload.base_sha256) ||
    typeof payload.result_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(payload.result_sha256) ||
    typeof payload.replacement_content !== "string" ||
    new TextEncoder().encode(payload.replacement_content).byteLength > 1_000_000 ||
    typeof payload.unified_diff !== "string" ||
    typeof payload.model !== "string" || !payload.model
  ) {
    throw new NexusChatTransportError("NEXUS returned an invalid patch draft contract.", response.status);
  }
  return payload as unknown as NexusPatchDraft;
}
