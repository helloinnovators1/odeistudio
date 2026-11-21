# ODID Browser Authentication Client

**Status:** provider-neutral PKCE client implemented and under CI verification; not yet wired into the Studio application. Production authentication remains blocked until the ODID service owner supplies and verifies the real public-client contract.

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

The only browser storage used is sessionStorage for the short-lived state/verifier transaction required to survive the authorization redirect. The transaction expires after ten minutes and is removed before token exchange. Applications must clear their in-memory token on logout, expiry or account change.

## Explicit limitations

This is a generic OAuth 2.0 public-client adapter, not proof that ODID implements the required contract. It is not connected to `App.tsx`, the project selector or NEXUS composer. It does not persist tokens, refresh sessions, validate an ID token, implement logout/revocation, or establish organization/project permissions. The API remains the authorization authority and validates its own access-token profile on every protected request.

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
2. Add a dedicated callback route that calls `completeODIDLogin(window.location.href, config)`, removes authorization parameters from browser history, and keeps the returned access token in React memory only.
3. On successful login, call `/api/v1/auth/me` and the organization membership endpoint; the API must verify the token. Resolve organizations from a trusted server-side discovery API before showing project selection.
4. Call the tenant-scoped project-list transport and require explicit project selection.
5. Connect the NEXUS composer only after a verified principal, active organization, authorized project and affirmative per-request cloud-model consent exist.
6. Clear in-memory token and all pending PKCE state on logout, expiry, identity change or authorization failure. Re-authenticate rather than storing refresh/access tokens in browser storage.
7. Add a real ODID staging integration test for issuer/JWKS/token profile, CORS, callback registration, scopes, resource/audience and membership denial before production enablement.

## Verification

Vitest coverage exercises discovery issuer matching, PKCE S256 request parameters, state mismatch, callback-origin mismatch, transaction expiry/consumption, token response validation, bounded response bodies and the absence of token persistence. CI on the current pull request is the verification gate; no local browser or ODID staging test has been performed in this hosted session.
