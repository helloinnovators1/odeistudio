# ODEI Studio Implementation Roadmap

This roadmap is ordered by dependencies. Status is updated only from repository artifacts and completed test evidence. A checked item means the described artifact or test exists; it does not imply production readiness. A design document alone does not count as an implemented capability.

## Phase 0 — Repository and security baseline

- [x] Verify repository access and default branch.
- [x] Establish architecture and initial MAC/provider requirements.
- [x] Add canonical documentation index and ecosystem specifications.
- [x] Audit the upstream Studio/ecosystem source tree and preserve all 68 Markdown/text source documents with provenance (47 path-preserving mirrors and 21 curated snapshots); complete target-repository inventory remains ongoing.
- [ ] Rotate any credential previously exposed in project setup material and verify rotation in the source environment.
- [x] Add linting and GitHub Actions CI (Ruff + pytest) on Ubuntu/Windows and Python 3.10/3.12; pull-request path filters include `apps/web/**` so frontend changes trigger web tests/build.
- [x] Add secret scanning (Gitleaks), Python dependency auditing (pip-audit), web dependency auditing (npm audit) and CodeQL for Python/TypeScript.
- [x] Verify the latest API/web CI on corrected audit-store head: [44776939214](https://github.com/helloinnovators1/odeistudio/actions/runs/44776939214) — Ubuntu/Windows × Python 3.10/3.12 and web tests/build all passed on `b44d732c884475d469527b001d88216feaa0ae05`.
- [x] Verify the latest security workflow on the same head: [44776939169](https://github.com/helloinnovators1/odeistudio/actions/runs/44776939169) — Gitleaks, pip-audit, npm audit and CodeQL Python/TypeScript all passed.
- [ ] Continue reviewing scanner alerts and dependency changes; successful runs are evidence for one commit, not a permanent security certification.

## Phase 1 — NEXUS foundation

- [x] Scaffold Python/FastAPI backend foundation.
- [ ] Select and scaffold the canonical frontend after reconciling the upstream Next.js/Monaco Agents and Editor application. Current React/TypeScript/Vite client is an initial read-only companion workspace, not the full editor.
- [x] Add configuration validation and safe environment handling.
- [x] Implement fail-closed RS256/JWKS verification and protected `/api/v1/auth/me` identity route.
- [ ] Connect a confirmed production ODID issuer/audience/JWKS contract, provision active memberships, and enforce tenant/project ownership and permissions. A protected organization-membership lookup and initial project/task authorization routes exist; production issuer configuration, membership provisioning, ownership transfer, invitations and complete role/permission policy remain open; initial project create/list and owner-managed membership routes now exist.
- [x] Implement read-only project file listing, bounded reads and literal search with .gitignore, path, symlink/reparse-point, binary and size controls.
- [x] Implement native Windows handle-relative opens and FileIdBothDirectoryInfo enumeration; retain selected root handles, reject reparse points and test path-swap/junction cases.
- [x] Implement POSIX descriptor-relative traversal and reads with no-follow/non-blocking controls.
- [x] Implement read-only local companion prototype with native folder selection, loopback-only binding, exact Origin/Host checks, one-time pairing, short-lived read-only sessions, multiple roots and revocation.
- [x] Implement initial Chrome browser pairing UI, explicit loopback permission/request flow, multi-root navigation and read-only preview; bearer tokens remain in memory only.
- [ ] Complete ODID user/tenant binding, explicit consent/audit lifecycle, signed Windows installer and validation on Windows 10 build 18362.
- [x] Implement durable tenant-scoped task records and separate append-only task events with transactional state/event writes (MongoDB replica-set/sharded transaction support required).
- [x] Atomically persist NEXUS task create/approve/cancel audit events in the same MongoDB transaction as task state and lifecycle events; audit failures roll back task mutations. A real MongoDB 7.0 replica-set integration test passed in API CI [44794850821](https://github.com/helloinnovators1/odeistudio/actions/runs/44794850821), job `mongodb-integration` (1 passed). Production Atlas connectivity and broader transaction/failure scenarios remain open.
- [x] Make readiness verify MongoDB ping plus transaction-capable topology (`setName` or `isdbgrid`); standalone MongoDB is not ready for NEXUS task/audit workflows.
- [x] Add bounded read-only NEXUS tool registry with strict schemas, injected workspace identity and unknown-tool rejection. Per-task capability enforcement and approval policy remain unchecked; this is not the complete policy/approval registry.
- [x] Add a fail-closed project authorization service: active tenant-scoped project, exact owner issuer+subject or active project membership; hide absent/unauthorized projects consistently.
- [x] Add tenant-scoped project create/list and owner-managed membership add/remove routes; require active organization membership for creator and target; use unique indexes and transactional audit writes. Ownership transfer, org administration and invitations remain open.
- [x] Add atomic planned-task persistence with ordered created → context_gathering → planning → awaiting_approval events in one MongoDB transaction; integrated project-scoped create/read/events/approve/cancel routes enforce membership/project/task access. Full role policy, project administration and production ODID integration remain open.
- [ ] Add patch application with hash/concurrency checks and explicit approval.
- [ ] Add isolated command runner with timeout/resource limits and network/filesystem policy.
- [ ] Add test runner and structured diagnostics.
- [ ] Deliver an end-to-end coding-agent vertical slice with authorized tools, patch review, execution, tests and resumable task state.
- [x] Add the first authenticated NEXUS planning API slice: verified principal + active organization membership + explicit cloud-model consent + bounded/redacted task/context + audit outcome. This is planning only, not an implementation agent.

## Phase 2 — Workspace experience

- [x] Add initial React/TypeScript Monaco workspace shell with read-only companion-backed files, multi-tabs and configurable NEXUS chat panel side (Cmd/Ctrl+I). This is not full IDE parity or an authenticated agent chat.

- [ ] Integrate the upstream React/Next.js/TypeScript/Monaco Agents and Editor experience after settling the canonical service boundary.
- [ ] Deliver full project explorer, editor, tabs and multi-card/multi-tab persistence.
- [ ] Add agent chat, task plan and approval UI.
- [ ] Add diff/review panel and isolated terminal integration.
- [ ] Add preview and diagnostics.
- [ ] Add persistent tasks and reconnect/resume behavior.

## Phase 3 — MAC and MAD

- [ ] Implement Studio MAC identity, organizations, roles and tenant administration.
- [ ] Add secret references and vault integration.
- [ ] Add environment configuration lifecycle.
- [ ] Add provider connection registry and capability discovery.
- [ ] Complete audit log integration across authentication, authorization, companion sessions, approvals and task operations; add privileged approvals and access-controlled audit queries. The insert-only Mongo audit writer is wired to organization-membership outcomes and NEXUS task create/approve/cancel transactions. Companion sessions, authentication outcomes, tool executions, audit query/export and database-level controls remain outstanding. Task and task-event reads, task-not-found/owner denials and project-owner approval denials are now instrumented; full route-by-route coverage review remains open.
- [ ] Add database-level audit writer permissions that deny update/delete, replica-set integration tests, retention/archival, monitoring and access review.
- [ ] Implement MAD operational metrics with source, freshness, aggregation and ownership definitions.

## Phase 4 — Integrations and agent maturity

- [ ] Integrate GitHub App and webhook verification.
- [ ] Integrate ODEI AI gateway, model routing, quotas and cost attribution.
- [ ] Implement provider adapters by verified capability and account/product scope.
- [ ] Add multi-agent orchestration and specialist agents.
- [ ] Add remote isolated workspaces and background tasks.

## Phase 5 — Ecosystem expansion

- [ ] Add website and app generation workflows.
- [ ] Add chatbot and AI integration builder.
- [ ] Add mobile development workflows.
- [ ] Add templates, extension SDK and marketplace.
- [ ] Add enterprise deployment, compliance and support operations.

## Security automation

- [x] Add scheduled/manual/push/PR security workflow for Gitleaks, pip-audit, npm audit and CodeQL for Python plus TypeScript.
- [x] Add weekly Dependabot update proposals for GitHub Actions and Python dependencies.
- [x] Verify all security jobs on the latest corrected audit-store head: [44776939169](https://github.com/helloinnovators1/odeistudio/actions/runs/44776939169).
- [ ] Continue triaging CodeQL and dependency alerts; never treat scanner configuration or a successful run as a clean security certification.

## Release gates

No phase is complete because its screens exist. Each capability needs working behavior, server-side authorization, tests, observability, documentation and failure handling. Production deployment additionally requires backup/restore, incident response, security review, retention controls and operational ownership.

## Latest evidence

- Current evidence commit: `b44d732c884475d469527b001d88216feaa0ae05`.
- API/web CI: [44776939214](https://github.com/helloinnovators1/odeistudio/actions/runs/44776939214) — all five jobs successful.
- Security CI: [44776939169](https://github.com/helloinnovators1/odeistudio/actions/runs/44776939169) — all four jobs successful.
- Audit writer tests include successful append/redaction, invalid identity/action/outcome/timestamp, metadata bounds and index initialization. These tests passed as part of the API CI run.
- Local Desktop folder scanning has not been performed; it requires running the companion locally and explicit folder selection by the user.


## Latest continuation — membership audit integration

- Added Mongo-backed audit index initialization to API startup when a database is configured. Startup fails rather than serving an API without the configured audit collection/indexes; startup cleanup closes the HTTP and Mongo clients if initialization fails.
- Wired the organization-membership route to append success, denial and malformed-record outcomes before returning a result. Audit storage absence or append failure returns 503 (`AUDIT_STORE_UNAVAILABLE`); authorization results are not returned unaudited.
- Added route tests for successful, denied and malformed-record audit events, plus missing/failing audit persistence. These tests passed in API/web CI [44778664819](https://github.com/helloinnovators1/odeistudio/actions/runs/44778664819) on commit `6405e81acbb0c0cec82a7a875ab0ccbf004b544a`.
- This is only a narrow membership authorization audit integration. Authentication failures, companion pairing/revocation, task and tool actions, audit querying/export, database role-level immutability, retention and replica-set integration tests remain open.

- Corrected-head security workflow [44778654256](https://github.com/helloinnovators1/odeistudio/actions/runs/44778654256) passed all four jobs: Gitleaks, pip-audit, npm audit and CodeQL Python/TypeScript.


## Latest NEXUS planning API increment

- Added `POST /api/v1/organizations/{organization_id}/nexus/plan` on the implementation branch. It requires verified identity, active organization membership and explicit cloud-model consent; bounds task/context; invokes the existing server-side Responses planning service off the async event loop; and audits success/failure without persisting user task/context/plan text.
- Verified on commit `97200eba263161595d4bef5193df409acf768dc7`: API Ruff/pytest passed on Ubuntu and Windows with Python 3.10 and 3.12; web tests/build passed; CodeQL, Gitleaks, Python dependency audit and web dependency audit passed. API/web run [44782893597](https://github.com/helloinnovators1/odeistudio/actions/runs/44782893597); security run [44782893818](https://github.com/helloinnovators1/odeistudio/actions/runs/44782893818). The endpoint does not write files, run commands or persist a resumable task; passing CI does not establish production readiness.


## Latest project authorization and planned-task persistence increment

- Added `require_project_access` with tenant-scoped active-project lookup, exact owner identity matching, active project-membership lookup and indistinguishable not-found responses for missing/unauthorized projects.
- Added `MongoTaskStore.create_planned`: it validates the initial task and non-empty plan, persists the approval-ready task and four ordered lifecycle events atomically, and rolls back on any event insert failure.
- Added focused service tests for project authorization and task lifecycle/rollback. The initial project-scoped task HTTP API is now implemented; project administration, patch/write tools and command runner remain unimplemented.


## 2026-11-20 increment — project-scoped NEXUS task API

- [x] Initialize durable task/event indexes during API startup.
- [x] Add project-authorized task creation with explicit cloud-model consent.
- [x] Persist plans as approval-ready tasks and ordered lifecycle events.
- [x] Add task read, explicit approval and cancellation endpoints with optimistic concurrency.
- [x] Add audit append operations and focused route tests.
- [x] Make task persistence, lifecycle events and audit append atomic through one MongoDB transaction; real replica-set integration passed in API CI run 44794850821.
- [x] Add durable ordered task-event retrieval with bounded pagination and a reconnectable version cursor.
- [x] Add project creation and membership administration (initial owner-managed lifecycle API; no ownership transfer or invitation flow).
- [ ] Implement patch proposal/review/apply, isolated execution, validation and bounded repair.
- [ ] Build Monaco-based IDE, agent window, streaming chat, CLI, background workers and cloud agents.


## Latest holistic scan and atomic-audit remediation

- Re-scanned the live branch tree and PR diff: 165 tree entries, 57 changed files versus `main`, 121 commits at the scan head. Confirmed the canonical docs, API, companion, browser prototype, tests and CI workflows exist. Latest scan evidence was branch head `f15df4d4f2edcbb49b24d4283d1a3456f1fc11ed`; implementation commits below supersede that scan head.
- Found a consistency defect: project-scoped task create/approve/cancel persisted task state and lifecycle events before separately appending audit events. An audit failure could therefore return an error after the task mutation had committed.
- Corrected the persistence boundary: `MongoAuditEventStore.append` now accepts an optional Mongo session; `MongoTaskStore.create_planned` and `transition` append audit records inside the same transaction as task state and lifecycle events; API startup injects the shared audit store; NEXUS routes no longer audit those mutations after commit.
- Added tests that prove successful task+audit commits and rollback of task state/lifecycle events when audit insertion fails. The route fakes were updated to exercise the new call contract. The task/task-event read and denial route tests passed in API/web CI [44794668471](https://github.com/helloinnovators1/odeistudio/actions/runs/44794668471) on commit `a907131fe2b03d66b9ff8d0f3ee821e6fda8e595` (Ubuntu 125 passed/4 skipped; Windows 127 passed/2 skipped). Security CI [44794668478](https://github.com/helloinnovators1/odeistudio/actions/runs/44794668478) also passed all four jobs.
- This does not yet provide full audit coverage. Selected task/task-event reads and task authorization denials are instrumented; companion pairing/revocation, authentication outcomes and tool execution remain open. DB-level audit immutability, retention/export and monitoring remain release gates; the real MongoDB replica-set transaction test now passes in CI.

- Extended NEXUS audit coverage to successful task/task-event reads and task-not-found/owner and project-owner approval denials. Added route assertions; these newest route-hook changes await latest-head CI.

- Added `tests/test_task_store_mongodb_integration.py` and a dedicated CI job that starts a disposable MongoDB 7.0 replica set and verifies real task/audit commit and rollback. The workflow run for the integration job is pending; do not mark real-server transaction verification complete until it passes.
- Fixed the API CI pull-request path filter to include `apps/web/**`, so web changes trigger the web tests and production build on PRs.

- Security workflow for the 8fe integration-test commit was cancelled by a later push; do not count it as a pass. A new security scan must complete on the latest branch head.

- Full API CI [44794850821](https://github.com/helloinnovators1/odeistudio/actions/runs/44794850821) passed all six jobs on `8fe8fd1f6f924919cb922e96a5c255017abb5976`: four OS/Python matrix jobs, web tests/build, and real MongoDB 7.0 replica-set integration. The integration test reported `1 passed in 0.24s`.

- Readiness tests passed in API CI [44795590882](https://github.com/helloinnovators1/odeistudio/actions/runs/44795590882) on commit `18b6f31c3c31695d092a0ef5e6a7936f5337f0c1`; the full six-job run passed the four-way Python matrix, web tests/build and MongoDB replica-set integration.

- [x] Emit semantic task lifecycle events for approval, cancellation, completion, failure and expiry; intermediate transitions use `task.status_changed`. Parameterized tests passed in API CI [44796392625](https://github.com/helloinnovators1/odeistudio/actions/runs/44796392625); security CI [44796427460](https://github.com/helloinnovators1/odeistudio/actions/runs/44796427460) passed all four checks.


## Project lifecycle and membership increment (2026-11-20)

- Added `POST/GET /api/v1/organizations/{organization_id}/projects` for tenant-scoped project creation and caller-visible listing. Active organization membership is required; creator becomes project owner.
- Added owner-only `PUT/DELETE /api/v1/organizations/{organization_id}/projects/{project_id}/members`. Targets must already be active organization members; removals are soft status changes; project owner is implicit and cannot be removed or duplicated as a member.
- Added unique project and membership indexes during API startup. Project creation and membership changes append audit records in the same MongoDB transaction as the mutation; authorization denials are audited.
- Added route tests for create/list/add/remove and rejection of a target without active organization membership. These latest tests and changes are pending CI; this item is implemented but not marked verified until current-head API and security workflows pass.
- Remaining boundaries: no org membership provisioning, project ownership transfer, invitation/acceptance workflow, arbitrary project roles, patch/write API, shell execution, IDE integration or local desktop scan.


## IDE workspace shell increment (2026-11-20)

- Replaced the basic file-preview page with a first Monaco read-only workspace shell, multi-file tabs, activity rail, explorer, bottom Problems/Output/Terminal surfaces and NEXUS panel shell.
- Implemented Command+I (macOS) / Ctrl+I (Windows/Linux) toggle and persisted Left/Right chat-panel setting (default Right); helper tests cover persistence, invalid storage, shortcut recognition and Monaco language mapping.
- Added `docs/IDE_WORKSPACE.md` and linked it from the documentation index.
- API/web CI [44803547712](https://github.com/helloinnovators1/odeistudio/actions/runs/44803547712) passed all six jobs on `d6aa775abd516ea4aa308b43b224fac995c30b30`: four OS/Python matrix jobs, 9 Vitest tests, Vite production build and MongoDB replica-set integration.
- The panel is not an authenticated chat yet; no streaming, patch editing, shell execution, LSP, Git, cloud agents or native desktop package is implied. The editor and companion remain read-only.
