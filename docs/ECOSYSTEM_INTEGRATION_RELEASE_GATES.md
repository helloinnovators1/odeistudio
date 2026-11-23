# Ecosystem integration and release gates

**Reviewed:** 2026-11-23  
**Verified main:** `45d968d8f4af82ec2d9520da37ded2485e21f87e`.  
**Merged integration:** PRs #49, #52, #53, #56, #67, #74, #76, #80, #81 and #83. This includes NEXUS/MAC/MAD governance, dependency and browser smoke-test integration, API container/Vercel subpath scaffolding and production-readiness/host-routing documentation.  
**Open NEXUS increment:** [PR #85](https://github.com/helloinnovators1/odeistudio/pull/85) is a draft, unmerged bounded multi-file context picker. Exact-head API CI and Security Scanning are being verified.  
**Production decision: NO-GO.** No ODEI production deployment, ODID staging acceptance, production database/secrets, hardened worker fleet, backup restore, target Windows device acceptance, or monitored rollback drill is evidenced.  
**Purpose:** one dependency-aware acceptance register for execution, NEXUS, ODID, MAC, MAD, Windows, browser and hosting work. It separates repository implementation from external provider and device acceptance.

## Current verified integration state

- MAC/MAD governance was integrated through merged PR #74; do not refer to it as an open integration candidate.
- PR #81's Vite TypeScript/subpath build fix is merged. Mainline API CI passed on its merge commit; current mainline Security Scanning passed. PR #83 reconciles production-readiness and host-routing documentation and is merged.
- Main includes ODID PKCE browser foundations, tenant/project-scoped chat/history, SSE streaming/cancellation, bounded excerpt inspection, task planning/approval, patch proposals, single-file companion apply, and the separate approved-profile execution vertical slice.
- NEXUS context inspection remains bounded to explicitly attached excerpts. PR #85 proposes up to five explicitly selected companion files with size/path limits and sensitive-path exclusions; it is not yet merged.
- Multi-file proposal records do not imply multi-file local application. Durable transaction journaling, rollback and crash recovery remain open.
- Task approval is not execution. The approved-profile worker/sandbox vertical slice exists, but the full model-controlled tool loop, integrated test-and-repair cycle and autonomous agent orchestration are not complete.
- The current repository backlog tracks repository indexing (#86), multi-file transactional apply (#87), governed tool loop and verification/repair (#88), parallel agents/worktrees (#89), and browser/MCP/background automation (#90).
- Issue #63 tracks main branch protection and independent review; #64 tracks authenticated browser E2E/accessibility/visual regression; #84 tracks Vercel project and host routing access.
- The connected Vercel team currently has only projects linked to `openpayglobal/zurios`; there is no ODEI project and the existing Zurios project/SSO/routing must not be overwritten. Vercel team write/admin access to `helloinnovators1/odeistudio` and host-project admin access are external prerequisites.
- Real ODID issuer/client/scopes/audience/JWKS/CORS, production MongoDB/KMS/secrets, concrete provider adapters, hardened hostile-code isolation, signed Windows installer/device acceptance, staging and rollback remain external gates.

This document records repository and CI evidence separately from external acceptance. A green workflow proves only that the exact tested commit passed its jobs; it does not prove merge, deployment, live identity integration or production readiness. Detailed historical PR scope descriptions and the original execution acceptance checklists follow. The current authoritative workstream summary is [Implementation Status](IMPLEMENTATION_STATUS.md), and the current NEXUS target architecture is [NEXUS Agent Workspace Implementation](NEXUS_AGENT_WORKSPACE_IMPLEMENTATION.md).

---

## 1. Current execution change set

The following table records the scope delivered by the merged pull requests:

| PR | Scope | Base/dependency | Evidence and remaining boundary |
|---|---|---|---|
| [#26](https://github.com/helloinnovators1/odeistudio/pull/26) | OCI sandbox foundation | main | CI reports Ubuntu/Windows Python matrix, MongoDB integration, web tests/build and security scans. Not user-operational alone; no execution routes, durable runs, tenant/task approval integration, snapshots, worker, artifact lifecycle or production command execution. Requires dedicated Linux worker and approved image digests; stronger isolation must be selected and validated before hostile code. |
| [#27](https://github.com/helloinnovators1/odeistudio/pull/27) | ODID browser refresh/revocation lifecycle | main; independent of execution stack | Browser token lifecycle code and tests are present. Real ODID staging issuer/client/scopes/refresh-token issuance/revocation behavior, API issuer/JWKS and CORS remain external gates. |
| [#28](https://github.com/helloinnovators1/odeistudio/pull/28) | Durable execution runs and worker leases | #26 | Adds tenant-scoped run records, transactional events, leases, heartbeat/expiry and cancellation intent. Still needs upper-layer routes, snapshot ingestion, worker integration, artifacts and authorization. |
| [#29](https://github.com/helloinnovators1/odeistudio/pull/29) | Safe workspace snapshot ingestion | #28 | Adds bounded ZIP validation/extraction and manifest digest. Needs authenticated route integration and production content/DLP/malware scanning policy. |
| [#30](https://github.com/helloinnovators1/odeistudio/pull/30) | Authenticated execution API and worker | #29 | Adds approved-task execution routes, GridFS snapshots/artifacts and worker lifecycle. Requires real worker-host acceptance, runtime/profile provisioning, stronger isolation, secret/content scanning and production operations. |
| [#31](https://github.com/helloinnovators1/odeistudio/pull/31) | NEXUS chat-panel execution integration | #30 | Adds explicit upload/execution consent, profile selection, run polling/cancellation and bounded results. One-shot polling only; task history, validation/review closure and live streaming remain gaps. |
| [#32](https://github.com/helloinnovators1/odeistudio/pull/32) | Snapshot credential heuristics | #30 | Adds common-pattern content scanning. Heuristics cannot prove a workspace is secret-free; managed DLP/secret scanning and malware/content scanning remain required. |
| [#33](https://github.com/helloinnovators1/odeistudio/pull/33) | Worker heartbeat and MAD execution metrics API | #30 | Adds private aggregate metrics endpoint and worker heartbeat. It is not the MAD web dashboard, full alerting, incident workflow or MAC governance. |

All eight changes are merged into the repository mainline. They must not be represented as deployed, connected to production providers, or production-accepted until the external gates in this document are evidenced.

## 2. Dependency-correct integration sequence

Do not merge stacked branches out of order. Rebase/update stacked PRs after each lower layer is merged and rerun required checks against the resulting target commit.

1. Review and accept #26 sandbox foundation, including threat model, runtime command construction, cleanup behavior, mount boundary and host prerequisites.
2. Merge #26 only after required reviews/checks; update #28's base and resolve any changed files.
3. Merge #28; update #29's base.
4. Merge #29; update #30's base.
5. Merge #30 only after API authorization, task approval, tenant scoping, cancellation, GridFS compensation and worker lifecycle have been reviewed together.
6. Rebase and validate #31, #32 and #33 on the merged #30 line. They are sibling follow-ups; their merge order should be chosen by conflicts and test dependencies, not guessed.
7. Review #27 independently and merge only after the browser session semantics and real ODID contract are verified.
8. Run full integration/security CI on the assembled mainline; then perform staging acceptance before any production rollout.

A mergeable flag is not a review approval. Draft PRs must not be converted to ready merely to make the queue appear complete.

## 3. NEXUS execution end-to-end acceptance

- [ ] ODID-authenticated user and active organization membership are resolved server-side.
- [ ] Project membership and task ownership/owner authority are checked for every route and every stored object.
- [ ] Task approval binds exact task version and project; execution requires separate, explicit workspace-upload and execution consent.
- [ ] Profile identifiers resolve only to deployment-owned immutable image digests and commands; browser cannot choose image, command, runtime flags, host paths, environment or network access.
- [ ] Snapshot upload is bounded; archive traversal, duplicate normalized paths, symlinks, hard links, special files, unsafe names and size/ratio bombs are rejected.
- [ ] Path exclusions and content-based secret detection run before durable storage; managed secret/DLP and malware scanning policy is defined before production.
- [ ] Snapshot manifest digest is verified by the worker before execution.
- [ ] Run creation, task transition, ordered lifecycle events and audit writes are transactionally consistent.
- [ ] Worker leases are atomic, renewed, expiry-reclaimed and safe against duplicate execution; retry exhaustion reaches a terminal state.
- [ ] Cancellation is propagated to the actual container/process and verified by cleanup tests.
- [ ] OCI runtime runs on a dedicated Linux worker, with no Docker socket/host credential mounts, network egress disabled by policy, non-root identity, resource quotas and bounded output.
- [ ] Select and validate an appropriate hostile-code isolation boundary (e.g. gVisor/Kata or microVM); do not treat ordinary container flags as a complete hostile multi-tenant boundary.
- [ ] Artifacts are tenant/project/task/run authorized, bounded, redacted, retained per policy and cleaned up with GridFS orphan reconciliation.
- [ ] Task validation and human review are distinct from successful process exit; execution success must not silently mark a task as product-complete.
- [ ] NEXUS UI presents consent, partial snapshot exclusions, run state, cancellation, output truncation and safe failure states.
- [ ] End-to-end staging tests cover identity changes during in-flight operations, organization/project switching, cancellation, worker loss, lease expiry, snapshot tampering and artifact cross-tenant denial.

## 4. ODID and browser session acceptance

- [ ] Confirm canonical HTTPS issuer and discovery metadata from the ODID owner.
- [ ] Register exact public client ID, redirect URI, resource/audience and approved scopes.
- [ ] Verify access-token type/profile, issuer, audience, subject stability, client_id, expiry, JWKS rotation and key overlap.
- [ ] Verify refresh token issuance/rotation and revocation endpoint behavior in staging; do not infer support from generic OAuth metadata.
- [ ] Configure API issuer, audience, JWKS URL, allowed client IDs and exact CORS origins using secret-safe deployment configuration.
- [ ] Verify logout, expiry, identity switch and revocation clear all project/conversation/approval/run context.
- [ ] Verify server-side active membership and project authorization; browser role labels or ID tokens are never authorization.
- [ ] Record staging evidence and a key-rotation/outage runbook.

## 5. MAC control-plane acceptance

MAC is the authoritative administrative control plane, not a collection of mock settings screens.

- [ ] Define platform operator identities, MFA/step-up requirements and server-enforced RBAC/ABAC permissions.
- [ ] Implement tenant/platform scope separation and deny-by-default authorization for every administrative operation.
- [ ] Implement audited environment-variable lifecycle: draft, validate, approve, publish, verify, rotate and rollback where supported.
- [ ] Integrate a KMS-backed vault or external secret manager; persist references/version metadata only; never return stored plaintext.
- [ ] Implement hosting, domains/DNS, databases, AI/model, GitHub, identity/tenant, agent/tool and platform settings through capability-declared provider adapters.
- [ ] Keep Vercel as a separate integration boundary as required by product architecture.
- [ ] Require confirmation/second approver for destructive or production operations; record actor, target, decision and provider request ID.
- [ ] Add immutable/tamper-evident audit storage controls, access reviews, export policy and incident response.
- [ ] Add provider connection health, permission expiry, rate-limit handling and partial-failure reporting.
- [ ] Never claim provider sync/deployment success without authoritative provider confirmation.

## 6. MAD dashboard acceptance

MAD consumes authoritative operational data; MAC remains configuration authority.

- [ ] Build the actual authenticated web dashboard; the PR #33 internal metrics endpoint is not a dashboard.
- [ ] Add platform health for API, workers, queue, database, event transport and storage.
- [ ] Add execution metrics, latency, retries, cancellation, resource utilization, sandbox failures and cleanup backlog.
- [ ] Add integrations/deployment health and commit/environment provenance.
- [ ] Add incidents with severity, source, affected service/tenant, deduplication key, owner, status and runbook.
- [ ] Implement audited acknowledge, assign, resolve and reopen transitions.
- [ ] Add alert routing, delivery retries, deduplication, escalation and notification-channel configuration.
- [ ] Reconcile model/provider usage and cost to authoritative provider records, currency and aggregation window.
- [ ] Add product analytics only under an explicit privacy and retention policy.
- [ ] Enforce operator/tenant visibility on the server; no browser-side filtering as a security boundary.
- [ ] Show freshness and unknown/degraded/stale states; never fabricate production metrics or silently replace missing data with zero.
- [ ] Ensure telemetry excludes secrets, prompts, raw command output and cross-tenant identifiers unless a specifically authorized drill-down contract permits them.

## 7. Windows companion and desktop acceptance

The target device reported by the project owner is Windows 10 version 1903, OS build 18362.1256. GitHub-hosted Windows CI is useful but is not device acceptance.

- [ ] Build and install the companion on a clean Windows 10 build 18362.1256 environment.
- [ ] Verify supported Python/runtime and native Windows API availability; fail with actionable diagnostics when unsupported.
- [ ] Test folder selection, retained root-handle lifetime, reparse-point/junction rejection, path-swap resistance and bounded traversal on the actual filesystem.
- [ ] Verify loopback-only listener, exact Origin/Host checks, one-time pairing, token expiry/revocation and browser Local Network Access permission.
- [ ] Verify read-only scanning without ZIP packaging, with explicit selected roots and exclusion reporting.
- [ ] Verify signed installer/update provenance and companion/server signing-key rotation.
- [ ] Test the signed one-file apply path, challenge replay rejection, base-hash mismatch and atomic replacement.
- [ ] Keep multi-file writes disabled until transaction/rollback journal and crash-recovery tests exist.
- [ ] Test Chrome-to-companion-to-NEXUS staging workflow end to end; no desktop scan or device acceptance is claimed until performed on the target machine.

## 8. Release and production gates

- [ ] All stacked PRs are reviewed, rebased and merged in dependency order.
- [ ] Full API matrix, Windows/Ubuntu matrix, frontend tests/build, real MongoDB replica-set integration, CodeQL, secret scanning and dependency audits pass on the exact release commit.
- [ ] Staging ODID issuer, MongoDB replica set, model provider and allowed origins are configured and verified.
- [ ] Dedicated worker infrastructure, immutable image digests, stronger sandbox isolation, quotas, backups and private ingress are provisioned.
- [ ] MAC/MAD access controls, audit, alerting, incident and runbooks are accepted.
- [ ] Windows target-device acceptance is recorded.
- [ ] Backup restore, GridFS orphan reconciliation, worker recovery, key rotation and incident drills pass.
- [ ] Release artifact is immutable and provenance-attested; staging smoke tests pass.
- [ ] Production rollout has explicit approval, monitored health thresholds and a tested rollback plan.

## 9. Operational truth

Execution PRs #26–#33 are merged into main. PR #49 MAD dashboard is merged. PR #55 MAC/MAD transactional governance and PRs #52, #53 and #56 NEXUS hardening remain open and unmerged; each latest reconciled head passed API CI and Security Scanning. Mainline Security Scanning, including CodeQL, passed on commit `8b2b2e6f9449732256fb756d7d81f848e5a91597`. No production deployment, live ODID provider connection, provisioned worker execution, staging acceptance, target Windows device acceptance, or complete MAC/MAD product acceptance is claimed. The remaining checklists in this document are live release gates, not claims of completion.


## MAC transactional audit implementation — 2026-11-22

- Successful MAC lifecycle mutations and their success audit records now share one MongoDB transaction/session. If the audit insert fails, the mutation is rolled back. Failure/denial records are appended separately after the aborted transaction.
- The transaction requires a replica set or sharded MongoDB topology. The API readiness check reports transaction support and rejects standalone MongoDB.
- Route-level tests assert that the MAC store operation and audit insert receive the same session. A real replica-set integration test also verifies that an audit insert failure rolls back the MAC revision and that a successful operation persists the revision and audit event together. Exact code head `909caf02edd077146e8a78f2f700fb02c83ec305` passed API CI [45018761778](https://github.com/helloinnovators1/odeistudio/actions/runs/45018761778) and Security Scanning [45018761807](https://github.com/helloinnovators1/odeistudio/actions/runs/45018761807), including Windows/Ubuntu Python 3.10/3.12 and real MongoDB replica-set integration.
- PRs #50 and #51 are closed as superseded by PR #55, which consolidates both implementations on current `main`. The latest reconciled PR #55 head has passed API CI 6/6 and Security Scanning 4/4, including Windows/Ubuntu Python 3.10/3.12, web tests/build, MongoDB replica-set integration, CodeQL, dependency audits and secret scanning.
- PR #55 is open and unmerged pending independent review. The promotion endpoint changes only the active configuration pointer; it is not a provider deployment.
- Remaining MAC release gates: production secret-manager adapter and authorization, concrete provider adapter, provider-side idempotency/reconciliation, provider health verification and rollback/compensation, operator-applied revision migration, real ODID staging permissions, worker deployment, monitoring and operational acceptance.


## MAC/MAD current integration candidate — 2026-11-23

- PR #66 is closed as superseded. PR #74 is the current-main integration candidate for MAC environment revisions, NEXUS MAC panel, deployment worker, transactional audit, bounded secret resolution, separate request/approval permissions and associated tests.
- PR #74 latest head `e2d4e106decfde1916defea8b93cbb509d9743d6` is based directly on current main `33354c866beda0da44a3f65bbf42a35b552bb509`, has no merge conflicts and is rerunning API CI and Security Scanning. Its preceding code-equivalent head passed both workflows (API CI 6/6, Security Scanning 4/4).
- PR #74 remains unmerged and has no independent security approval. Main remains unprotected; no production migration, worker deployment, provider invocation or production rollout has been performed.
- Before merge: independent review of transaction/audit session propagation, provider idempotency/reconciliation, secret resolver cancellation, allowlisted factory loading, migration/rollback and worker crash recovery. Before rollout: staging replica-set migration rehearsal, real ODID and operator-role acceptance, concrete provider/secret-manager adapters, hardened isolated worker and monitored rollback.
