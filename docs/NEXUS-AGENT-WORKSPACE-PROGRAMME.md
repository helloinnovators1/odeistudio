# NEXUS agent workspace capability programme

This document separates current repository foundations from capabilities that still require implementation and backend acceptance. Cursor is a capability reference, not a UI or proprietary implementation specification.

## Product contract

NEXUS is a governed project agent inside ODEI Studio. It must make the distinction between answering, planning, inspecting, proposing changes and executing changes explicit. No mode may silently gain privileges from another mode. Every tool invocation is tenant-scoped, permission-checked, auditable and cancellable where the underlying provider supports cancellation.

## Capability matrix

| Capability | Existing foundation observed in this branch | Required end state / acceptance |
|---|---|---|
| Agent modes | Ask / Plan / Agent / Debug selector; Ask and Debug use read-only chat; Agent is restricted to attached-excerpt inspection and review-only proposals; Plan uses the approval-ready task endpoint. API mode guards and route/runtime tests are in place. Mode is included in chat audit metadata and persisted on every user and assistant conversation message; the transcript restores and displays it. | Enforce mode-scoped tool/capability registry for all future tools; enforce mode-scoped tool/capability registry for all future tools; extend Agent through approved execution only after review and explicit execution consent. |
| Context picker | Active-file excerpt and up to five explicitly selected workspace excerpts | Unified `@` picker for files, folders, terminal sessions, chats, Git diff/status, browser page and approved integrations; context preview, source provenance, token/size budget and remove controls |
| Tool execution | Inspection endpoint, patch proposals, task plans, isolated execution profiles | Typed tool registry, policy engine, scoped capabilities, tool event stream, approval prompts, timeout/rate limits, audit events and deny-by-default behavior |
| Change review | Patch proposal review and approved apply capability | Per-file and per-hunk diff, accept/reject, stale-base detection, atomic multi-file apply, conflict recovery and verified rollback |
| Recovery | Task cancellation and execution history/events | Local immutable checkpoints plus durable server task checkpoints, restore preview, rollback verification and retention controls |
| Long-running work | Durable task and execution records, polling and cancellation | Durable sessions, queue/steer/stop/resume, background agents, isolated subagents, idempotent orchestration and event replay |
| Integrations | Existing API modules for selected NEXUS/MAC/MAD operations | Governed registry for MCP servers, skills, rules and plugins; signed manifests, scopes, allowlists, approval policy, health status and revocation |
| Voice | No complete voice-agent workflow verified in this branch | Accessible dictation and realtime voice sessions, explicit microphone consent, transcript controls and equivalent text-only operation |
| Privacy and safety | Explicit cloud-model consent, excerpt filtering and in-memory browser tokens | Per-project data policy, provider/model disclosure, retention controls, redaction, secret exclusion, tenant isolation and auditable consent |
| Multi-hosting | Electron preload/IPC bridge and cloud-backed web UI | Host capability contract with OS adapters (macOS, Windows, Linux), browser-safe capability subset and separately governed cloud execution workers |

## Mode permission contract

- **Ask:** read-only conversation and explicitly attached context. No file writes, shell commands or external side effects.
- **Plan:** read-only discovery and structured task plan. No execution or file mutation.
- **Agent:** may propose and apply changes only through explicit policy checks and review/approval. Shell and external tools require their own capability grants.
- **Debug:** diagnostic read-only tools by default; any remediation is converted into a reviewed proposal or separately approved execution.

The UI mode label is never an authorization boundary. The API must enforce mode and capability scopes on every request.

## Host and security architecture

1. The web client receives only browser-safe capabilities. It must never be treated as a trusted source of native OS privileges.
2. A signed native host exposes a narrow, versioned capability bridge. Electron IPC validates the sender frame and origin; every new capability must have input validation, path/symlink protections, bounded output and explicit authorization.
3. macOS, Windows and Linux implementations are separate host adapters behind the same capability contract. Host-specific functionality is reported as unavailable rather than simulated.
4. Cloud execution is a separate service boundary with tenant-scoped immutable snapshots, isolated workers, server-owned policy and short-lived credentials. It is not an extension of browser privileges.
5. MCP, skills and plugins run through a governed registry. Untrusted integration output is data, never instructions; secrets are never passed to arbitrary tools by default.

## Delivery gates

### P0 — identity and host safety
- Persist desktop ODID enablement in Electron userData, default false, never store tokens in settings.
- Gate callback handling and sign-in on the desktop setting and complete valid OAuth configuration.
- Turning the setting off clears in-memory identity and project state.
- Keep web-host auth behavior independent.
- Test fresh install, restart persistence, off-state callback, on-state valid/invalid configuration, sign-out, and web-host regression.

### P1 — coherent interaction model
- [x] Initial explicit Ask / Plan / Agent / Debug selector and server-side route/runtime boundaries; mode is included in chat audit metadata. Conversation-turn metadata and complete capability registry remain open.
- [ ] Deliver unified context picker and provenance preview.
- Standardize tool event schema and streamed execution timeline.
- Add per-file review and transactional multi-file apply.

### P2 — durable agent runtime
- Durable sessions, checkpoints, queue/steer/stop/resume and replay.
- Subagent orchestration with budgets, delegation policy and aggregate audit trail.
- Background execution with cancellation and cleanup guarantees.

### P3 — integrations and voice
- Governed MCP/skills/plugins registry and project rules.
- Voice dictation and realtime voice with consent, transcripts and text fallback.

### P4 — multi-host production acceptance
- Native host adapters and signed installers for each supported OS.
- Cloud worker isolation, secret management, observability, backup/restore and disaster-recovery drills.
- Browser, desktop and cloud capability matrix with automated security and accessibility tests.

## Evidence and release discipline

A capability is complete only when its backend enforcement, UI behavior, tests and supported-host acceptance are all demonstrated. A visible control or client-side mode selector alone is not acceptance. Do not mark a row complete from documentation or mock UI.
