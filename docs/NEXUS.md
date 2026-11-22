# ODEI NEXUS — AI Software Engineering Agent

**Status:** Implemented vertical slices spanning authenticated chat, bounded inspection, durable tasks, reviewed patch proposals, isolated execution and a paired local companion. NEXUS is not yet a fully autonomous, production-accepted software engineering agent. Capabilities below distinguish implemented repository behavior from gated or unavailable workflows.

## Mission and trust boundaries

NEXUS is ODEI Studio's project-scoped engineering control plane. It receives developer intent, binds it to an authenticated organization/project, gathers only authorized context, plans work, requests approval where required, and exposes controlled proposal, execution and review workflows.

The browser is not an authorization boundary. Every API operation must verify the access token, active organization membership, project access, task/proposal ownership and capability policy on the server. Model output, repository files, tool results and user-provided instructions are untrusted data. A UI label, client-supplied role or model statement never grants permission.

## Implemented capability map

| Capability | Current behavior | Hard boundary |
|---|---|---|
| Identity | ODID Authorization Code + PKCE browser client foundation, callback/state validation and in-memory access/refresh token lifecycle. API validates signed access tokens against configured issuer/audience/JWKS. | Real ODID issuer/client/callback/scopes/audience and production API trust configuration must be supplied and staging-verified. |
| Organization/project | Authenticated membership and authorized project discovery/selection. PR #71 adds a request-generation guard so stale project-list responses cannot overwrite state after organization changes, sign-out or session expiry. | Authorization is rechecked server-side. Full authenticated browser acceptance for organization/project switching remains open. |
| Chat | Consent-gated Responses API requests, bounded history/context, SSE text streaming and browser cancellation. | Browser abort stops delivery; provider-side cancellation is best-effort. |
| Conversation history | Owner- and tenant-scoped MongoDB persistence with bounded messages and optimistic versions. | Conversation mutation and separate audit writes still need transaction/idempotency review. Production MongoDB, retention, encryption and backup controls are deployment gates. |
| Inspection | Bounded model tool loop with list/read/literal search and secret redaction over explicitly attached excerpts. | Not unrestricted whole-repository semantic indexing. The panel currently attaches the active file excerpt rather than a complete multi-file context manager. |
| Task planning | Durable task records, approval-ready plans, owner-only approval, cancellation and lifecycle events. | Approval records intent; it does not by itself mean work is complete. |
| Patch proposals | Persisted proposal records, per-file operation/hash/diff metadata and owner approve/reject decisions. | Approval does not write files. |
| Local apply | One-file apply only, requiring owner approval, explicit local confirmation, fresh one-use companion challenge, short-lived signed capability and live base-hash verification. | No multi-file transaction, journal, automatic rollback or crash recovery. Never imply otherwise. |
| Execution | Approved task/profile flow, explicit workspace-upload and code-execution consent, bounded filtered snapshot, durable run/events/leases, sandbox worker, cancellation and artifacts. | Production hostile-code isolation and worker operations require hardened infrastructure and staging/recovery drills. |
| MAD | Aggregate worker/execution telemetry and incident lifecycle UI/API with scoped server-side authorization. | External telemetry and alert delivery, operational calibration and real operator provisioning remain deployment gates. |
| MAC | Role/permission foundation exists in main; broader environment governance and deployment-worker changes are in open PR #66. | Do not treat PR #66 as merged or operational. Requires independent review, real provider/secret adapters, migration and enforcement acceptance. |

## NEXUS request lifecycle

1. **Authenticate:** obtain a short-lived access token through the approved ODID PKCE flow. Keep tokens out of local storage, URLs, logs and analytics.
2. **Bind tenant and project:** load only memberships/projects returned by authenticated APIs. The server independently revalidates every operation.
3. **Obtain consent:** disclose when prompts and selected excerpts are sent to the configured cloud model. Consent is affirmative and scoped; companion pairing is not model consent.
4. **Select context:** attach only bounded, authorized excerpts. Redact likely credentials before model submission and output. Do not silently upload the complete workspace.
5. **Chat or inspect:** default chat uses no repository tools. Inspection tools are explicitly enabled and constrained to the attached excerpt set.
6. **Plan:** create a durable task with bounded goal/context and an approval-ready plan.
7. **Approve:** only the authorized project owner may approve the plan or a patch proposal. Approval is a recorded decision, not an implicit file write or deployment.
8. **Propose:** generate a persisted, reviewable diff with base/result hashes and validated paths.
9. **Apply one file:** require the paired companion, explicit local confirmation, fresh one-use challenge, signed short-lived capability and unchanged base snapshot.
10. **Execute:** require a server-approved execution profile plus separate affirmative workspace-upload and code-execution consent. Execute only the immutable filtered snapshot in the configured sandbox.
11. **Validate and review:** inspect run status, bounded output and artifacts. Sandbox exit success is not equivalent to task completion, production deployment or user acceptance.
12. **Report evidence:** identify changed artifacts, checks actually run, failures, remaining risks and external acceptance gates. Never claim an action occurred without its result.

## Execution and local-write safety

- Workspace snapshots are filtered and bounded; skipped files must be disclosed before upload.
- Execution uses a server-approved profile and a durable run/task lifecycle. Network, credentials, process limits, resource limits and runtime isolation must be enforced by the worker deployment, not trusted to model instructions.
- The local companion is loopback-bound and paired to an explicitly selected workspace. API-signed capabilities are independently verified by the companion.
- The current patch apply endpoint is intentionally single-file. Multi-file changes must remain disabled until a durable journal, preflight, recoverable commit protocol, idempotent restart recovery and rollback have been implemented and tested on Windows and POSIX.
- Do not run arbitrary host shell commands, install packages, deploy infrastructure or push/merge Git changes unless a separately authorized workflow explicitly permits the action.

## Audit, persistence and failure semantics

- Persisted tasks and their lifecycle events have transaction-coupled audit guarantees in the MongoDB transaction paths.
- Conversation and patch-proposal mutation/audit consistency still require further hardening. A mutation followed by a separate audit failure can produce an ambiguous outcome; add transactional coupling or idempotent reconciliation before claiming end-to-end exactly-once semantics.
- Treat retries as potentially duplicative unless the endpoint has an explicit idempotency key or version guard.
- Fail closed when identity, authorization, required audit persistence, base-hash verification, capability verification or durable state is unavailable.
- Avoid logging prompts, file contents, credentials, bearer tokens, capability secrets or provider responses containing sensitive material.

## Browser testing status

Playwright/Chromium CI is present. The merged browser suite currently covers opening the NEXUS panel, the keyboard shortcut, narrow shell overflow, accessible panel identity, safe unauthenticated/configuration state, and panel-open overflow at 320, 360, 390, 768, 1024 and 1440 CSS-pixel widths.

Still required: mocked authenticated ODID callback success/failure; org/project switching and stale responses; conversation create/load/send/stream/cancel/delete; session expiry/sign-out; task approval; execution consent/run/cancel/artifact flows; proposal review and companion apply; companion pairing/workspace errors; MAC/MAD authorization and incident workflows; keyboard/focus/dialog behavior; axe checks and deterministic visual baselines.

## Production acceptance gates

- Register and test real ODID browser/API trust settings and tenant isolation.
- Provision MongoDB with replica-set transaction support, backups, restore tests, encryption and retention/deletion controls.
- Configure model credentials and an approved secret manager without placing secrets in source or chat.
- Deploy a hardened worker fleet with immutable images, no host credentials, restricted egress, quotas, monitoring and tested crash/cancel/retry recovery. Ordinary OCI flags alone are not sufficient for hostile multi-tenant workloads.
- Install and test the companion on the target Windows 10 build 18362.1256 device; verify signed installer/update and key rotation.
- Implement multi-file journal/rollback before enabling multi-file writes.
- Enable independent code review and required CI/security checks on `main`.
- Complete staging acceptance, backup/restore, incident drills, monitored rollout and rollback approval.

## Product capabilities not yet complete

The full Agents Window/CLI, policy-controlled multi-agent orchestration, durable background agents, broad semantic project indexing, unrestricted multi-file authoring, automatic repair loops, production deployment automation and full ecosystem-wide operational acceptance are not complete. Do not describe NEXUS as fully autonomous or production-ready until their explicit acceptance gates pass.
