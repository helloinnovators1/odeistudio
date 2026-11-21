const BASE=import.meta.env.VITE_COMPANION_ORIGIN||"http://127.0.0.1:8765";
export interface CompanionWorkspace{workspace_id:string;name:string;access:"read-only"}
export interface CompanionFile{path:string;size:number}
interface Pair{access_token:string;token_type:"Bearer";expires_in:number;permissions:string[]}
async function call<T>(path:string,opts:{method?:"GET"|"POST";token?:string;body?:unknown}={}):Promise<T>{const headers=new Headers();if(opts.token)headers.set("Authorization","Bearer "+opts.token);if(opts.body!==undefined)headers.set("Content-Type","application/json");const init={method:opts.method||"GET",headers,body:opts.body===undefined?undefined:JSON.stringify(opts.body),mode:"cors",cache:"no-store",credentials:"omit",redirect:"error",targetAddressSpace:"loopback"} as RequestInit&{targetAddressSpace:"loopback"};const res=await fetch(new Request(BASE+path,init));const body=res.status===204?undefined:await res.json().catch(()=>undefined);if(!res.ok)throw new Error(body&&typeof body.detail==="string"?body.detail:"Companion HTTP "+res.status);return body as T;}
export async function connectToCompanion():Promise<void>{let permissionCheck:Promise<PermissionStatus|null>=Promise.resolve(null);if("permissions"in navigator&&navigator.permissions?.query){try{const query=navigator.permissions.query as unknown as (d:{name:string})=>Promise<PermissionStatus>;permissionCheck=query({name:"loopback-network"}).catch(()=>null);}catch{/* Permission descriptor is not supported in this browser. */}}const healthCheck=call<{status:string}>("/health").then(health=>({health,error:null as unknown}),error=>({health:null,error}));const permission=await permissionCheck;if(permission?.state==="denied")throw new Error("Loopback access is blocked. Allow Local Network Access for this ODEI Studio site in Chrome site settings.");const result=await healthCheck;if(result.error)throw result.error;if(result.health?.status!=="ok")throw new Error("Local companion is not healthy.");}
export function pairWithCompanion(code:string):Promise<Pair>{return call<Pair>("/v1/pair",{method:"POST",body:{code}})}
export async function listWorkspaces(token:string):Promise<CompanionWorkspace[]>{return(await call<{workspaces:CompanionWorkspace[]}>("/v1/workspaces",{token})).workspaces}
export async function listWorkspaceFiles(token:string,id:string):Promise<CompanionFile[]>{return(await call<{files:CompanionFile[]}>("/v1/workspaces/"+encodeURIComponent(id)+"/files",{token})).files}
export async function readWorkspaceFile(token:string,id:string,path:string):Promise<string>{const q=new URLSearchParams({path});return(await call<{content:string}>("/v1/workspaces/"+encodeURIComponent(id)+"/file?"+q.toString(),{token})).content}
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
  if (!globalThis.crypto?.subtle) throw new Error("Secure hashing is unavailable in this browser.");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(content));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
export async function previewWorkspacePatch(
  token: string,
  workspaceId: string,
  changes: Record<string, string | null>,
  baseContents: Record<string, string | null>,
): Promise<PatchPreviewResponse> {
  const paths = Object.keys(changes);
  if (paths.length === 0 || paths.length > 20 || paths.length !== Object.keys(baseContents).length) {
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
      return file.operation === expectedOperation &&
        file.base_sha256 === (base === null ? null : expectedBaseHashes[file.path]) &&
        file.result_sha256 === (replacement === null ? null : /^[0-9a-f]{64}$/.test(file.result_sha256 ?? "")) &&
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
