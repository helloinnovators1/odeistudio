const BASE=import.meta.env.VITE_COMPANION_ORIGIN||"http://127.0.0.1:8765";
export interface CompanionWorkspace{workspace_id:string;name:string;access:"read-only"|"approval-gated"}
export interface CompanionFile{path:string;size:number}
interface Pair{access_token:string;token_type:"Bearer";expires_in:number;permissions:string[]}
async function call<T>(
  path: string,
  opts: { method?: "GET" | "POST"; token?: string; body?: unknown; signal?: AbortSignal } = {},
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const headers = new Headers();
  if (opts.token) headers.set("Authorization", "Bearer " + opts.token);
  if (opts.body !== undefined) headers.set("Content-Type", "application/json");
  const init = {
    method: opts.method || "GET",
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    signal: opts.signal,
    mode: "cors",
    cache: "no-store",
    credentials: "omit",
    redirect: "error",
    targetAddressSpace: "loopback",
  } as RequestInit & { targetAddressSpace: "loopback" };
  const response = await fetcher(new Request(BASE + path, init));
  const body = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body
      ? (body as { detail?: unknown }).detail : undefined;
    if (typeof detail === "string") throw new Error(detail);
    if (detail && typeof detail === "object") {
      const item = detail as { message?: unknown; rollback_failures?: unknown };
      const message = typeof item.message === "string" ? item.message : "Companion HTTP " + response.status;
      const failedPaths = Array.isArray(item.rollback_failures)
        ? item.rollback_failures.filter((value): value is string => typeof value === "string")
        : [];
      throw new Error(failedPaths.length > 0
        ? message + " Recovery is required for: " + failedPaths.join(", ")
        : message);
    }
    throw new Error("Companion HTTP " + response.status);
  }
  return body as T;
}
export async function connectToCompanion():Promise<void>{let permissionCheck:Promise<PermissionStatus|null>=Promise.resolve(null);if("permissions"in navigator&&navigator.permissions?.query){try{const query=navigator.permissions.query as unknown as (d:{name:string})=>Promise<PermissionStatus>;permissionCheck=query({name:"loopback-network"}).catch(()=>null);}catch{/* Permission descriptor is not supported in this browser. */}}const healthCheck=call<{status:string}>("/health").then(health=>({health,error:null as unknown}),error=>({health:null,error}));const permission=await permissionCheck;if(permission?.state==="denied")throw new Error("Loopback access is blocked. Allow Local Network Access for this ODEI Studio site in Chrome site settings.");const result=await healthCheck;if(result.error)throw result.error;if(result.health?.status!=="ok")throw new Error("Local companion is not healthy.");}
export async function pairWithCompanion(code:string):Promise<Pair>{
  const result=await call<Pair>("/v1/pair",{method:"POST",body:{code}});
  if(!result||typeof result.access_token!=="string"||!result.access_token||
    result.token_type!=="Bearer"||!Number.isInteger(result.expires_in)||
    result.expires_in<1||result.expires_in>86_400||
    !Array.isArray(result.permissions)||!result.permissions.includes("workspace:read")||
    result.permissions.some((permission)=>!["workspace:read","patch:apply"].includes(permission))){
    throw new Error("Companion returned an invalid pairing permission contract.");
  }
  return result;
}
export async function listWorkspaces(token:string):Promise<CompanionWorkspace[]>{return(await call<{workspaces:CompanionWorkspace[]}>("/v1/workspaces",{token})).workspaces}
export async function listWorkspaceFiles(token:string,id:string):Promise<CompanionFile[]>{return(await call<{files:CompanionFile[]}>("/v1/workspaces/"+encodeURIComponent(id)+"/files",{token})).files}
export async function readWorkspaceFile(token:string,id:string,path:string,signal?:AbortSignal):Promise<string>{const q=new URLSearchParams({path});return(await call<{content:string}>("/v1/workspaces/"+encodeURIComponent(id)+"/file?"+q.toString(),{token,signal})).content}
export async function disconnectFromCompanion(token:string):Promise<void>{await call<void>("/v1/session/revoke",{method:"POST",token})}

export interface PatchPreviewFile {
  path: string;
  operation: "create" | "update" | "delete";
  base_sha256: string | null;
  result_sha256: string | null;
  content: string | null;
  unified_diff: string;
}
export interface PatchPreviewResponse {
  workspace_id: string;
  mode: "preview_only";
  writes_performed: false;
  files: PatchPreviewFile[];
  total_content_bytes: number;
  total_diff_bytes: number;
}
async function sha256Text(content: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("Secure hashing is unavailable in this browser.");
  }
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256", new TextEncoder().encode(content),
  );
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
export async function previewWorkspacePatch(
  token: string,
  workspaceId: string,
  changes: Record<string, string | null>,
  baseContents: Record<string, string | null>,
): Promise<PatchPreviewResponse> {
  const paths = Object.keys(changes);
  if (
    paths.length === 0 ||
    paths.length > 20 ||
    paths.length !== Object.keys(baseContents).length
  ) {
    throw new Error("Patch preview requires matching base content for 1–20 changed files.");
  }
  const expectedBaseHashes = Object.create(null) as Record<string, string | null>;
  for (const path of paths) {
    if (!Object.prototype.hasOwnProperty.call(baseContents, path)) {
      throw new Error("Patch preview is missing a base snapshot for a changed path.");
    }
    const base = baseContents[path];
    expectedBaseHashes[path] = base === null ? null : await sha256Text(base);
  }
  const response = await call<PatchPreviewResponse>(
    "/v1/workspaces/" + encodeURIComponent(workspaceId) + "/patch-proposals",
    { method: "POST", token, body: { changes, expected_base_hashes: expectedBaseHashes } },
  );
  if (!response || typeof response !== "object") {
    throw new Error("Companion returned an invalid patch preview response.");
  }
  const responsePaths = Array.isArray(response.files)
    ? response.files.map((file) => file?.path)
    : [];
  const uniqueResponsePaths = new Set(responsePaths);
  const filesAreValid = Array.isArray(response.files) &&
    response.files.length === paths.length &&
    uniqueResponsePaths.size === paths.length &&
    response.files.every((file) => {
      if (!file || typeof file !== "object" || !paths.includes(file.path)) return false;
      const base = baseContents[file.path];
      const replacement = changes[file.path];
      const expectedOperation = base === null ? "create" : replacement === null ? "delete" : "update";
      const resultHashIsValid = replacement === null
        ? file.result_sha256 === null
        : typeof file.result_sha256 === "string" && /^[0-9a-f]{64}$/.test(file.result_sha256);
      return file.operation === expectedOperation &&
        file.base_sha256 === (base === null ? null : expectedBaseHashes[file.path]) &&
        resultHashIsValid &&
        file.content === replacement &&
        typeof file.unified_diff === "string";
    });
  if (
    response.workspace_id !== workspaceId ||
    response.mode !== "preview_only" ||
    response.writes_performed !== false ||
    !filesAreValid ||
    !Number.isSafeInteger(response.total_content_bytes) ||
    response.total_content_bytes < 0 ||
    !Number.isSafeInteger(response.total_diff_bytes) ||
    response.total_diff_bytes < 0
  ) {
    throw new Error("Companion returned an invalid patch preview response.");
  }
  return response;
}


export interface CompanionApplyChallenge {
  workspace_id: string;
  challenge: string;
  expires_in: number;
}

export interface CompanionApplyResult {
  workspace_id: string;
  proposal_id: string;
  proposal_version: number;
  applied: true;
  transaction_semantics: "per-file-atomic-with-compensating-rollback";
  rollback_required: false;
  files: Array<{
    path: string;
    operation: "create" | "update" | "delete";
    result_sha256: string;
    applied: true;
    durability_confirmed: boolean;
  }>;
}

export async function createWorkspaceApplyChallenge(
  token: string,
  workspaceId: string,
  fetcher: typeof fetch = fetch,
): Promise<CompanionApplyChallenge> {
  const id = workspaceId.trim();
  if (!id || id.length > 128) throw new TypeError("A valid selected workspace is required.");
  const result = await call<CompanionApplyChallenge>(
    "/v1/workspaces/" + encodeURIComponent(id) + "/apply-challenge",
    { method: "POST", token },
    fetcher,
  );
  if (
    result.workspace_id !== id ||
    typeof result.challenge !== "string" ||
    !/^[A-Za-z0-9_-]{32,128}$/.test(result.challenge) ||
    !Number.isInteger(result.expires_in) || result.expires_in < 1 || result.expires_in > 120
  ) {
    throw new Error("Companion returned an invalid apply challenge.");
  }
  return result;
}

export async function applyApprovedWorkspacePatch(
  token: string,
  workspaceId: string,
  request: {
    organizationId: string;
    projectId: string;
    proposalId: string;
    proposalVersion: number;
    challenge: string;
    capability: string;
    files: PatchPreviewFile[];
  },
  fetcher: typeof fetch = fetch,
): Promise<CompanionApplyResult> {
  const id = workspaceId.trim();
  if (!id || id.length > 128 || !request.organizationId || !request.projectId ||
      !request.proposalId || !Number.isInteger(request.proposalVersion) ||
      request.proposalVersion < 0 || !/^[A-Za-z0-9_-]{32,128}$/.test(request.challenge) ||
      !request.capability || request.capability.length > 8_192 ||
      !Array.isArray(request.files) || request.files.length < 1 || request.files.length > 20) {
    throw new TypeError("A valid approved patch capability, selected workspace and bounded file batch are required.");
  }
  let totalBytes = 0;
  for (const file of request.files) {
    if (
      !file || !["create", "update", "delete"].includes(file.operation) ||
      typeof file.path !== "string" || !file.path ||
      (file.content !== null && typeof file.content !== "string") ||
      (file.base_sha256 !== null && !/^[0-9a-f]{64}$/.test(file.base_sha256)) ||
      (file.result_sha256 !== null && !/^[0-9a-f]{64}$/.test(file.result_sha256))
    ) {
      throw new TypeError("An approved patch file is invalid.");
    }
    totalBytes += file.content === null ? 0 : new TextEncoder().encode(file.content).byteLength;
  }
  const paths = request.files.map((file) => file.path.toLocaleLowerCase("en-US"));
  if (new Set(paths).size !== paths.length) {
    throw new TypeError("The approved patch batch contains duplicate paths.");
  }
  if (totalBytes > 5 * 1024 * 1024) {
    throw new TypeError("The approved patch batch exceeds the aggregate content limit.");
  }
  const result = await call<CompanionApplyResult>(
    "/v1/workspaces/" + encodeURIComponent(id) + "/apply-patch",
    {
      method: "POST",
      token,
      body: {
        organization_id: request.organizationId,
        project_id: request.projectId,
        proposal_id: request.proposalId,
        proposal_version: request.proposalVersion,
        companion_challenge: request.challenge,
        capability: request.capability,
        files: request.files.map((file) => ({
          path: file.path,
          operation: file.operation,
          base_sha256: file.base_sha256,
          result_sha256: file.result_sha256,
          content: file.content,
        })),
      },
    },
    fetcher,
  );
  if (
    result.workspace_id !== id ||
    result.proposal_id !== request.proposalId ||
    result.proposal_version !== request.proposalVersion ||
    result.applied !== true ||
    result.transaction_semantics !== "per-file-atomic-with-compensating-rollback" ||
    result.rollback_required !== false ||
    !Array.isArray(result.files) || result.files.length !== request.files.length ||
    result.files.some((file, index) => {
      const expected = request.files[index];
      return !expected ||
        file.path !== expected.path ||
        file.operation !== expected.operation ||
        file.result_sha256 !== (expected.result_sha256 ?? "") ||
        file.applied !== true ||
        typeof file.durability_confirmed !== "boolean";
    })
  ) {
    throw new Error("Companion returned an invalid multi-file patch application result.");
  }
  return result;
}
