export interface NexusOrganization {
  organization_id: string;
  role: string;
}

export interface NexusOrganizationList {
  organizations: NexusOrganization[];
  limit: number;
}

export interface NexusProjectOwner {
  issuer: string;
  subject: string;
}

export interface NexusProject {
  project_id: string;
  organization_id: string;
  name: string;
  description: string;
  status: "active";
  owner: NexusProjectOwner;
  created_at: string;
  updated_at: string;
}

export interface NexusProjectList {
  projects: NexusProject[];
  limit: number;
}

export interface NexusProjectCreate {
  name: string;
  description?: string;
}

export class NexusProjectTransportError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = "NexusProjectTransportError";
  }
}

const MAX_RESPONSE_CHARS = 128_000;

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

function identifier(value: string, label: string): string {
  const clean = value.trim();
  if (!clean || clean.length > 128) {
    throw new TypeError(`${label} must contain 1 to 128 characters.`);
  }
  return clean;
}

function bearer(value: string): string {
  const token = value.trim();
  if (!token || token.length > 16_384 || /[\r\n]/.test(token)) {
    throw new TypeError("A valid in-memory access token is required.");
  }
  return token;
}

function parseObject(raw: string, status: number): Record<string, unknown> {
  if (raw.length > MAX_RESPONSE_CHARS) {
    throw new NexusProjectTransportError("NEXUS returned an oversized project response.", status);
  }
  try {
    const value: unknown = JSON.parse(raw);
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  } catch {
    // Return one stable transport error without exposing provider response bodies.
  }
  throw new NexusProjectTransportError("NEXUS returned an invalid project response.", status);
}

function safeError(payload: Record<string, unknown>, status: number): NexusProjectTransportError {
  const detail = payload.detail;
  const detailObject = detail && typeof detail === "object" && !Array.isArray(detail)
    ? detail as Record<string, unknown>
    : {};
  const code = typeof detailObject.code === "string"
    ? detailObject.code
    : typeof payload.code === "string" ? payload.code : undefined;
  const messages: Record<string, string> = {
    AUTH_NOT_CONFIGURED: "Trusted identity is not configured for this environment.",
    AUTH_REQUIRED: "Sign in before accessing projects.",
    INVALID_ACCESS_TOKEN: "Your sign-in has expired or is invalid. Sign in again.",
    CLIENT_NOT_ALLOWED: "This application is not an approved identity client.",
    ORGANIZATION_ACCESS_DENIED: "You do not have active access to this organization.",
    PROJECT_STORE_UNAVAILABLE: "Project storage is temporarily unavailable.",
    MEMBERSHIP_STORE_UNAVAILABLE: "Organization membership is temporarily unavailable.",
    AUDIT_STORE_UNAVAILABLE: "Authorization audit storage is temporarily unavailable.",
  };
  return new NexusProjectTransportError(
    messages[code ?? ""] ?? "NEXUS could not complete the project request.",
    status,
    code,
  );
}

function isProject(value: unknown, organizationId: string): value is NexusProject {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const project = value as Record<string, unknown>;
  const owner = project.owner;
  return typeof project.project_id === "string" && project.project_id.length > 0 &&
    project.project_id.length <= 128 &&
    project.organization_id === organizationId &&
    typeof project.name === "string" && project.name.length > 0 &&
    typeof project.description === "string" &&
    project.status === "active" &&
    typeof project.created_at === "string" &&
    typeof project.updated_at === "string" &&
    !!owner && typeof owner === "object" && !Array.isArray(owner) &&
    typeof (owner as Record<string, unknown>).issuer === "string" &&
    typeof (owner as Record<string, unknown>).subject === "string";
}

async function request(
  apiBaseUrl: string,
  organizationId: string,
  accessToken: string,
  method: "GET" | "POST",
  body: NexusProjectCreate | undefined,
  fetcher: typeof fetch,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const response = await fetcher(
    `${normalizeApiBaseUrl(apiBaseUrl)}/api/v1/organizations/${encodeURIComponent(organizationId)}/projects`,
    {
      method,
      headers: {
        Authorization: `Bearer ${bearer(accessToken)}`,
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal,
    },
  );
  const payload = parseObject(await response.text(), response.status);
  if (!response.ok) throw safeError(payload, response.status);
  return payload;
}

/** List only organizations where the authenticated identity has an active server-side membership. */
export async function listNexusOrganizations(
  apiBaseUrl: string,
  accessToken: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<NexusOrganizationList> {
  const response = await fetcher(
    `${normalizeApiBaseUrl(apiBaseUrl)}/api/v1/organizations`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${bearer(accessToken)}`,
        Accept: "application/json",
      },
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal,
    },
  );
  const payload = parseObject(await response.text(), response.status);
  if (!response.ok) throw safeError(payload, response.status);
  if (
    !Array.isArray(payload.organizations)
    || payload.organizations.length > 100
    || payload.limit !== 100
    || !payload.organizations.every((value) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) return false;
      const organization = value as Record<string, unknown>;
      return typeof organization.organization_id === "string"
        && organization.organization_id.length > 0
        && organization.organization_id.length <= 128
        && organization.organization_id.trim() === organization.organization_id
        && typeof organization.role === "string"
        && organization.role.length > 0
        && organization.role.length <= 128;
    })
  ) {
    throw new NexusProjectTransportError("NEXUS returned an unexpected organization-list contract.", 200);
  }
  const ids = payload.organizations.map((value) =>
    (value as NexusOrganization).organization_id
  );
  if (new Set(ids).size !== ids.length) {
    throw new NexusProjectTransportError("NEXUS returned duplicate organization identities.", 200);
  }
  return payload as unknown as NexusOrganizationList;
}

/** List only projects the authenticated identity may access in this organization. */
export async function listNexusProjects(
  apiBaseUrl: string,
  organizationId: string,
  accessToken: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<NexusProjectList> {
  const org = identifier(organizationId, "Organization ID");
  const payload = await request(apiBaseUrl, org, accessToken, "GET", undefined, fetcher, signal);
  if (
    !Array.isArray(payload.projects) ||
    payload.projects.length > 100 ||
    !Number.isSafeInteger(payload.limit) ||
    payload.limit !== 100 ||
    !payload.projects.every((project) => isProject(project, org))
  ) {
    throw new NexusProjectTransportError("NEXUS returned an unexpected project-list contract.", 200);
  }
  const ids = payload.projects.map((project) => (project as NexusProject).project_id);
  if (new Set(ids).size !== ids.length) {
    throw new NexusProjectTransportError("NEXUS returned duplicate project identities.", 200);
  }
  return payload as unknown as NexusProjectList;
}

/** Create a project for the authenticated active organization member. */
export async function createNexusProject(
  apiBaseUrl: string,
  organizationId: string,
  accessToken: string,
  input: NexusProjectCreate,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<NexusProject> {
  const org = identifier(organizationId, "Organization ID");
  if (!input || typeof input.name !== "string" || !input.name.trim() ||
      input.name.trim().length > 120 ||
      (input.description !== undefined &&
        (typeof input.description !== "string" || input.description.length > 2_000))) {
    throw new TypeError("Project name must contain 1 to 120 characters and description at most 2,000.");
  }
  const payload = await request(
    apiBaseUrl, org, accessToken, "POST",
    { name: input.name.trim(), description: input.description?.trim() ?? "" },
    fetcher, signal,
  );
  if (!isProject(payload, org)) {
    throw new NexusProjectTransportError("NEXUS returned an unexpected project-creation contract.", 201);
  }
  return payload;
}
