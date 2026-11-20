# ODEI Studio Implementation Roadmap

This roadmap is ordered by dependencies. Status is updated only from repository artifacts and completed test evidence. A checked item means the described artifact or test exists; it does not imply production readiness. A design document alone does not count as an implemented capability.

## Phase 0 — Repository and security baseline

- [x] Verify repository access and default branch.
- [x] Establish architecture and initial MAC/provider requirements.
- [x] Add canonical documentation index and ecosystem specifications.
- [x] Audit the upstream Studio/ecosystem source tree and preserve all 68 Markdown/text source documents with provenance (47 path-preserving mirrors and 21 curated snapshots); complete target-repository inventory remains ongoing.
- [ ] Rotate any credential previously exposed in project setup material and verify rotation in the source environment.
- [x] Add linting and GitHub Actions CI (Ruff + pytest) on Ubuntu/Windows and Python 3.10/3.12.
- [x] Add secret scanning (Gitleaks), Python dependency auditing (pip-audit), web dependency auditing (npm audit) and CodeQL for Python/TypeScript.
- [x] Verify the latest API/web CI on corrected audit-store head: [44776939214](https://github.com/helloinnovators1/odeistudio/actions/runs/44776939214) — Ubuntu/Windows × Python 3.10/3.12 and web tests/build all passed on `b44d732c884475d469527b001d88216feaa0ae05`.
- [x] Verify the latest security workflow on the same head: [44776939169](https://github.com/helloinnovators1/odeistudio/actions/runs/44776939169) — Gitleaks, pip-audit, npm audit and CodeQL Python/TypeScript all passed.
- [ ] Continue reviewing scanner alerts and dependency changes; successful runs are evidence for one commit, not a permanent security certification.

## Phase 1 — NEXUS foundation

- [x] Scaffold Python/FastAPI backend foundation.
- [ ] Select and scaffold the canonical frontend after reconciling the upstream Next.js/Monaco Agents and Editor application. Current React/TypeScript/Vite client is an initial read-only companion workspace, not the full editor.
- [x] Add configuration validation and safe environment handling.
- [x] Implement fail-closed RS256/JWKS verification and protected `/api/v1/auth/me` identity route.
- [ ] Connect a confirmed production ODID issuer/audience/JWKS contract, provision active memberships, and enforce tenant/project ownership and permissions. A protected read-only organization-membership lookup exists; production issuer configuration, membership provisioning and project authorization do not.
- [x] Implement read-only project file listing, bounded reads and literal search with .gitignore, path, symlink/reparse-point, binary and size controls.
- [x] Implement native Windows handle-relative opens and FileIdBothDirectoryInfo enumeration; retain selected root handles, reject reparse points and test path-swap/junction cases.
- [x] Implement POSIX descriptor-relative traversal and reads with no-follow/non-blocking controls.
- [x] Implement read-only local companion prototype with native folder selection, loopback-only binding, exact Origin/Host checks, one-time pairing, short-lived read-only sessions, multiple roots and revocation.
- [x] Implement initial Chrome browser pairing UI, explicit loopback permission/request flow, multi-root navigation and read-only preview; bearer tokens remain in memory only.
- [ ] Complete ODID user/tenant binding, explicit consent/audit lifecycle, signed Windows installer and validation on Windows 10 build 18362.
- [x] Implement durable tenant-scoped task records and separate append-only task events with transactional state/event writes (MongoDB replica-set/sharded transaction support required).
- [x] Add bounded read-only NEXUS tool registry with strict schemas, injected workspace identity and unknown-tool rejection. Per-task capability enforcement and approval policy remain unchecked; this is not the complete policy/approval registry.
- [x] Add a fail-closed project authorization service: active tenant-scoped project, exact owner issuer+subject or active project membership; hide absent/unauthorized projects consistently. Project CRUD and membership administration remain open.
- [x] Add atomic planned-task persistence with ordered created → context_gathering → planning → awaiting_approval events in one MongoDB transaction. The HTTP route and end-to-end project/task authorization integration remain open.
- [ ] Add patch application with hash/concurrency checks and explicit approval.
- [ ] Add isolated command runner with timeout/resource limits and network/filesystem policy.
- [ ] Add test runner and structured diagnostics.
- [ ] Deliver an end-to-end coding-agent vertical slice with authorized tools, patch review, execution, tests and resumable task state.
- [x] Add the first authenticated NEXUS planning API slice: verified principal + active organization membership + explicit cloud-model consent + bounded/redacted task/context + audit outcome. This is planning only, not an implementation agent.

## Phase 2 — Workspace experience

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
- [ ] Complete audit log integration across authentication, authorization, companion sessions, approvals and task operations; add privileged approvals and access-controlled audit queries. The insert-only Mongo audit writer is now wired to organization-membership success, denial and malformed-record decisions, but companion/session/task hooks and the remaining controls are outstanding.
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
- Added focused service tests for project authorization and task lifecycle/rollback. These are service/persistence increments only. No task HTTP endpoint, project administration API, patch/write tool or command runner is exposed yet.


## 2026-11-20 increment — project-scoped NEXUS task API

- [x] Initialize durable task/event indexes during API startup.
- [x] Add project-authorized task creation with explicit cloud-model consent.
- [x] Persist plans as approval-ready tasks and ordered lifecycle events.
- [x] Add task read, explicit approval and cancellation endpoints with optimistic concurrency.
- [x] Add audit append operations and focused route tests.
- [ ] Make task persistence and audit append atomic through a shared transaction/outbox.
- [ ] Add project creation and membership administration.
- [ ] Implement patch proposal/review/apply, isolated execution, validation and bounded repair.
- [ ] Build Monaco-based IDE, agent window, streaming chat, CLI, background workers and cloud agents.
