# ODEI NEXUS — AI Software Engineering Agent

**Priority:** First major product implementation.  
**Status:** Initial planning service and read-only project indexing utilities are committed. No authenticated agent API, tool execution loop or sandbox is implemented yet.

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
- `services/tasks.py` defines task states, legal transitions, terminal states, plan-before-approval and optimistic version checks. Persistence and authenticated access are not yet wired.
- `services/project_files.py` lists, reads and searches bounded text files with common secret exclusions, GitIgnoreSpec rules and scan budgets. It is not exposed to HTTP callers.

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

Tool schemas must define arguments, output, permission, timeout, resource limits, idempotency and audit behavior. Tool output and repository contents are untrusted data, never system instructions.

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
