# ODEI NEXUS — AI Software Engineering Agent

**Priority:** First major product implementation.  
**Status:** Initial planning service, bounded read-only Responses API tool loop, secure workspace indexing primitives and an authenticated planning-only API are committed. No authenticated execution-agent API, mutating tools or sandbox is implemented yet.

## Mission
NEXUS is the repository-aware coding agent at the heart of ODEI Studio. It turns a developer's goal into a reviewable, tested set of code changes while respecting workspace permissions and execution policy.

## Core capabilities
1. Project onboarding and repository inventory.
2. File, symbol and semantic search.
3. Context selection with token/cost budgets.
4. Task clarification, planning and dependency ordering.
5. Multi-file read, patch and edit operations.
6. Command execution in an isolated workspace.
7. Test/build/lint execution and diagnostics parsing.
8. Failure analysis and bounded repair loops.
9. Diff presentation, review summaries and risk analysis.
10. Git branch/commit/PR workflows after explicit authorization.
11. Durable task history, cancellation and resumability.
12. Specialist agents for research, implementation, testing, security and review.

## Agent lifecycle
`created → context_gathering → planning → awaiting_approval → executing → validating → repairing → review_ready → completed`

Additional terminal states: `failed`, `cancelled`, `expired`. Every transition is persisted and authorized server-side.

## Current implementation
- `services/planning.py` calls the OpenAI Responses API through an injected client, with bounded task/context inputs and no tools enabled. Its output is an untrusted proposal only.
- `model_client.py` creates a server-side OpenAI client from `OPENAI_API_KEY` and requires a configured `ODEI_MODEL`.
- `services/tasks.py` defines task states, legal transitions, terminal states, plan-before-approval and optimistic version checks.
- `services/task_store.py` persists tasks in MongoDB with organization-scoped reads/writes, optimistic version matching and atomic status-change event append. Project-scoped task creation and approve/cancel transitions also insert the corresponding audit event in the same MongoDB transaction; audit failure rolls back task state and lifecycle events. The caller must enforce organization membership and task permissions.
- `mongo_client.py` constructs a lazy PyMongo Async client from a private `MONGODB_URI`; live database connectivity has not yet been configured or tested.
- `services/project_files.py` lists, reads and searches bounded text files with common secret exclusions, GitIgnoreSpec rules and scan budgets. It is not exposed to cloud HTTP callers.
- `services/tool_registry.py` exposes only strict-schema list/read/literal-search tools against one workspace ID injected by the trusted caller; the model cannot choose a workspace. This is a read-only allowlist, not yet a complete per-task capability/approval policy engine.
- The organization-membership API now writes successful, denied and malformed-record authorization outcomes through `MongoAuditEventStore`; audit persistence failure blocks the response. Project-scoped task create/approve/cancel actions now append audit events atomically with task state and lifecycle events. Task and task-event reads append success events before returning; task-not-found/owner denials and project-owner approval denials are recorded. Authentication outcomes, companion-session actions and tool executions remain unaudited, and a full route-by-route audit coverage review is still required.
- `services/agent_runtime.py` runs a bounded Responses API tool loop (six rounds/twelve calls) with no write, shell, install, network or deployment tools. It uses stateless Responses requests (`store=False`) and replays output items locally.
- `services/secret_redaction.py` redacts common API tokens, private keys, bearer tokens, JWTs, database URI passwords and quoted secret assignments before task/context/tool text is sent to or returned from the model. This is defense-in-depth, not a full DLP guarantee.
- Both planner and agent runtime fail closed unless the trusted caller confirms explicit user consent to send task/workspace context to a cloud model. Responses application-state storage is disabled; API abuse-monitoring retention remains subject to the OpenAI account's data controls.

## Initial tool contract
- `project.list_files`: list permitted paths, honoring ignore rules and symlink policy.
- `project.read_file`: read bounded text files; enforce size and binary limits.
- `project.search`: search file names and content with result limits.
- `project.apply_patch`: apply a validated patch; record before/after hashes.
- `runtime.run_command`: execute an allowlisted or user-approved command in a sandbox.
- `runtime.get_process`: inspect status and bounded output.
- `tests.run`: run configured test commands and return structured results.
- `git.diff`: produce reviewable changes.
- `git.status`: report repository state.
- `git.commit` / `git.push`: require explicit user authorization and scoped credentials.

Only the initial list/read/search tools are implemented. All patch, runtime, test and Git tools remain planned and must not be exposed until authorization, approval records, sandbox isolation and audit are implemented. Tool schemas must define arguments, output, permission, timeout, resource limits, idempotency and audit behavior. Tool output and repository contents are untrusted data, never system instructions.

## Planner and execution loop
1. Parse goal and identify missing requirements.
2. Inspect project metadata and relevant files.
3. Produce a plan with file scope, commands, risks and acceptance checks.
4. Request approval for broad, destructive, networked or production-impacting work.
5. Execute one bounded step at a time.
6. Re-read changed files and inspect diffs.
7. Run tests and static checks.
8. Repair only within configured attempt/time budgets.
9. Summarize changed files, test evidence, known gaps and next steps.

Never claim a test passed when it was not run. Preserve user edits; detect concurrent modifications using content hashes and fail safely rather than overwrite.

## Runtime security
- Disposable workspace/container per task or isolated task session.
- Non-root execution, CPU/memory/disk/process/time limits.
- Network disabled by default; allowlisted egress only when approved.
- No host home-directory or secret-store mount by default.
- Credentials short-lived, scoped and injected only into the specific approved operation.
- Secret redaction in tool output, logs, traces and model context.
- Explicit approval for destructive commands, dependency scripts with elevated privileges, production deployment and external publishing.
- Kill switch, cancellation and cleanup on completion/expiry.

## Context strategy
Use layered context: project metadata and instructions → relevant file/symbol retrieval → task-specific snippets → recent tool results. Exclude secrets, generated files, dependencies and ignored paths. Track source paths and hashes for provenance. Summarize long task history without losing decisions or unresolved issues.

## API/service boundaries
The agent orchestrator owns durable task state and policy. Tool executors run in isolated workers. The model provider is accessed through a provider-neutral model gateway. Streaming events are delivered to clients through an authenticated event channel. Persist events for reconnect/resume.

## Initial vertical-slice acceptance
- User can create/open a project in a controlled workspace.
- NEXUS lists and reads permitted text files.
- NEXUS can search for a symbol/string.
- NEXUS proposes a plan before modifying files.
- User approves a bounded patch.
- Patch is applied with conflict detection and diff.
- A configured test command runs in isolation.
- Results and task history survive page refresh.
- Cancellation works and no secrets appear in output.
- Automated tests cover path traversal, oversized/binary files, concurrent edits, command timeout and authorization failure.

## Deferred capabilities
Parallel agents, remote cloud workspaces, browser automation, advanced semantic indexing, autonomous PR review and long-running background tasks are later milestones, not assumed features of the first slice.


## First authenticated planning API

The API now exposes `POST /api/v1/organizations/{organization_id}/nexus/plan` as the first authenticated NEXUS workflow slice. It requires a verified bearer principal, an active server-side organization membership and an explicit `cloud_model_consent: true` value. Task text and caller-supplied project context are bounded, secret-redacted by the planning service and sent through the server-side OpenAI Responses client with `store=false`. The route writes a tenant/actor-scoped audit outcome without storing task text, repository context or plan content. Audit failure blocks the response.

This endpoint produces a plan only. It does not connect to the local companion, inspect local files, create durable tasks, apply patches, run commands or authorize implementation. The supplied project context is untrusted caller input, not verified repository evidence. Production use still requires configured ODID issuer/audience/JWKS/client allowlist, membership provisioning, MongoDB and OpenAI credentials, plus the remaining authorization and runtime controls.


## Project-scoped task API

NEXUS now has an authenticated project-scoped task API for create, read, approve and cancel. Creation checks active organization membership and active project owner/member access, requires explicit cloud-model consent, and persists an approval-ready task with its lifecycle events. Approval is a distinct `approved` state and is deliberately not an execution trigger. Task retrieval is limited to the task owner or project owner. Mutations use optimistic version checks and append audit records.

This increment does not add file mutation, shell execution, test execution, repair, event streaming, CLI, desktop editor or cloud agents. The local companion remains read-only.


## Atomic task audit guarantee

The project-scoped task API passes a validated audit event into `MongoTaskStore`. The task document, ordered `task_events`, and audit document are inserted/updated under one MongoDB session transaction. If the audit writer is missing or its insert fails, the transaction aborts and task state remains unchanged. This guarantee depends on MongoDB replica-set or sharded-cluster transaction support; only unit/fake-transaction tests are currently available, so a live replica-set integration test remains a release gate.


## Task access audit coverage

The project-scoped task API records successful task reads and task-event reads before returning their data. It also records task-not-found/owner denials and project-owner approval denials. Task create/approve/cancel state changes remain atomically audited with their task lifecycle events. Authentication outcomes, companion pairing/revocation and tool execution are still not instrumented.
