# ODEI Identity Integration Contract

**Status:** blocked on a production ODID issuer and authorization contract  
**Last reviewed:** 2026-11-20

## Executive decision

Do not connect ODEI Studio's protected APIs to the upstream browser-local identity simulation. The upstream source documentation explicitly states that its role registry, demo invite codes, browser-local sessions and client-side admin redirects are not production authorization. The ODEI Identity overview describes a historical OPMS identity seed, with heuristic KYC and an MFA flag that is not enforced. Those artifacts are useful product references, not a trusted token issuer or a production authorization service.

The target API therefore fails closed until real issuer, audience and JWKS settings are configured. It must never infer authorization from browser localStorage, role dropdowns, demo invite codes or unverified JWT claims.

## Verified upstream evidence

- docs/upstream/ODEI_IDENTITY_HOLISTIC_SOURCE.md describes ODID as a foundational identity product but records the root brief as historically thin and OPMS Universal Identity as a seed to extract/promote.
- docs/upstream/PRODUCTION_ROLES_SOURCE.md explicitly calls the local identity stand-in a browser-local UX simulation. It documents member/operator/admin labels and demo invite codes, while warning that protected server routes do not validate trusted ODID claims or enforce server-side 401/403.
- docs/upstream/ODEI_AUTH_UI_SOURCE.md describes reusable login/register/reset UI patterns; it does not define a production token issuer, access-token profile, JWKS endpoint or server authorization contract.

Do not copy the local role storage or invite-code logic into ODEI Studio backend authorization.

## Implemented target verifier

The API security module currently:
- Requires HTTPS issuer and HTTPS JWKS URL, plus a non-empty explicit allowlist of registered OAuth client_id values (AUTH_ALLOWED_CLIENT_IDS).
- Fetches JWKS with a five-second timeout, five-minute cache, one-megabyte response cap and maximum 100 keys.
- Accepts RS256 only and requires a unique matching RSA key ID. If supplied, JWK alg/use/key_ops must be compatible with RS256 signature verification.
- Requires an explicit JWT access-token type: at+jwt or application/at+jwt.
- Verifies issuer, audience, signature and expiry, requires sub, iat, jti and client_id, and rejects client_id values outside the configured allowlist.
- Parses the optional space-delimited scope claim into the verified Principal.
- Resolves organization membership separately from server-side storage using verified issuer/subject context and an active membership record.

This implements a strict RFC 9068-style JWT access-token profile. It intentionally rejects untyped JWTs and OIDC ID tokens. It does not mean that a production ODID issuer has been connected or that role-based authorization is complete.

## Contract required from ODID before production integration

The Identity service owner must publish and verify the following versioned contract:

1. **Issuer and discovery:** canonical HTTPS issuer identifier, OIDC/OAuth metadata endpoint, HTTPS JWKS URI, signing-key rotation and overlap policy.
2. **Access-token profile:** RFC 9068 compatibility (typ at+jwt or application/at+jwt; iss, aud, exp, sub, client_id, iat and jti; documented scope semantics). If ODID cannot implement RFC 9068, publish a versioned custom access-token profile with an explicit typ and equivalent anti-token-substitution rules. Do not silently accept untyped tokens.
3. **Audience and client registration:** exact ODEI Studio API audience and approved web/desktop client IDs. Define which clients may request each scope.
4. **Subject stability:** define whether sub is globally stable or issuer-scoped. The target membership key is the verified issuer + subject pair, not email address.
5. **Membership source of truth:** authoritative organization membership API/store, immutable organization ID, user subject mapping, active/suspended/revoked status, invitation acceptance, removal and audit behavior.
6. **Roles and permissions:** confirm the production role vocabulary and its semantics. The upstream member/operator/admin labels are provisional UI policy, not a production authorization contract. Define least-privilege permissions for Studio, MAC, deployments, secrets, agents and billing separately.
7. **Project-level authorization:** define project membership, repository/workspace ownership, role inheritance, service accounts and cross-tenant denial rules.
8. **Session lifecycle:** access-token maximum lifetime, refresh-token policy, logout/revocation, compromised-session response and clock-skew policy.
9. **Authentication assurance:** MFA requirements, acr/amr/auth_time semantics and which privileged actions require step-up authentication. Do not trust an unenforced MFA boolean.
10. **Operations:** key rotation runbook, issuer/JWKS outage behavior, audit event schema, incident response and staging/test issuer.

## Target authorization rules

- Verify access tokens at the API boundary; never accept ID tokens as API bearer access tokens.
- Use verified issuer + subject as the identity key. Do not key authorization by mutable email. Restrict client_id to explicitly registered Studio API clients.
- Resolve memberships and project access from server-side storage. Never trust role, tenant or project identifiers supplied only by the browser.
- Apply tenant filters to every tenant-owned database query.
- Distinguish 401 (missing/invalid token), 403 (valid identity but no permission), and 503 (identity provider/configuration unavailable).
- Use explicit permission checks for sensitive actions such as secret access, shell execution, writes, deployment and admin changes.
- Record actor, organization, project, action, target, decision and trace ID in audit events; never log bearer tokens or secret values.
- Keep local companion pairing tokens separate from ODID user tokens. A loopback pairing session is not a cloud identity or tenant membership.

## Current limitations

- No real ODID issuer, audience, JWKS endpoint or allowed client IDs are configured in this repository.
- The protected API exposes verified identity metadata, organization membership lookup and an initial project-scoped NEXUS task API. Task routes enforce active organization membership, active tenant-matched project access, issuer+subject owner identity, active project membership, task-owner/project-owner read access and project-owner-only approval. They are not production-enabled against ODID because no production issuer contract is configured.
- The membership endpoint resolves active membership by organization ID + verified issuer + subject from MongoDB and returns only organization ID and role. It does not yet enforce a production role vocabulary or project-level permissions. Missing membership storage fails closed with 503; missing/inactive membership returns 403.
- There is no membership provisioning/invitation lifecycle, refresh/revocation integration or MFA step-up enforcement. Audit coverage is partial: organization-membership decisions and NEXUS task create/approve/cancel/read/event-read plus selected task denials are recorded; authentication failures, companion pairing/revocation, tool execution, full coverage review and DB-level immutability remain outstanding.
- The RFC 9068 profile is the target contract for this API. The actual ODID issuer must be tested against it before enabling protected routes.


- The initial project-scoped NEXUS chat route is now implemented at `POST /organizations/{organization_id}/projects/{project_id}/nexus/chat`. It uses the same verified bearer dependency and server-side organization/project membership checks, requires explicit cloud consent, redacts bounded chat/file context, records prompt-free audit metadata and calls the Responses API with `store=false` and no tools. It does not mean ODID is connected: no production issuer/client settings or browser token-acquisition flow are configured.
- The React workspace composer remains disabled. Do not enable it or ask users to paste tokens into browser storage until ODID publishes the contract above and the browser implements Authorization Code + PKCE, in-memory access-token handling, refresh/revocation and exact registered client settings.

## Acceptance tests before production ODID enablement and cloud workspace APIs

- Valid access token with correct typ, issuer, audience, key, subject and required claims succeeds.
- ID token, missing/wrong typ, wrong issuer/audience, expired token, future iat, missing jti/client_id, unknown/ambiguous kid, wrong key use and non-RS256 algorithm fail.
- Oversized/invalid JWKS and non-HTTPS issuer/JWKS fail closed.
- Active organization membership succeeds; missing, suspended, revoked and cross-tenant membership returns 403. Missing membership storage returns 503; malformed membership records fail closed.
- Project owner/member/operator/admin policy is verified against the approved role contract, not inferred from localStorage.
- Key rotation works with old/new key overlap and unknown old keys fail after retirement.
- Every sensitive route returns correct 401/403/503 and emits a redacted audit event. Current membership and NEXUS task routes have partial audit hooks; expand tests to every route and denial path before production.
- Project/task route tests verify cross-issuer isolation, project membership, task-owner read restrictions, project-owner approval and optimistic-version conflicts.
- NEXUS task create/approve/cancel writes task state, lifecycle events and audit events in one MongoDB transaction; verify rollback against a real replica-set CI job.

## References

- Upstream historical identity source: docs/upstream/ODEI_IDENTITY_HOLISTIC_SOURCE.md
- Upstream local roles warning: docs/upstream/PRODUCTION_ROLES_SOURCE.md
- Upstream auth UI patterns: docs/upstream/ODEI_AUTH_UI_SOURCE.md
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068.html
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725.html
- RFC 8414 — OAuth 2.0 Authorization Server Metadata: https://www.rfc-editor.org/rfc/rfc8414.html


## Implemented protected project/task API (initial slice)

The target currently exposes these authenticated routes under `/api/v1/organizations/{organization_id}/projects/{project_id}/tasks`:

- `POST` collection: explicit cloud-model consent, planning and durable approval-ready task creation.
- `GET /{task_id}`: task-owner or project-owner read.
- `GET /{task_id}/events`: authorized cursor-paginated lifecycle events.
- `POST /{task_id}/approve`: project-owner-only approval with expected-version concurrency; approval does not start execution.
- `POST /{task_id}/cancel`: authorized cancellation with expected-version concurrency.

These routes use the configured JWT verifier and server-side Mongo membership/project records. They do not provide membership provisioning, role administration, workspace file access, patch application or command execution. Do not treat the existence of these initial routes as production ODID integration.
