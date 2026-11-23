import { NexusChatTransportError } from "./nexus-chat";

export interface NexusTask {
  task_id: string;
  organization_id: string;
  project_id: string;
  owner_id: string;
  goal: string;
  status: string;
  plan: string | null;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

function normalizeBase(value: string): string {
  let url: URL;
  try { url = new URL(value); } catch { throw new TypeError("A valid NEXUS API base URL is required."); }
  const localHttp = url.protocol === "http:" &&
    (url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "[::1]");
  if ((url.protocol !== "https:" && !localHttp) || url.username || url.password || url.search || url.hash) {
    throw new TypeError("NEXUS API must use HTTPS (or loopback HTTP) without URL credentials or query parameters.");
  }
  return url.toString().replace(/\/+$/, "");
}

function validateTask(value: unknown): NexusTask {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new NexusChatTransportError("NEXUS returned an invalid task.", 200);
  }
  const item = value as Record<string, unknown>;
  if (
    typeof item.task_id !== "string" || !item.task_id ||
    typeof item.organization_id !== "string" || typeof item.project_id !== "string" ||
    typeof item.owner_id !== "string" || typeof item.goal !== "string" ||
    typeof item.status !== "string" ||
    !(typeof item.plan === "string" || item.plan === null) ||
    (typeof item.plan === "string" && item.plan.length > 32_000) ||
    typeof item.version !== "number" || !Number.isInteger(item.version) ||
    !(typeof item.created_at === "string" || item.created_at === null) ||
    !(typeof item.updated_at === "string" || item.updated_at === null)
  ) throw new NexusChatTransportError("NEXUS returned an invalid task contract.", 200);
  return item as unknown as NexusTask;
}

async function taskRequest(
  apiBaseUrl: string,
  organizationId: string,
  projectId: string,
  accessToken: string,
  path: string,
  method: "POST" | "GET",
  body?: unknown,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<NexusTask> {
  const token = accessToken.trim();
  if (!token || token.length > 16_384 || /[\r\n]/.test(token)) {
    throw new TypeError("A valid in-memory access token is required.");
  }
  const response = await fetcher(
    `${normalizeBase(apiBaseUrl)}/api/v1/organizations/${encodeURIComponent(organizationId)}/projects/${encodeURIComponent(projectId)}/tasks${path}`,
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
  if (raw.length > 40_000) throw new NexusChatTransportError("NEXUS returned an oversized task response.", response.status);
  let payload: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid");
    payload = parsed as Record<string, unknown>;
  } catch {
    throw new NexusChatTransportError("NEXUS returned invalid task data.", response.status);
  }
  if (!response.ok) {
    const detail = payload.detail && typeof payload.detail === "object"
      ? payload.detail as Record<string, unknown> : payload;
    const code = typeof detail.code === "string" ? detail.code : undefined;
    const messages: Record<string, string> = {
      PROJECT_OWNER_APPROVAL_REQUIRED: "Only the project owner can approve this plan.",
      TASK_VERSION_OR_STATE_CONFLICT: "The task changed. Reload it before trying again.",
      CLOUD_MODEL_CONSENT_REQUIRED: "Explicit cloud-model consent is required.",
      MODEL_NOT_CONFIGURED: "The NEXUS model provider is not configured.",
    };
    throw new NexusChatTransportError(
      messages[code ?? ""] ?? "NEXUS could not complete the task request.",
      response.status, code,
    );
  }
  return validateTask(payload);
}

export function createNexusTask(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, task: string, projectContext = "",
  signal?: AbortSignal, fetcher: typeof fetch = fetch,
): Promise<NexusTask> {
  const goal = task.trim();
  if (!goal || goal.length > 8_000) throw new TypeError("Task description must contain 1 to 8,000 characters.");
  if (projectContext.length > 24_000) throw new TypeError("Selected project context exceeds 24,000 characters.");
  return taskRequest(
    apiBaseUrl, organizationId, projectId, accessToken, "", "POST",
    { task: goal, project_context: projectContext, cloud_model_consent: true },
    signal, fetcher,
  );
}

export function getNexusTask(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, taskId: string, fetcher: typeof fetch = fetch,
): Promise<NexusTask> {
  return taskRequest(
    apiBaseUrl, organizationId, projectId, accessToken,
    "/" + encodeURIComponent(taskId), "GET", undefined, undefined, fetcher,
  );
}

export function approveNexusTask(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, taskId: string, expectedVersion: number,
  fetcher: typeof fetch = fetch, signal?: AbortSignal,
): Promise<NexusTask> {
  return taskRequest(
    apiBaseUrl, organizationId, projectId, accessToken,
    "/" + encodeURIComponent(taskId) + "/approve", "POST",
    { expected_version: expectedVersion }, signal, fetcher,
  );
}

export function cancelNexusTask(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, taskId: string, expectedVersion: number,
  fetcher: typeof fetch = fetch, signal?: AbortSignal,
): Promise<NexusTask> {
  return taskRequest(
    apiBaseUrl, organizationId, projectId, accessToken,
    "/" + encodeURIComponent(taskId) + "/cancel", "POST",
    { expected_version: expectedVersion }, signal, fetcher,
  );
}
