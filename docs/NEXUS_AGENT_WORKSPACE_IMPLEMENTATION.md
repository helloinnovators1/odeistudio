# NEXUS Agent Workspace — Implementation and Acceptance Plan

**Reviewed:** 2026-11-23  
**Baseline:** `main` at `45d968d8f4af82ec2d9520da37ded2485e21f87e`  
**Scope:** NEXUS chat, repository context, agent tool execution, editing, verification, orchestration and operational acceptance.

This document separates shipped code from a proposed target architecture. A passing test proves only the tested behavior on the tested commit; it does not prove real ODID integration, production deployment or hostile-code isolation.

## 1. Existing implementation

The repository currently includes:
- ODID Authorization Code + PKCE browser foundation and in-memory token lifecycle.
- Server-authorized organization and project discovery.
- Consent-gated project chat, streaming and tenant/owner-scoped persisted conversations.
- Bounded inspection tools over explicitly attached excerpts, secret redaction and review-only patch proposals.
- Durable task planning and owner approval; approval is not execution.
- One-file signed, challenge-bound local companion application.
- Approved-profile workspace snapshot execution, durable run/event/lease state, worker integration, cancellation, bounded artifacts and project history.
- MAC environment revision/approval foundations and MAD telemetry/incident workflows.

Current hard boundaries:
- Inspection is limited to one through five explicitly attached excerpts; no automatic repository index or semantic retrieval is present.
- Proposal storage can represent multiple files, but companion application is single-file and has no durable multi-file transaction journal/rollback/crash recovery.
- Task approval and execution are distinct. Execution is a separate approved-profile workflow, not a general model-controlled terminal.
- Browser Stop/cancel does not guarantee upstream provider cancellation.
- ODID issuer/client/audience/scopes/JWKS/CORS and production provider infrastructure require real environment configuration and staging acceptance.
- MAC/MAD code and CI are not proof of production deployment or provider integration.

## 2. Increment delivered by the workspace-context branch

The current implementation branch adds an explicit context picker:
- User selects individual files from the paired local companion's file listing.
- No file is read merely because it exists in the workspace.
- At most five files are selected.
- Each excerpt is limited to 8,000 characters and aggregate path/content to 40,000 characters.
- The current unsaved editor buffer takes precedence over a disk read for the active file.
- Unsafe relative paths, case-insensitive duplicate paths and oversized context are rejected.
- Context loading checks cancellation before and after each read.
- Selected paths are reset when the companion workspace, organization, project or identity changes; the active-file attachment and inspection toggle reset when the editor buffer changes.
- Cloud transmission still requires the existing explicit consent control.
- Read-only inspection and review-only proposal semantics remain unchanged.

This is deliberately not an implicit full-workspace upload and does not claim semantic indexing.

## 3. Target architecture

### 3.1 Workspace intelligence service
- Project-authorized file inventory and metadata.
- Exact search (literal, regex and symbol-aware).
- Language-aware symbol extraction and reference graph.
- Syntactic chunking, content hashes and incremental index updates.
- Optional embeddings and semantic retrieval behind a separately configured model/vector provider.
- Provenance on every retrieved chunk: project, path, revision/hash, line range and index version.
- Explicit exclusion policies for secrets, generated files, vendor trees, ignored files and binary content.
- Per-project access control, tenant isolation, deletion propagation, retention and index rebuild.
- Context budget and retrieval diversity/ranking; no hidden files or unbounded repository dumps.

### 3.2 Agent orchestrator
- Typed tool registry with schemas, versioning and capability checks.
- Bounded model/tool loop with per-turn, per-tool, wall-clock and token/cost limits.
- Explicit action states: proposed, awaiting approval, approved, executing, completed, failed, cancelled and recovered.
- Durable idempotency keys and request correlation.
- Cancellation propagated to actual provider requests, child processes and workers where supported.
- Model output, repository content and tool results remain untrusted data.
- Audit events record actor, project, tool, policy decision, outcome and correlation ID without storing source or secrets.

### 3.3 Workspace editing
- Multi-file patch manifests with normalized paths, base/result hashes and preconditions.
- Review UI showing exact adds/changes/deletes and per-file diffs.
- Durable transaction journal and before-images.
- Staging area, atomic per-file replacement, ordered commit and reverse rollback.
- Crash recovery and idempotent receipts; conflicting external edits fail closed.
- Windows reparse-point/handle-relative and POSIX symlink/descriptor-relative parity.
- No automatic apply until all preconditions and approval versions match.

### 3.4 Verification loop
- Agent may propose approved build/test/lint commands from deployment-owned profiles.
- Execution happens only in the isolated worker, never in the browser or API process.
- Collect exit code, bounded stdout/stderr, duration, test summaries and artifact digests.
- Failed verification returns structured diagnostics to the agent.
- A repair iteration creates a new proposal/version and requires policy re-evaluation.
- Hard iteration, time, cost and concurrency limits; no claim of success without evidence.
- Human review remains required before merge/deploy.

### 3.5 Multi-agent workspace
- Durable agent jobs with scoped project/task/branch ownership.
- Independent worktrees or isolated workspace snapshots.
- Specialist roles (research, implementation, test, review) with least-privilege tools.
- Task dependency graph, concurrency controls and conflict detection.
- Checkpoints, resumability, cancellation, retries and attribution.
- Parent agent cannot silently grant child permissions; each tool call is re-authorized.
- Human-visible agent activity timeline and final artifact/review handoff.

### 3.6 Browser and external integrations
- Browser automation in a separately isolated environment.
- Domain allowlists, navigation and download restrictions, credential boundaries and screenshot/video evidence.
- MCP server registry with tenant-scoped connection grants, OAuth, schema validation, quotas and audit.
- Git provider operations through explicit least-privilege credentials and branch protections.
- Cloud/background agent workers, web console, CLI and event-driven automation are separate deployable capabilities.

## 4. Security invariants

1. Every read, write, tool call, task, conversation, artifact and event is authorized server-side for the verified identity, organization and project.
2. A client-provided path, role, project ID, file hash or approval claim is never authority.
3. Cloud consent is explicit, visible and scoped to the data being transmitted.
4. Local companion pairing is not ODID authentication and is not cloud consent.
5. Model-generated instructions cannot change policy or authorize tools.
6. File content, retrieved chunks, command output, browser pages and MCP results are untrusted.
7. Secret scanning and redaction are defense in depth, not proof that a workspace is secret-free.
8. No arbitrary shell, network or host filesystem access in the API/browser process.
9. Production execution requires a dedicated hardened isolation boundary appropriate for hostile code; ordinary OCI flags alone are insufficient.
10. Every mutation has optimistic preconditions, idempotency, an auditable actor and a recovery story.
11. Tool and agent outputs are bounded; sensitive payloads are excluded from logs and audit metadata.
12. A successful process exit is not equivalent to product acceptance, merge or deployment.

## 5. Delivery sequence and release gates

| Sequence | Deliverable | Acceptance evidence |
|---|---|---|
| 0 | Explicit multi-file context picker | Unit tests for path/size/budget/cancel and authenticated browser flow |
| 1 | Whole-repository exact search and metadata index | Tenant-isolation tests, ignored/secret-file tests, stale-index and deletion tests |
| 2 | Semantic/symbol/dependency retrieval | Provenance, ranking, incremental update, privacy and retrieval-quality tests |
| 3 | Multi-file transactional companion apply | Crash/fault injection, concurrent edit, Windows/POSIX, rollback and recovery tests |
| 4 | Typed agent tool orchestration | Tool authorization, idempotency, cancellation, prompt-injection and audit tests |
| 5 | Integrated test-and-repair loop | Real worker test jobs, bounded iterations, diagnostic provenance and human review |
| 6 | Agent workspace and subagents | Independent workspaces, conflict, cancellation, resumability and least-privilege tests |
| 7 | Cloud agents, browser and MCP | Isolation, provider contract, credential, domain allowlist and external E2E tests |
| 8 | CLI, Git/PR and automation | Branch protection, permission scope, webhook replay and release-gate acceptance |
| 9 | Production readiness | Real ODID, MongoDB, KMS/secrets, hardened worker, backups/restore, staging, monitoring, canary and rollback |

## 6. Current external gates

- Real ODID issuer/client registration, callback, scopes/resource, API issuer/JWKS and CORS.
- Production MongoDB topology, encryption/key management, backup/PITR and restore drill.
- Dedicated worker fleet, immutable images, hostile-code isolation, egress policy and operational recovery.
- Real secret-manager and deployment-provider adapters.
- Authenticated browser acceptance, accessibility and visual regression.
- Repository branch protection and independent security review.
- Signed companion installer/update and target Windows device acceptance.
- Staging deployment, migration, canary, monitoring and rollback evidence.

## 7. Decision rule

Do not mark a capability complete because a UI control exists, a plan was approved, a patch was generated, a process exited zero, a PR is mergeable, or a workflow passed on a different SHA. Mark it complete only when implementation, tests, security review, exact-head CI and required external acceptance evidence all exist.
