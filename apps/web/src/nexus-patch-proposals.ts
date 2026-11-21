import { NexusChatTransportError } from "./nexus-chat";

export type NexusPatchProposalStatus = "pending" | "approved" | "rejected";

export interface NexusPatchProposalSummary {
  proposal_id: string;
  title: string;
  status: NexusPatchProposalStatus;
  version: number;
  file_count: number;
  created_at: string;
  updated_at: string;
}

export interface NexusPatchProposalFile {
  path: string;
  operation: "create" | "update" | "delete";
  base_sha256: string | null;
  result_sha256: string | null;
  content: string | null;
  unified_diff: string;
}

export interface NexusPatchProposal extends NexusPatchProposalSummary {
  files: NexusPatchProposalFile[];
  can_decide: boolean;
  application_enabled: false;
}

export interface NexusPatchProposalList {
  proposals: NexusPatchProposalSummary[];
  limit: 30;
  can_decide: boolean;
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

function validateSummary(value: unknown): NexusPatchProposalSummary {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new NexusChatTransportError("NEXUS returned an invalid patch proposal.", 200);
  }
  const item = value as Record<string, unknown>;
  if (
    typeof item.proposal_id !== "string" || !item.proposal_id ||
    typeof item.title !== "string" ||
    !["pending", "approved", "rejected"].includes(String(item.status)) ||
    typeof item.version !== "number" || !Number.isInteger(item.version) || item.version < 0 ||
    typeof item.file_count !== "number" || !Number.isInteger(item.file_count) || item.file_count < 1 || item.file_count > 20 ||
    typeof item.created_at !== "string" || typeof item.updated_at !== "string"
  ) throw new NexusChatTransportError("NEXUS returned an invalid patch proposal contract.", 200);
  return item as unknown as NexusPatchProposalSummary;
}

function validateDetail(value: unknown): NexusPatchProposal {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new NexusChatTransportError("NEXUS returned an invalid patch proposal detail.", 200);
  }
  const item = value as Record<string, unknown>;
  const summary = validateSummary(item);
  if (
    !Array.isArray(item.files) || item.files.length !== summary.file_count ||
    typeof item.can_decide !== "boolean" || item.application_enabled !== false
  ) throw new NexusChatTransportError("NEXUS returned an invalid patch review contract.", 200);
  const files = item.files.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new NexusChatTransportError("NEXUS returned an invalid patch file.", 200);
    }
    const file = value as Record<string, unknown>;
    if (
      typeof file.path !== "string" || !file.path ||
      !["create", "update", "delete"].includes(String(file.operation)) ||
      !(typeof file.base_sha256 === "string" || file.base_sha256 === null) ||
      !(typeof file.result_sha256 === "string" || file.result_sha256 === null) ||
      !(typeof file.content === "string" || file.content === null) ||
      typeof file.unified_diff !== "string" || file.unified_diff.length > 8_000_000
    ) throw new NexusChatTransportError("NEXUS returned an invalid patch file contract.", 200);
    for (const hash of [file.base_sha256, file.result_sha256]) {
      if (hash !== null && !/^[0-9a-f]{64}$/.test(hash)) {
        throw new NexusChatTransportError("NEXUS returned an invalid patch hash.", 200);
      }
    }
    return file as unknown as NexusPatchProposalFile;
  });
  if (new Set(files.map((file) => file.path.toLocaleLowerCase("en-US"))).size !== files.length) {
    throw new NexusChatTransportError("NEXUS returned duplicate patch paths.", 200);
  }
  return { ...summary, files, can_decide: item.can_decide, application_enabled: false };
}

async function request(
  apiBaseUrl: string,
  organizationId: string,
  projectId: string,
  accessToken: string,
  path: string,
  method: "GET" | "POST",
  body?: unknown,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const token = accessToken.trim();
  if (!token || token.length > 16_384 || /[\r\n]/.test(token)) {
    throw new TypeError("A valid in-memory access token is required.");
  }
  const response = await fetcher(
    `${normalizeBase(apiBaseUrl)}/api/v1/organizations/${encodeURIComponent(organizationId)}/projects/${encodeURIComponent(projectId)}/nexus/patch-proposals${path}`,
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
  if (raw.length > 8_500_000) {
    throw new NexusChatTransportError("NEXUS returned an oversized patch proposal response.", response.status);
  }
  let payload: Record<string, unknown>;
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid");
    payload = parsed as Record<string, unknown>;
  } catch {
    throw new NexusChatTransportError("NEXUS returned invalid patch proposal data.", response.status);
  }
  if (!response.ok) {
    const detail = payload.detail && typeof payload.detail === "object"
      ? payload.detail as Record<string, unknown> : payload;
    const code = typeof detail.code === "string" ? detail.code : undefined;
    const messages: Record<string, string> = {
      PROJECT_OWNER_REQUIRED: "Only the project owner can approve or reject this proposal.",
      PATCH_PROPOSAL_VERSION_CONFLICT: "The proposal changed. Reload it before deciding.",
      PATCH_PROPOSAL_NOT_FOUND: "Patch proposal was not found or is not visible to this identity.",
    };
    throw new NexusChatTransportError(
      messages[code ?? ""] ?? "NEXUS could not complete the patch proposal request.",
      response.status, code,
    );
  }
  return payload;
}

export async function listNexusPatchProposals(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, fetcher: typeof fetch = fetch, signal?: AbortSignal,
): Promise<NexusPatchProposalList> {
  const payload = await request(apiBaseUrl, organizationId, projectId, accessToken, "", "GET", undefined, fetcher, signal);
  if (!Array.isArray(payload.proposals) || payload.proposals.length > 30 ||
      payload.limit !== 30 || typeof payload.can_decide !== "boolean") {
    throw new NexusChatTransportError("NEXUS returned an invalid patch proposal list.", 200);
  }
  const proposals = payload.proposals.map(validateSummary);
  if (new Set(proposals.map((item) => item.proposal_id)).size !== proposals.length) {
    throw new NexusChatTransportError("NEXUS returned duplicate patch proposal IDs.", 200);
  }
  return { proposals, limit: 30, can_decide: payload.can_decide };
}

export async function getNexusPatchProposal(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, proposalId: string, fetcher: typeof fetch = fetch, signal?: AbortSignal,
): Promise<NexusPatchProposal> {
  const id = proposalId.trim();
  if (!id || id.length > 128) throw new TypeError("A valid patch proposal ID is required.");
  const payload = await request(apiBaseUrl, organizationId, projectId, accessToken, "/" + encodeURIComponent(id), "GET", undefined, fetcher, signal);
  return validateDetail(payload);
}

async function decide(
  decision: "approve" | "reject",
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, proposalId: string, expectedVersion: number,
  fetcher: typeof fetch, signal?: AbortSignal,
): Promise<NexusPatchProposalSummary> {
  const id = proposalId.trim();
  if (!id || id.length > 128 || !Number.isInteger(expectedVersion) || expectedVersion < 0) {
    throw new TypeError("A valid proposal ID and version are required.");
  }
  const payload = await request(
    apiBaseUrl, organizationId, projectId, accessToken,
    `/${encodeURIComponent(id)}/${decision}`, "POST",
    { expected_version: expectedVersion }, fetcher, signal,
  );
  if (payload.decision_recorded !== true || payload.application_enabled !== false) {
    throw new NexusChatTransportError("NEXUS returned an invalid proposal decision contract.", 200);
  }
  return validateSummary(payload);
}

export function approveNexusPatchProposal(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, proposalId: string, expectedVersion: number,
  fetcher: typeof fetch = fetch, signal?: AbortSignal,
): Promise<NexusPatchProposalSummary> {
  return decide("approve", apiBaseUrl, organizationId, projectId, accessToken, proposalId, expectedVersion, fetcher, signal);
}

export function rejectNexusPatchProposal(
  apiBaseUrl: string, organizationId: string, projectId: string,
  accessToken: string, proposalId: string, expectedVersion: number,
  fetcher: typeof fetch = fetch, signal?: AbortSignal,
): Promise<NexusPatchProposalSummary> {
  return decide("reject", apiBaseUrl, organizationId, projectId, accessToken, proposalId, expectedVersion, fetcher, signal);
}


export interface NexusPatchApplyCapability {
  capability: string;
  expires_at: number;
  workspace_id: string;
  companion_challenge: string;
  proposal_id: string;
  proposal_version: number;
  patch_sha256: string;
  application_enabled: false;
}

export async function createNexusPatchApplyCapability(
  apiBaseUrl: string,
  organizationId: string,
  projectId: string,
  accessToken: string,
  proposalId: string,
  expectedVersion: number,
  workspaceId: string,
  companionChallenge: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<NexusPatchApplyCapability> {
  const id = proposalId.trim();
  if (
    !id || id.length > 128 || !Number.isInteger(expectedVersion) || expectedVersion < 0 ||
    !workspaceId || workspaceId.length > 128 ||
    !/^[A-Za-z0-9_-]{32,128}$/.test(companionChallenge)
  ) {
    throw new TypeError("A valid approved proposal, selected workspace and fresh companion challenge are required.");
  }
  const payload = await request(
    apiBaseUrl, organizationId, projectId, accessToken,
    "/" + encodeURIComponent(id) + "/apply-capability",
    "POST",
    {
      expected_version: expectedVersion,
      workspace_id: workspaceId,
      companion_challenge: companionChallenge,
      confirm_apply: true,
    },
    fetcher,
    signal,
  );
  if (
    typeof payload.capability !== "string" || !payload.capability ||
    payload.capability.length > 8_192 ||
    typeof payload.expires_at !== "number" || !Number.isSafeInteger(payload.expires_at) ||
    payload.workspace_id !== workspaceId ||
    payload.companion_challenge !== companionChallenge ||
    payload.proposal_id !== id ||
    payload.proposal_version !== expectedVersion ||
    typeof payload.patch_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(payload.patch_sha256) ||
    payload.application_enabled !== false
  ) {
    throw new NexusChatTransportError("NEXUS returned an invalid local apply capability.", 200);
  }
  return payload as unknown as NexusPatchApplyCapability;
}
