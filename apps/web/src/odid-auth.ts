/**
 * Provider-neutral OAuth 2.0 Authorization Code + PKCE client for ODID.
 *
 * Access tokens are returned to the caller and are never persisted here.
 * Only the short-lived PKCE transaction (state + verifier) is kept in
 * sessionStorage so a full-page authorization redirect can be completed.
 */
export interface ODidOAuthConfig {
  issuer: string;
  clientId: string;
  redirectUri: string;
  resource: string;
  scopes: string[];
}

export interface ODidAccessToken {
  accessToken: string;
  expiresAt: number;
  scope?: string;
  /** Optional rotating refresh token; held in application memory only. */
  refreshToken?: string;
}

interface LoginTransaction {
  state: string;
  verifier: string;
  issuer: string;
  clientId: string;
  redirectUri: string;
  resource: string;
  createdAt: number;
}

type TransactionStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
type Fetcher = typeof fetch;

const TRANSACTION_KEY = "odei.odid.pkce.transaction.v1";
const TRANSACTION_TTL_MS = 10 * 60 * 1_000;
const MAX_DISCOVERY_BYTES = 32_000;
const MAX_TOKEN_RESPONSE_BYTES = 16_000;
const MAX_ACCESS_TOKEN_CHARS = 8_192;
const MAX_REFRESH_TOKEN_CHARS = 8_192;
const MAX_TOKEN_LIFETIME_SECONDS = 86_400;

export class ODidOAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ODidOAuthError";
  }
}

function parseHttpsUrl(value: string, label: string, allowLoopbackHttp = false): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new ODidOAuthError(`${label} must be a valid absolute URL.`);
  }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.protocol !== "https:" && !(allowLoopbackHttp && loopback && url.protocol === "http:")) {
    throw new ODidOAuthError(`${label} must use HTTPS (HTTP is allowed only for loopback development).`);
  }
  if (url.username || url.password || url.hash) {
    throw new ODidOAuthError(`${label} must not contain credentials or a fragment.`);
  }
  return url;
}

function validateConfig(config: ODidOAuthConfig): ODidOAuthConfig {
  if (!config || typeof config !== "object") throw new ODidOAuthError("ODID OAuth configuration is missing.");
  if (
    typeof config.issuer !== "string" || !config.issuer || config.issuer.trim() !== config.issuer
    || typeof config.redirectUri !== "string" || !config.redirectUri
    || config.redirectUri.trim() !== config.redirectUri
    || typeof config.resource !== "string" || !config.resource
    || config.resource.trim() !== config.resource
  ) {
    throw new ODidOAuthError("ODID issuer, redirect URI and API resource must be exact configured URLs.");
  }
  const issuerUrl = parseHttpsUrl(config.issuer, "ODID issuer");
  if (issuerUrl.search) throw new ODidOAuthError("ODID issuer must not contain a query.");
  const redirect = parseHttpsUrl(config.redirectUri, "Registered redirect URI", true);
  if (redirect.search) throw new ODidOAuthError("Registered redirect URI must not contain a query.");
  parseHttpsUrl(config.resource, "API resource");
  if (typeof config.clientId !== "string" || !config.clientId.trim() || config.clientId.length > 256) {
    throw new ODidOAuthError("ODID public client ID is invalid.");
  }
  if (!Array.isArray(config.scopes) || config.scopes.length < 1 || config.scopes.length > 20
    || config.scopes.some((scope) => typeof scope !== "string" || !/^[\x21\x23-\x5B\x5D-\x7E]{1,128}$/.test(scope))) {
    throw new ODidOAuthError("ODID scopes must be a bounded list of valid scope names.");
  }
  return {
    issuer: config.issuer,
    clientId: config.clientId.trim(),
    redirectUri: config.redirectUri,
    resource: config.resource,
    scopes: [...new Set(config.scopes)],
  };
}

function discoveryUrl(issuer: string): string {
  const url = new URL(issuer);
  const path = url.pathname.replace(/\/$/, "");
  url.pathname = `${path}/.well-known/openid-configuration`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

function endpoint(value: unknown, label: string): string {
  if (typeof value !== "string") throw new ODidOAuthError(`ODID discovery is missing its ${label}.`);
  return parseHttpsUrl(value, `ODID ${label}`).toString();
}

function validRefreshToken(value: unknown): value is string {
  return typeof value === "string" && value.length <= MAX_REFRESH_TOKEN_CHARS
    && /^[\x21-\x7E]+$/.test(value);
}

async function readJson(response: Response, maximum: number, label: string): Promise<Record<string, unknown>> {
  const declaredLength = Number(response.headers.get("Content-Length"));
  if (Number.isFinite(declaredLength) && declaredLength > maximum) {
    throw new ODidOAuthError(`ODID ${label} response is oversized.`);
  }
  let text: string;
  if (response.body) {
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let totalBytes = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        totalBytes += value.byteLength;
        if (totalBytes > maximum) {
          await reader.cancel();
          throw new ODidOAuthError(`ODID ${label} response is oversized.`);
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    const bytes = new Uint8Array(totalBytes);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      throw new ODidOAuthError(`ODID ${label} response is invalid.`);
    }
  } else {
    text = await response.text();
    if (new TextEncoder().encode(text).byteLength > maximum) {
      throw new ODidOAuthError(`ODID ${label} response is oversized.`);
    }
  }
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new ODidOAuthError(`ODID ${label} response is invalid.`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ODidOAuthError(`ODID ${label} response is invalid.`);
  }
  return value as Record<string, unknown>;
}

async function discover(
  config: ODidOAuthConfig,
  fetcher: Fetcher,
): Promise<{ authorizationEndpoint: string; tokenEndpoint: string; revocationEndpoint?: string }> {
  let response: Response;
  try {
    response = await fetcher(discoveryUrl(config.issuer), {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ODidOAuthError("ODID discovery could not be reached securely.");
  }
  if (!response.ok) throw new ODidOAuthError("ODID discovery is unavailable.");
  const metadata = await readJson(response, MAX_DISCOVERY_BYTES, "discovery");
  if (metadata.issuer !== config.issuer) {
    throw new ODidOAuthError("ODID discovery issuer does not match the configured issuer.");
  }
  const methods = metadata.code_challenge_methods_supported;
  if (!Array.isArray(methods) || !methods.includes("S256")) {
    throw new ODidOAuthError("ODID must advertise PKCE S256 support.");
  }
  return {
    authorizationEndpoint: endpoint(metadata.authorization_endpoint, "authorization endpoint"),
    tokenEndpoint: endpoint(metadata.token_endpoint, "token endpoint"),
    ...(metadata.revocation_endpoint === undefined
      ? {}
      : { revocationEndpoint: endpoint(metadata.revocation_endpoint, "revocation endpoint") }),
  };
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function randomValue(cryptoProvider: Crypto, length: number): string {
  const bytes = new Uint8Array(length);
  cryptoProvider.getRandomValues(bytes);
  return base64Url(bytes);
}

async function sha256(value: string, cryptoProvider: Crypto): Promise<string> {
  const digest = await cryptoProvider.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return base64Url(new Uint8Array(digest));
}

function browserSessionStorage(): TransactionStorage | undefined {
  try {
    return typeof window !== "undefined" ? window.sessionStorage : undefined;
  } catch {
    return undefined;
  }
}

function storageOrThrow(storage: TransactionStorage | undefined): TransactionStorage {
  if (!storage) throw new ODidOAuthError("Secure session storage is unavailable.");
  return storage;
}

export async function beginODIDLogin(
  rawConfig: ODidOAuthConfig,
  options: {
    storage?: TransactionStorage;
    cryptoProvider?: Crypto;
    fetcher?: Fetcher;
    now?: number;
  } = {},
): Promise<string> {
  const config = validateConfig(rawConfig);
  const storage = storageOrThrow(options.storage ?? browserSessionStorage());
  const cryptoProvider = options.cryptoProvider ?? (typeof window !== "undefined" ? window.crypto : undefined);
  if (!cryptoProvider?.subtle || !cryptoProvider.getRandomValues) {
    throw new ODidOAuthError("Web Crypto is required for secure PKCE login.");
  }
  const metadata = await discover(config, options.fetcher ?? fetch);
  const state = randomValue(cryptoProvider, 32);
  const verifier = randomValue(cryptoProvider, 32);
  const challenge = await sha256(verifier, cryptoProvider);
  const transaction: LoginTransaction = {
    state,
    verifier,
    issuer: config.issuer,
    clientId: config.clientId,
    redirectUri: config.redirectUri,
    resource: config.resource,
    createdAt: options.now ?? Date.now(),
  };
  try {
    storage.setItem(TRANSACTION_KEY, JSON.stringify(transaction));
  } catch {
    throw new ODidOAuthError("Secure login state could not be stored for the authorization redirect.");
  }
  const url = new URL(metadata.authorizationEndpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", config.clientId);
  url.searchParams.set("redirect_uri", config.redirectUri);
  url.searchParams.set("scope", config.scopes.join(" "));
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("resource", config.resource);
  return url.toString();
}

function parseTokenResponse(
  payload: Record<string, unknown>,
  now: number,
  previousRefreshToken?: string,
): ODidAccessToken {
  const accessToken = payload.access_token;
  const tokenType = payload.token_type;
  const expiresIn = payload.expires_in;
  const returnedRefreshToken = payload.refresh_token;
  if (
    typeof accessToken !== "string" || !/^[A-Za-z0-9\-._~+/]+=*$/.test(accessToken)
    || accessToken.length > MAX_ACCESS_TOKEN_CHARS
    || typeof tokenType !== "string" || tokenType.toLowerCase() !== "bearer"
    || !Number.isInteger(expiresIn) || (expiresIn as number) < 1
    || (expiresIn as number) > MAX_TOKEN_LIFETIME_SECONDS
  ) {
    throw new ODidOAuthError("ODID returned an invalid access-token response.");
  }
  if (returnedRefreshToken !== undefined && !validRefreshToken(returnedRefreshToken)) {
    throw new ODidOAuthError("ODID returned an invalid refresh-token response.");
  }
  const refreshToken = typeof returnedRefreshToken === "string"
    ? returnedRefreshToken
    : previousRefreshToken;
  return {
    accessToken,
    expiresAt: now + (expiresIn as number) * 1_000,
    ...(typeof payload.scope === "string" ? { scope: payload.scope } : {}),
    ...(refreshToken ? { refreshToken } : {}),
  };
}

export async function completeODIDLogin(
  callbackUrl: string,
  rawConfig: ODidOAuthConfig,
  options: {
    storage?: TransactionStorage;
    fetcher?: Fetcher;
    now?: number;
  } = {},
): Promise<ODidAccessToken> {
  const config = validateConfig(rawConfig);
  const storage = storageOrThrow(options.storage ?? (typeof window !== "undefined" ? window.sessionStorage : undefined));
  let callback: URL;
  try {
    callback = new URL(callbackUrl);
  } catch {
    throw new ODidOAuthError("ODID authorization callback URL is invalid.");
  }
  const registeredRedirect = new URL(config.redirectUri);
  if (
    callback.origin !== registeredRedirect.origin
    || callback.pathname !== registeredRedirect.pathname
    || callback.hash
  ) {
    throw new ODidOAuthError("ODID callback does not match the registered redirect URI.");
  }
  const codes = callback.searchParams.getAll("code");
  const states = callback.searchParams.getAll("state");
  const code = codes.length === 1 ? codes[0] : null;
  const state = states.length === 1 ? states[0] : null;
  const providerError = callback.searchParams.get("error");
  let rawTransaction: string | null = null;
  try {
    rawTransaction = storage.getItem(TRANSACTION_KEY);
    storage.removeItem(TRANSACTION_KEY);
  } catch {
    throw new ODidOAuthError("ODID login state could not be read securely.");
  }
  if (providerError) throw new ODidOAuthError("ODID authorization was not completed.");
  if (!code || code.length > 4_096 || !state || state.length > 256 || !rawTransaction) {
    throw new ODidOAuthError("ODID authorization callback is incomplete.");
  }
  let transaction: LoginTransaction;
  try {
    transaction = JSON.parse(rawTransaction) as LoginTransaction;
  } catch {
    throw new ODidOAuthError("ODID login state is invalid.");
  }
  const now = options.now ?? Date.now();
  if (
    !transaction || transaction.state !== state || transaction.issuer !== config.issuer
    || transaction.clientId !== config.clientId || transaction.redirectUri !== config.redirectUri
    || transaction.resource !== config.resource
    || typeof transaction.verifier !== "string" || transaction.verifier.length < 43
    || transaction.verifier.length > 128
    || typeof transaction.createdAt !== "number" || !Number.isFinite(transaction.createdAt)
    || transaction.createdAt > now || now - transaction.createdAt > TRANSACTION_TTL_MS
  ) {
    throw new ODidOAuthError("ODID login state is invalid or expired. Start login again.");
  }

  const metadata = await discover(config, options.fetcher ?? fetch);
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: config.redirectUri,
    client_id: config.clientId,
    code_verifier: transaction.verifier,
    resource: config.resource,
  });
  let response: Response;
  try {
    response = await (options.fetcher ?? fetch)(metadata.tokenEndpoint, {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    });
  } catch {
    throw new ODidOAuthError("ODID token exchange could not be completed securely.");
  }
  const payload = await readJson(response, MAX_TOKEN_RESPONSE_BYTES, "token");
  if (!response.ok) throw new ODidOAuthError("ODID rejected the authorization-code exchange.");
  return parseTokenResponse(payload, now);
}


export async function refreshODIDAccessToken(
  rawConfig: ODidOAuthConfig,
  currentRefreshToken: string,
  options: { fetcher?: Fetcher; now?: number; signal?: AbortSignal } = {},
): Promise<ODidAccessToken> {
  const config = validateConfig(rawConfig);
  if (!validRefreshToken(currentRefreshToken)) {
    throw new ODidOAuthError("The in-memory ODID refresh token is invalid.");
  }
  const fetcher = options.fetcher ?? fetch;
  const metadata = await discover(config, fetcher);
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: currentRefreshToken,
    client_id: config.clientId,
    resource: config.resource,
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  const forwardAbort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  else options.signal?.addEventListener("abort", forwardAbort, { once: true });
  let response: Response;
  let payload: Record<string, unknown>;
  try {
    response = await fetcher(metadata.tokenEndpoint, {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    });
    payload = await readJson(response, MAX_TOKEN_RESPONSE_BYTES, "refresh-token");
  } catch (error) {
    if (error instanceof ODidOAuthError) throw error;
    throw new ODidOAuthError("ODID session refresh could not be completed securely.");
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", forwardAbort);
  }
  if (!response.ok) throw new ODidOAuthError("ODID rejected the session refresh. Sign in again.");
  return parseTokenResponse(payload, options.now ?? Date.now(), currentRefreshToken);
}

export async function revokeODIDToken(
  rawConfig: ODidOAuthConfig,
  token: string,
  tokenTypeHint: "refresh_token" | "access_token" = "refresh_token",
  options: { fetcher?: Fetcher } = {},
): Promise<boolean> {
  const config = validateConfig(rawConfig);
  if (!validRefreshToken(token)) {
    throw new ODidOAuthError("The in-memory ODID token is invalid.");
  }
  const fetcher = options.fetcher ?? fetch;
  const metadata = await discover(config, fetcher);
  if (!metadata.revocationEndpoint) return false;
  const body = new URLSearchParams({
    token,
    token_type_hint: tokenTypeHint,
    client_id: config.clientId,
  });
  let response: Response;
  try {
    response = await fetcher(metadata.revocationEndpoint, {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    });
  } catch {
    throw new ODidOAuthError("ODID token revocation could not be completed securely.");
  }
  if (!response.ok) throw new ODidOAuthError("ODID token revocation was rejected.");
  return true;
}

export function clearODIDLoginTransaction(
  storage?: TransactionStorage,
): void {
  const safeStorage = storageOrThrow(storage ?? browserSessionStorage());
  try {
    safeStorage.removeItem(TRANSACTION_KEY);
  } catch {
    throw new ODidOAuthError("ODID login state could not be cleared securely.");
  }
}
