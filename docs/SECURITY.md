# Security, Privacy and Trust Baseline

## Security objectives
Protect source code, credentials, customer data, infrastructure and agent execution from cross-tenant access, prompt injection, supply-chain attacks, accidental disclosure and destructive automation.

## Identity and authorization
- Authenticate users through established identity protocols; require MFA for privileged roles.
- Enforce RBAC/ABAC on the server for every resource and action.
- Resolve tenant membership on every request; never trust client-supplied tenant IDs.
- Separate roles for secret administration, secret use, infrastructure changes and audit.
- Use short-lived sessions/tokens, rotation and revocation.

### Current API authentication foundation
- The API now has a fail-closed OIDC access-token verifier using a configured issuer, audience and JWKS URL (`AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL`). It accepts RS256 only, requires `exp` and `sub`, and verifies signature, issuer and audience.
- JWKS documents are fetched over TLS with a bounded timeout and cached for five minutes; the cache refreshes after expiry. Signing key selection requires one matching RSA `kid`.
- Organization access is resolved separately from the verified subject against an active server-side membership record. Client-supplied organization IDs and token role claims do not establish membership.
- Missing identity configuration fails closed. The dependency is not yet attached to project/task routes because those routes are not exposed; do not treat this foundation as completed SSO or production tenant authorization.

## Secrets
- Store secret material in a managed KMS-backed vault or external secret manager.
- Store only references, version identifiers and non-sensitive metadata in MongoDB.
- Mask values after submission; no ordinary read endpoint returns saved secret plaintext.
- Inject secrets server-side into narrowly scoped operations.
- Redact credentials from logs, traces, error messages, model context and support exports.
- Rotate any credential that has been exposed in chat, source control or project documentation.

## Agent and tool security
Repository files, issue text, webpages, terminal output and tool responses are untrusted input. They cannot override system policy or authorize additional tool use. Validate tool arguments and paths. Block path traversal and unsafe symlink escapes. Use explicit tool allowlists and per-task capabilities.

## Execution isolation
Use disposable, non-root sandboxes with resource quotas, process limits, filesystem boundaries and network egress controls. Do not mount host credentials or production secrets. Require approval for privileged commands and external side effects.

## Application security
Use secure headers, CSRF protection where applicable, strict CORS, input validation, output encoding, dependency scanning, SAST, secret scanning, rate limits and safe error responses. Protect webhook endpoints with signature verification and replay defense.

## Data governance
Classify data, minimize collection, define retention/deletion, encrypt transport and storage, back up critical records, restrict exports and log access. Keep audit trails tamper-evident and access-controlled.

## Incident response
Prepare procedures for credential compromise, tenant isolation breach, malicious agent execution, provider compromise and data loss. Include containment, credential revocation, evidence preservation, notification assessment, recovery and post-incident review.

## Release gate
No production release with known critical/high exploitable vulnerabilities, plaintext secret persistence, missing tenant authorization, unbounded agent execution or unverified destructive operations.
