# ODID Browser Authentication Client

**Status:** provider-neutral PKCE client merged into main and wired into the NEXUS panel's sign-in/callback flow. Production authentication remains gated on the real ODID public-client contract, API token profile, API CORS allowlist and live staging verification.

## What this increment provides

`apps/web/src/odid-auth.ts` implements an OAuth 2.0 Authorization Code flow with PKCE S256:

- Fetches issuer discovery metadata over HTTPS and requires an exact issuer match.
- Requires the authorization server to advertise `code_challenge_methods_supported: ["S256", ...]`.
- Uses cryptographically random state and verifier values, then derives an S256 challenge with Web Crypto.
- Requests an explicitly configured API resource using the RFC 8707 `resource` parameter.
- Uses a registered redirect URI, public client ID and caller-supplied scopes. No client secret is accepted or sent.
- Exchanges the one-time authorization code using the verifier and a no-credentials, no-cache, redirect-rejecting request.
- Bounds discovery/token response bodies, authorization code, access-token size and token lifetime.
- Validates the callback origin/path and state, consumes the one-time transaction, and rejects expired or mismatched transactions.
- Returns the access token to the caller in memory. It never writes access or refresh tokens to localStorage, sessionStorage, cookies, URLs or logs.

The only browser storage used is sessionStorage for the short-lived state/verifier transaction required to survive the authorization redirect. The transaction expires after ten minutes and is removed before token exchange. Applications must clear in-memory access/refresh tokens on logout, failed refresh, expiry or account change, and attempt provider revocation when supported.

## Explicit limitations

This is a generic OAuth 2.0 public-client adapter, not proof that ODID implements the required contract. The Studio now calls this client from `NexusChatPanel.tsx`, handles the registered callback route, keeps the access token and any optional rotating refresh token in React memory, refreshes before expiry when supported, and clears the callback query from browser history. The panel uses it to load the authenticated user's projects and unlock the read-only composer. It does not persist tokens or validate an ID token. If the provider returns a refresh token, the helper refreshes before access-token expiry, accepts refresh-token rotation, and retains the token only in React memory. If discovery advertises an RFC 7009 revocation endpoint, sign-out attempts revocation; local state is cleared immediately even if revocation is unavailable or fails. The API remains the authority for the authenticated principal and access-token validation. The panel now discovers active organization memberships through a new authenticated server endpoint; project authorization is enforced by the existing server-side project-list and chat APIs. The API remains the authorization authority and validates its own access-token profile on every protected request.

The API currently requires a signed RS256 access token with explicit `typ=at+jwt` or `application/at+jwt`, issuer, audience, expiry, subject, issued-at, token ID and allowlisted client ID. A successful OAuth token response alone does not prove that the returned token satisfies this profile. The first authenticated API request must be accepted by the backend verifier and membership checks.

## Required ODID and deployment configuration

The Identity service owner must provide and verify, through a versioned contract:

1. Canonical HTTPS issuer and its discovery metadata URL.
2. Public Studio browser client ID and exact registered redirect URI for each environment.
3. API resource/audience identifier and confirmation that ODID supports RFC 8707 resource indicators at authorization and token endpoints.
4. Allowed scopes and their server-side authorization semantics.
5. Authorization-code + PKCE S256 support for public clients; token endpoint CORS policy for the exact Studio origin.
6. Access-token profile compatible with the API's RFC 9068-style RS256/JWKS verifier, including `typ`, `iss`, `aud`, `exp`, `sub`, `iat`, `jti` and `client_id`.
7. Refresh, revocation, maximum lifetime, key rotation, staging issuer and incident-response behavior.

Do not invent these values, commit credentials, or ask users to paste bearer tokens. Public configuration is not a secret, but it must still be registered and verified by the Identity/API owners.

## Integration sequence

1. Supply approved public issuer/client/redirect/resource/scope configuration through environment-specific public runtime configuration.
2. The NEXUS panel now handles the configured callback path, calls `completeODIDLogin(window.location.href, config)`, removes authorization parameters from browser history, and keeps the returned access token in React memory only.
3. The panel calls the existing organization-scoped project-list endpoint with the bearer token; that endpoint verifies the token and active organization membership server-side. The panel discovers organizations through the authenticated `GET /api/v1/organizations` endpoint, then loads the selected organization's authorized projects.
4. Call the tenant-scoped project-list transport and require explicit project selection.
5. Connect the NEXUS composer only after a verified principal, active organization, authorized project and affirmative per-request cloud-model consent exist.
6. Keep access and optional refresh tokens in memory only. Refresh before expiry when the provider issues a refresh token, replace rotated refresh tokens, and clear the session/re-authenticate on refresh failure. On logout, clear all pending PKCE state and attempt provider revocation when supported; never store access or refresh tokens in browser storage.
7. Add a real ODID staging integration test for issuer/JWKS/token profile, CORS, callback registration, scopes, resource/audience and membership denial before production enablement.

## Verification

Vitest coverage exercises discovery issuer matching, PKCE S256 request parameters, state mismatch, callback-origin mismatch, transaction expiry/consumption, token response validation, bounded response bodies and the absence of token persistence. CI on the current pull request is the verification gate; no local browser or ODID staging test has been performed in this hosted session.


## Studio integration update — 2026-11-21

- Added the authenticated NEXUS panel component and connected it to the IDE shell. The panel performs ODID authorization-code + PKCE login, processes the registered callback, strips callback query parameters from browser history and holds the access token only in component memory.
- Added the project-list flow using the existing tenant-scoped project transport. Since there is no organization-discovery endpoint, the user enters an organization ID; the API remains authoritative and returns only projects the verified identity may access.
- Added a functional composer with Enter-to-send, Shift+Enter newline, explicit unchecked per-request cloud-model consent, optional user-selected active-file excerpt, bounded transcript, in-memory session-only history, abort/cancel, expiry clearing, sign-out and safe error states.
- Added public browser environment template values in `apps/web/.env.example`. Added strict explicit-origin CORS configuration through `CORS_ALLOWED_ORIGINS`; wildcard, non-loopback HTTP, credentials, paths, query and fragments are rejected.
- This is an interactive authenticated read-only chat integration, not a production ODID deployment. No issuer, client ID, redirect, resource, scopes, API audience, JWKS URL, allowed-client ID, CORS origin, database or model credentials have been configured here. No real identity provider or browser staging test has been run.
- No streaming, durable conversation persistence, model tool calls, chat-triggered patch proposals, patch approval/application, isolated command/test execution or agent orchestration is included in this increment. The transcript is lost on reload and capped to the latest 20 messages.


### Organization discovery update

- Added `GET /api/v1/organizations`, which filters active memberships by the verified issuer and subject, bounds results to 100, validates membership records and audits each returned organization.
- Added the typed browser transport and panel organization selector. The client does not accept organization IDs or roles as authorization evidence; all membership checks remain server-side.
- Organization discovery returns identifiers and roles only. Organization names/branding and invitations remain outside this endpoint.
