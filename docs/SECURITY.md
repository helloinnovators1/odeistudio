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
- The API has a fail-closed RFC 9068-style JWT access-token verifier using configured issuer, audience and JWKS URL (AUTH_ISSUER, AUTH_AUDIENCE, AUTH_JWKS_URL). It requires HTTPS issuer/JWKS, explicit typ (at+jwt or application/at+jwt), RS256, exp, sub, iat, jti and client_id, verifies signature/issuer/audience, and checks client_id against the non-empty AUTH_ALLOWED_CLIENT_IDS allowlist. JWKS responses are bounded to 1 MB/100 keys and cached for five minutes.
- Organization access is resolved separately from the verified subject against an active server-side membership record. Client-supplied organization IDs and token role claims do not establish membership.
- Missing identity configuration fails closed. The dependency is not yet attached to project/task routes because those routes are not exposed; no production ODID issuer is configured. The upstream localStorage/demo-invite role simulation is not production authorization. See IDENTITY_INTEGRATION.md for the required issuer, token, membership and RBAC contract.

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

## Workspace filesystem access and local companion
- Windows reads use native NtCreateFile child opens relative to held directory handles with FILE_OPEN_REPARSE_POINT; Windows enumeration uses GetFileInformationByHandleEx(FileIdBothDirectoryInfo) on held handles. Reparse points are rejected before descending.
- POSIX listing uses os.fwalk; file and .gitignore access is descriptor-relative with O_NOFOLLOW and O_NONBLOCK. File reads are bounded and regular-file verified.
- WorkspaceHandleRegistry retains a selected root OS handle/descriptor, serializes operations, and closes it on revocation. CI covers root-path replacement after registration, Windows junctions, path swaps, POSIX FIFOs and traversal controls.
- The odei-companion prototype binds only to 127.0.0.1, validates exact Origin and Host values, uses one-time pairing and short-lived hashed bearer sessions, allows only workspace:read, supports revocation, returns folder basenames without absolute paths and sends no-store security headers. Chrome loopback-network Local Network Access permission is a separate browser-side gate; the frontend must use HTTPS, an explicit user gesture and targetAddressSpace: loopback.
- The companion is not production-ready: ODID identity/user/tenant binding, audit trail, signed installer, Windows 10 build 18362 validation and the initial folder-picker-to-handle trust boundary remain open. Keep it loopback-only; never bind it to 0.0.0.0 or expose it to the LAN.

## Automated security checks
.github/workflows/security.yml runs:
- Gitleaks secret scanning over repository history and working tree.
- Python dependency auditing from the API project metadata using `python -m pip_audit --strict --desc=on .` (run from `apps/api`). This audits the declared API dependency graph without asking PyPI to resolve the unpublished local application package as if it were a third-party release.
- npm audit against the web dependency tree.
- CodeQL analysis for Python and JavaScript/TypeScript.
- Scheduled, push, pull-request and manual workflow triggers.

An earlier run on commit `02da0ca4fb1e915c307789584f51d7e18bd3de73` failed because the audit attempted to resolve the unpublished local application distribution on PyPI, and CodeQL was cancelled. The workflow was subsequently corrected to audit the API project dependency graph. Security run [44762159926](https://github.com/helloinnovators1/odeistudio/actions/runs/44762159926) completed successfully: Gitleaks, Python `pip-audit`, web `npm audit`, and CodeQL Python plus JavaScript/TypeScript all passed. This is evidence for that exact commit/run, not a permanent guarantee or blanket vulnerability-free certification; review alerts and rerun scans on subsequent changes.

## Cloud model data transfer
- Sending repository text to a hosted model is a separate data-transfer decision from selecting a local folder. Require explicit consent tied to the authenticated user/session before any planner or agent call includes workspace context.
- Redact common secrets before model submission and redact model/tool output before display or logs. Redaction is best-effort defense-in-depth and does not guarantee detection of every credential; secret files remain excluded at the filesystem layer.
- Responses requests set store=false and replay stateless history. This disables Responses application-state storage, but does not itself enable Zero Data Retention or disable default abuse-monitoring retention. Confirm the account's retention controls and customer obligations before production use.
