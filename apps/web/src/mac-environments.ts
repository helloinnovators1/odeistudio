export interface MacEnvironmentRevision {
  version: number;
  status: "draft" | "pending_approval" | "approved" | "promoted";
  config: Record<string, string | number | boolean>;
  created_by: string;
  created_at: string;
  change_summary: string;
  approvals: unknown[];
  rollback_of?: number;
}
export interface MacEnvironmentRecord {
  environment: "development" | "staging" | "production";
  active_version: number;
  latest_version: number;
  versions: MacEnvironmentRevision[];
}
const MAX_RESPONSE_BYTES = 256_000;
type Fetcher = typeof fetch;

function normalizeBase(value: string): string {
  let url: URL;
  try { url = new URL(value); } catch { throw new TypeError("A valid ODEI API base URL is required."); }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if ((url.protocol !== "https:" && !(url.protocol === "http:" && loopback))
    || url.username || url.password || url.search || url.hash) {
    throw new TypeError("MAC API must use HTTPS (or loopback HTTP) without URL credentials or query parameters.");
  }
  return url.toString().replace(/\/+$/, "");
}
async function readBounded(response: Response): Promise<string> {
  const length = Number(response.headers.get("Content-Length"));
  if (Number.isFinite(length) && length > MAX_RESPONSE_BYTES) throw new Error("MAC API returned an oversized response.");
  if (!response.body) {
    const raw = await response.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_RESPONSE_BYTES) throw new Error("MAC API returned an oversized response.");
    return raw;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new Error("MAC API returned an oversized response.");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try { return new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
  catch { throw new Error("MAC API returned an invalid response."); }
}
async function request<T>(
  base: string, environment: string, token: string, fetcher: Fetcher,
  method = "GET", suffix = "", body?: unknown, signal?: AbortSignal,
): Promise<T> {
  if (!/^(development|staging|production)$/.test(environment)) throw new TypeError("Invalid MAC environment.");
  if (!/^[A-Za-z0-9\-._~+/]+=*$/.test(token) || token.length > 8_192) throw new TypeError("A valid in-memory ODID access token is required.");
  const response = await fetcher(
    normalizeBase(base) + "/api/v1/mac/environments/" + environment + suffix,
    {
      method, headers: {
        Accept: "application/json", Authorization: "Bearer " + token,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "omit", cache: "no-store", redirect: "error", signal,
    },
  );
  const raw = await readBounded(response);
  let payload: unknown;
  try { payload = JSON.parse(raw); } catch { throw new Error("MAC API returned an invalid response."); }
  if (!response.ok) {
    const detail = (payload as { detail?: { message?: unknown } | string })?.detail;
    const message = typeof detail === "string" ? detail
      : detail && typeof detail.message === "string" ? detail.message
      : response.status === 403 ? "Your verified ODID identity lacks the required MAC permission."
      : "MAC API request failed with HTTP " + response.status + ".";
    throw new Error(message);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("MAC API returned an invalid response.");
  return payload as T;
}
function versionBody(version: number, latest: number) {
  if (!Number.isSafeInteger(version) || version < 1 || !Number.isSafeInteger(latest) || latest < 1) {
    throw new TypeError("A valid revision and latest version are required.");
  }
  return { version, expected_latest_version: latest };
}
export function getMacEnvironment(base: string, environment: string, token: string, fetcher: Fetcher = fetch, signal?: AbortSignal) {
  return request<{ environment: MacEnvironmentRecord }>(base, environment, token, fetcher, "GET", "", undefined, signal);
}
export function createMacEnvironmentDraft(base: string, environment: string, token: string, config: Record<string, unknown>, changeSummary: string, expectedLatestVersion?: number, fetcher: Fetcher = fetch, signal?: AbortSignal) {
  const body = { config, change_summary: changeSummary, ...(expectedLatestVersion === undefined ? {} : { expected_latest_version: expectedLatestVersion }) };
  return request<{ revision: MacEnvironmentRevision }>(base, environment, token, fetcher, "POST", "/drafts", body, signal);
}
export function updateMacEnvironmentDraft(base: string, environment: string, token: string, version: number, latest: number, config: Record<string, unknown>, changeSummary: string, fetcher: Fetcher = fetch, signal?: AbortSignal) {
  return request<{ environment: MacEnvironmentRecord }>(base, environment, token, fetcher, "PUT", "/drafts/" + version, { ...versionBody(version, latest), config, change_summary: changeSummary }, signal);
}
export function submitMacEnvironment(base: string, environment: string, token: string, version: number, latest: number, fetcher: Fetcher = fetch, signal?: AbortSignal) {
  return request<{ environment: MacEnvironmentRecord }>(base, environment, token, fetcher, "POST", "/submit", versionBody(version, latest), signal);
}
export function approveMacEnvironment(base: string, environment: string, token: string, version: number, latest: number, fetcher: Fetcher = fetch, signal?: AbortSignal) {
  return request<{ environment: MacEnvironmentRecord }>(base, environment, token, fetcher, "POST", "/approve", versionBody(version, latest), signal);
}
export function promoteMacEnvironment(base: string, environment: string, token: string, version: number, latest: number, active: number, fetcher: Fetcher = fetch, signal?: AbortSignal) {
  return request<{ environment: MacEnvironmentRecord }>(base, environment, token, fetcher, "POST", "/promote", { ...versionBody(version, latest), expected_active_version: active }, signal);
}
export function rollbackMacEnvironment(base: string, environment: string, token: string, targetVersion: number, latest: number, changeSummary: string, fetcher: Fetcher = fetch, signal?: AbortSignal) {
  return request<{ revision: MacEnvironmentRevision }>(base, environment, token, fetcher, "POST", "/rollback-drafts", { target_version: targetVersion, expected_latest_version: latest, change_summary: changeSummary }, signal);
}
