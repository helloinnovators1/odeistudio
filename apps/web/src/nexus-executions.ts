export type NexusExecutionStatus =
  | "queued" | "leased" | "running" | "collecting"
  | "completed" | "failed" | "cancelled" | "expired";

export interface NexusExecutionProfile { profile_id: string; }
export interface NexusExecutionSnapshot {
  snapshot_id: string; organization_id: string; project_id: string; task_id: string;
  sha256: string; file_count: number; total_bytes: number; archive_bytes: number;
  created_at: string; expires_at: string;
}
export interface NexusRepositoryReview {
  repository_id: number; repository_node_id: string; owner: string; name: string;
  default_branch: string; base_sha: string; binding_version: number;
  commit_sha: string | null; tree_sha: string | null; branch: string | null;
  pull_request_number: number | null; pull_request_url: string | null;
  provenance_at: string | null;
}
export interface NexusExecutionRun {
  run_id: string; organization_id: string; project_id: string; task_id: string;
  profile_id: string; snapshot_sha256: string; status: NexusExecutionStatus;
  version: number; attempts: number; max_attempts: number; cancel_requested: boolean;
  created_at: string | null; updated_at: string | null;
  repository_review?: NexusRepositoryReview | null;
}
export interface NexusExecutionCreateResponse {
  run_id: string; status: "queued"; task_id: string; profile_id: string;
  snapshot: NexusExecutionSnapshot;
  repository_binding_version?: number | null;
  repository_base_sha?: string | null;
  repository_publish_consent?: boolean;
}
export interface NexusExecutionEvent {
  event_id: string; type: string; version: number; occurred_at: string;
  from_status?: string; to_status?: string;
}
export interface NexusExecutionHistoryCursor {
  before_created_at: string;
  before_run_id: string;
}
export interface NexusExecutionHistoryPage {
  runs: NexusExecutionRun[];
  has_more: boolean;
  next_cursor: NexusExecutionHistoryCursor | null;
}
export interface NexusExecutionEventsPage {
  events: NexusExecutionEvent[]; has_more: boolean; next_after_version: number;
}
export interface NexusExecutionDiagnostics {
  run_id: string;
  category: "succeeded" | "failed" | "timed_out";
  summary: string;
  exit_code: number;
  duration_ms: number;
  timed_out: boolean;
  signals: string[];
  evidence: string[];
  next_step: string;
}
export interface NexusExecutionArtifacts {
  artifact_id: string; run_id: string; exit_code: number; duration_ms: number;
  timed_out: boolean; stdout_truncated: boolean; stderr_truncated: boolean;
  stdout_bytes: number; stderr_bytes: number; created_at: string;
  stdout: string; stderr: string;
}

type Fetcher = typeof fetch;

function normalizeBase(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new TypeError("A valid NEXUS API base URL is required.");
  }
  const localHttp = url.protocol === "http:"
    && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if ((url.protocol !== "https:" && !localHttp)
    || url.username || url.password || url.search || url.hash) {
    throw new TypeError("NEXUS API must use HTTPS (or loopback HTTP) without URL credentials or query parameters.");
  }
  return url.toString().replace(/\/+$/, "");
}

function route(baseUrl: string, organizationId: string, projectId: string, taskId?: string): string {
  const base = normalizeBase(baseUrl);
  const root = base + "/api/v1/organizations/" + encodeURIComponent(organizationId)
    + "/projects/" + encodeURIComponent(projectId);
  return taskId ? root + "/tasks/" + encodeURIComponent(taskId) + "/executions" : root + "/execution";
}

async function request<T>(
  url: string,
  accessToken: string,
  options: { method?: "GET" | "POST"; body?: unknown; signal?: AbortSignal; fetcher?: Fetcher } = {},
): Promise<T> {
  const headers = new Headers({ Accept: "application/json", Authorization: "Bearer " + accessToken });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await (options.fetcher ?? fetch)(url, {
    method: options.method ?? "GET", headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal, credentials: "omit", cache: "no-store", redirect: "error",
  });
  const payload = await response.json().catch(() => undefined) as
    | { detail?: string | { code?: string; message?: string } } | undefined;
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail
      : detail && typeof detail.message === "string" ? detail.message
        : "Execution API returned HTTP " + response.status + ".";
    throw new Error(message);
  }
  if (!payload || typeof payload !== "object") throw new Error("Execution API returned an invalid response.");
  return payload as T;
}

export async function listNexusProjectExecutions(
  baseUrl: string, organizationId: string, projectId: string, accessToken: string,
  options: {
    limit?: number; cursor?: NexusExecutionHistoryCursor | null;
    fetcher?: Fetcher; signal?: AbortSignal;
  } = {},
): Promise<NexusExecutionHistoryPage> {
  const limit = options.limit ?? 50;
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new RangeError("Execution history page size must be between 1 and 100.");
  }
  const query = new URLSearchParams({ limit: String(limit) });
  if (options.cursor) {
    if (!options.cursor.before_created_at || !options.cursor.before_run_id) {
      throw new TypeError("Execution history cursor is incomplete.");
    }
    query.set("before_created_at", options.cursor.before_created_at);
    query.set("before_run_id", options.cursor.before_run_id);
  }
  const base = normalizeBase(baseUrl);
  const projectUrl = base + "/api/v1/organizations/" + encodeURIComponent(organizationId)
    + "/projects/" + encodeURIComponent(projectId) + "/executions?" + query.toString();
  const response = await request<NexusExecutionHistoryPage>(
    projectUrl, accessToken, { fetcher: options.fetcher, signal: options.signal },
  );
  if (!Array.isArray(response.runs) || typeof response.has_more !== "boolean"
    || !(response.next_cursor === null || (
      typeof response.next_cursor === "object"
      && typeof response.next_cursor.before_created_at === "string"
      && typeof response.next_cursor.before_run_id === "string"
    ))
    || response.runs.some((run) => !run || typeof run.run_id !== "string"
      || typeof run.task_id !== "string" || typeof run.status !== "string")) {
    throw new Error("Execution API returned an invalid project history response.");
  }
  return response;
}

export async function listNexusExecutionProfiles(
  baseUrl: string, organizationId: string, projectId: string, accessToken: string,
  fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<NexusExecutionProfile[]> {
  const response = await request<{ profiles: NexusExecutionProfile[] }>(
    route(baseUrl, organizationId, projectId) + "/profiles", accessToken, { fetcher, signal },
  );
  if (!Array.isArray(response.profiles)
    || response.profiles.some((profile) => !profile || typeof profile.profile_id !== "string")) {
    throw new Error("Execution API returned an invalid profile list.");
  }
  return response.profiles;
}

export async function createNexusExecution(
  baseUrl: string, organizationId: string, projectId: string, taskId: string,
  accessToken: string,
  values: { profileId: string; expectedTaskVersion: number; snapshotZipBase64: string; repositoryPublishConsent?: boolean },
  fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<NexusExecutionCreateResponse> {
  const response = await request<NexusExecutionCreateResponse>(
    route(baseUrl, organizationId, projectId, taskId), accessToken,
    { method: "POST", fetcher, signal, body: {
      profile_id: values.profileId,
      mode: "agent",
      expected_task_version: values.expectedTaskVersion,
      workspace_upload_consent: true,
      execution_consent: true,
      repository_publish_consent: values.repositoryPublishConsent === true,
      snapshot_zip_base64: values.snapshotZipBase64,
    } },
  );
  if (response.status !== "queued" || typeof response.run_id !== "string"
    || response.task_id !== taskId || response.snapshot?.sha256 == null) {
    throw new Error("Execution API returned an invalid run creation response.");
  }
  return response;
}

export async function getNexusExecution(
  baseUrl: string, organizationId: string, projectId: string, taskId: string,
  runId: string, accessToken: string, fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<NexusExecutionRun> {
  return request<NexusExecutionRun>(
    route(baseUrl, organizationId, projectId, taskId) + "/" + encodeURIComponent(runId),
    accessToken, { fetcher, signal },
  );
}

export async function cancelNexusExecution(
  baseUrl: string, organizationId: string, projectId: string, taskId: string,
  runId: string, accessToken: string, fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<NexusExecutionRun> {
  return request<NexusExecutionRun>(
    route(baseUrl, organizationId, projectId, taskId) + "/" + encodeURIComponent(runId) + "/cancel",
    accessToken, { method: "POST", fetcher, signal },
  );
}

export async function listNexusExecutionEvents(
  baseUrl: string, organizationId: string, projectId: string, taskId: string,
  runId: string, accessToken: string, afterVersion = -1,
  fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<NexusExecutionEventsPage> {
  const query = new URLSearchParams({ after_version: String(afterVersion), limit: "100" });
  return request<NexusExecutionEventsPage>(
    route(baseUrl, organizationId, projectId, taskId) + "/" + encodeURIComponent(runId)
      + "/events?" + query.toString(),
    accessToken, { fetcher, signal },
  );
}

export async function getNexusExecutionArtifacts(
  baseUrl: string, organizationId: string, projectId: string, taskId: string,
  runId: string, accessToken: string, fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<NexusExecutionArtifacts> {
  return request<NexusExecutionArtifacts>(
    route(baseUrl, organizationId, projectId, taskId) + "/" + encodeURIComponent(runId) + "/artifacts",
    accessToken, { fetcher, signal },
  );
}


export async function getNexusExecutionDiagnostics(
  baseUrl: string, organizationId: string, projectId: string, taskId: string,
  runId: string, accessToken: string, fetcher: Fetcher = fetch, signal?: AbortSignal,
): Promise<NexusExecutionDiagnostics> {
  const result = await request<NexusExecutionDiagnostics>(
    route(baseUrl, organizationId, projectId, taskId) + "/" + encodeURIComponent(runId) + "/diagnostics",
    accessToken, { fetcher, signal },
  );
  if (result.run_id !== runId ||
    !["succeeded", "failed", "timed_out"].includes(result.category) ||
    typeof result.summary !== "string" || !Number.isInteger(result.exit_code) ||
    !Number.isInteger(result.duration_ms) || typeof result.timed_out !== "boolean" ||
    !Array.isArray(result.signals) || result.signals.length > 8 ||
    result.signals.some((item) => typeof item !== "string") ||
    !Array.isArray(result.evidence) || result.evidence.length > 8 ||
    result.evidence.some((item) => typeof item !== "string" || item.length > 240) ||
    typeof result.next_step !== "string") {
    throw new Error("Execution API returned an invalid diagnostics response.");
  }
  return result;
}
