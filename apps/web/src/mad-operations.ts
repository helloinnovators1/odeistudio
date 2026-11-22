export interface MadMetrics {
  observed_at: string;
  freshness: "fresh" | "stale" | "unknown";
  worker_stale_after_seconds: number;
  workers: { state: "healthy" | "degraded" | "unknown"; known: number; fresh: number; stale: number; stopping: number };
  queue: { state: "healthy" | "degraded" | "unknown"; queued: number; active: number; oldest_queued_at: string | null };
  executions_24h: { completed: number; failed: number; cancelled: number };
  alerts: MadAlert[];
}
export interface MadAlert {
  id: string;
  deduplication_key: string;
  severity: "info" | "warning" | "critical";
  status: "firing";
  summary: string;
  observed_at: string;
  runbook: string;
  age_seconds?: number;
  failed_24h?: number;
}
export interface MadIncidentHistory {
  action: string;
  actor: string;
  at: string;
  version: number;
  assignee?: string;
}
export interface MadIncident {
  id: string;
  incident_id: string;
  alert_id: string;
  severity: "info" | "warning" | "critical";
  summary: string;
  runbook: string;
  status: "firing" | "acknowledged" | "resolved";
  assignee: string | null;
  version: number;
  first_seen_at: string;
  last_seen_at: string;
  updated_at: string;
  history: MadIncidentHistory[];
}
type Fetcher = typeof fetch;
const MAX_RESPONSE_BYTES = 256_000;

function normalizeBase(value: string): string {
  let url: URL;
  try { url = new URL(value); } catch { throw new TypeError("A valid ODEI API base URL is required."); }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if ((url.protocol !== "https:" && !(url.protocol === "http:" && loopback))
    || url.username || url.password || url.search || url.hash) {
    throw new TypeError("MAD API must use HTTPS (or loopback HTTP) without URL credentials or query parameters.");
  }
  return url.toString().replace(/\/+$/, "");
}
function validateToken(token: string): void {
  if (typeof token !== "string" || !/^[A-Za-z0-9\-._~+/]+=*$/.test(token) || token.length > 8_192) {
    throw new TypeError("A valid in-memory ODID access token is required.");
  }
}
async function request<T>(base: string, path: string, token: string, fetcher: Fetcher, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
  const url = normalizeBase(base) + path;
  validateToken(token);
  const headers = new Headers({ Accept: "application/json", Authorization: "Bearer " + token });
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetcher(url, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "omit", cache: "no-store", redirect: "error",
  });
  const raw = await response.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_RESPONSE_BYTES) throw new Error("MAD API returned an oversized response.");
  let payload: Record<string, unknown>;
  try { payload = JSON.parse(raw) as Record<string, unknown>; } catch { throw new Error("MAD API returned an invalid response."); }
  if (!response.ok) {
    const detail = payload.detail as { message?: unknown } | string | undefined;
    const message = typeof detail === "string" ? detail
      : detail && typeof detail.message === "string" ? detail.message
      : response.status === 403 ? "Your ODID identity does not have the required MAD operator permission."
      : "MAD API request failed with HTTP " + response.status + ".";
    throw new Error(message);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("MAD API returned an invalid response.");
  return payload as T;
}
function nonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}
function validTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}
function validateMetrics(value: MadMetrics): MadMetrics {
  if (!value || typeof value !== "object" || !validTimestamp(value.observed_at)
    || !["fresh", "stale", "unknown"].includes(value.freshness)
    || !value.workers || !["healthy", "degraded", "unknown"].includes(value.workers.state)
    || !["known", "fresh", "stale", "stopping"].every((key) => nonNegativeInteger(value.workers[key as keyof MadMetrics["workers"]]))
    || !value.queue || !["healthy", "degraded", "unknown"].includes(value.queue.state)
    || !["queued", "active"].every((key) => nonNegativeInteger(value.queue[key as keyof MadMetrics["queue"]]))
    || !(value.queue.oldest_queued_at === null || validTimestamp(value.queue.oldest_queued_at))
    || !value.executions_24h || !["completed", "failed", "cancelled"].every((key) => nonNegativeInteger(value.executions_24h[key as keyof MadMetrics["executions_24h"]]))
    || !Array.isArray(value.alerts) || value.alerts.length > 100) {
    throw new Error("MAD API returned an unexpected metrics contract.");
  }
  return value;
}
function validateIncident(value: MadIncident): MadIncident {
  if (!value || typeof value !== "object" || typeof value.incident_id !== "string"
    || typeof value.id !== "string" || !["info", "warning", "critical"].includes(value.severity)
    || !["firing", "acknowledged", "resolved"].includes(value.status)
    || typeof value.summary !== "string" || !validTimestamp(value.updated_at)
    || !Number.isSafeInteger(value.version) || value.version < 1
    || !Array.isArray(value.history) || value.history.length > 200) {
    throw new Error("MAD API returned an unexpected incident contract.");
  }
  return value;
}
export async function getMadExecutionMetrics(
  apiBaseUrl: string, accessToken: string, fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<MadMetrics> {
  const value = await request<MadMetrics>(apiBaseUrl, "/api/v1/mad/execution-metrics", accessToken, fetcher);
  return validateMetrics(value);
}
export async function listMadIncidents(
  apiBaseUrl: string, accessToken: string,
  options: { includeResolved?: boolean; limit?: number; fetcher?: Fetcher; signal?: AbortSignal } = {},
): Promise<MadIncident[]> {
  const limit = options.limit ?? 100;
  if (!Number.isInteger(limit) || limit < 1 || limit > 200) throw new RangeError("MAD incident page size must be between 1 and 200.");
  const query = new URLSearchParams({ include_resolved: String(options.includeResolved ?? false), limit: String(limit) });
  const payload = await request<{ incidents: MadIncident[] }>(
    apiBaseUrl, "/api/v1/mad/incidents?" + query.toString(), accessToken, options.fetcher ?? fetch,
  );
  if (!Array.isArray(payload.incidents) || payload.incidents.length > limit) throw new Error("MAD API returned an unexpected incident-list contract.");
  const incidents = payload.incidents.map(validateIncident);
  if (new Set(incidents.map((item) => item.incident_id)).size !== incidents.length) throw new Error("MAD API returned duplicate incident identities.");
  return incidents;
}
export async function transitionMadIncident(
  apiBaseUrl: string, accessToken: string, incident: Pick<MadIncident, "incident_id" | "version">,
  action: "acknowledge" | "assign" | "resolve" | "reopen",
  options: { assignee?: string; fetcher?: Fetcher; signal?: AbortSignal } = {},
): Promise<MadIncident> {
  if (!incident.incident_id || !Number.isSafeInteger(incident.version) || incident.version < 1) {
    throw new TypeError("A valid incident identity and current version are required.");
  }
  const assignee = options.assignee?.trim();
  if (action === "assign" && (!assignee || assignee.length > 128 || !/^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$/.test(assignee))) {
    throw new TypeError("A valid assignee identifier is required.");
  }
  const payload = await request<{ incident: MadIncident }>(
    apiBaseUrl, "/api/v1/mad/incidents/" + encodeURIComponent(incident.incident_id) + "/transitions",
    accessToken, options.fetcher ?? fetch, "POST",
    { action, expected_version: incident.version, ...(action === "assign" ? { assignee } : {}) },
  );
  return validateIncident(payload.incident);
}
