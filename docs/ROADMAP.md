# ODEI Studio Implementation Roadmap

This roadmap is ordered by dependencies. Status must be updated only with repository evidence.

## Phase 0 — Repository and security baseline
- [x] Verify repository access and default branch.
- [x] Establish architecture and initial MAC/provider requirements.
- [x] Add canonical documentation index and ecosystem specifications.
- [x] Audit the upstream Studio/ecosystem source tree and mirror its 68 core documentation files; complete target-repository inventory remains ongoing.
- [ ] Rotate any credential previously exposed in project setup material.
- [x] Add linting and GitHub Actions CI (Ruff + pytest) on Ubuntu/Windows and Python 3.10/3.12.
- [ ] Add secret scanning and dependency vulnerability scanning.

## Phase 1 — NEXUS foundation
- [x] Scaffold Python/FastAPI backend foundation; [ ] select and scaffold the frontend framework after reconciling the upstream Next.js/Monaco app.
- [x] Add configuration validation and safe environment handling.
- [x] Implement fail-closed RS256/JWKS verification and protected `/api/v1/auth/me` identity route.
- [ ] Connect a confirmed ODID issuer/audience/JWKS, provision active memberships, and enforce tenant/project ownership and permissions.
- [x] Implement read-only project file listing, bounded reads and literal search with .gitignore, path, symlink/reparse-point, binary and size controls.
- [x] Use native Windows handle-relative opens for file reads and `FileIdBothDirectoryInfo` enumeration; add Windows junction-exclusion and directory-handle path-swap regression tests.
- [x] Replace POSIX path-based directory enumeration with `os.fwalk`, descriptor-relative metadata/open operations, `O_NOFOLLOW` and `O_NONBLOCK`.
- [x] Add an in-memory `WorkspaceHandleRegistry` that retains Windows root handles/POSIX descriptors, performs list/read through retained handles, serializes operations and supports revocation; test root path replacement after registration.
- [ ] Implement the native folder picker/companion flow and bind opaque workspace IDs to authenticated users/tenants; protect the initial path-to-handle selection boundary.
- [x] Implement durable tenant-scoped task records and a separate append-only task event stream with transactional state/event writes.
- [ ] Add policy-controlled tool registry.
- [ ] Add patch application with hash/concurrency checks.
- [ ] Add isolated command runner with timeout/resource limits.
- [ ] Add test runner and structured diagnostics.
- [ ] Deliver end-to-end coding-agent vertical slice.

## Phase 2 — Workspace experience
- [ ] Project explorer, editor and tabs.
- [ ] Agent chat, task plan and approval UI.
- [ ] Diff/review panel and terminal.
- [ ] Preview and diagnostics.
- [ ] Persistent tasks and reconnect/resume behavior.

## Phase 3 — MAC and MAD
- [ ] Identity, organizations, roles and tenant administration.
- [ ] Secret references and vault integration.
- [ ] Environment configuration lifecycle.
- [ ] Provider connection registry and capability discovery.
- [ ] Audit log and privileged approvals.
- [ ] Operational metrics with source/freshness definitions.

## Phase 4 — Integrations and agent maturity
- [ ] GitHub App integration and webhook verification.
- [ ] Model gateway, routing, quotas and cost attribution.
- [ ] Provider adapters by verified capability.
- [ ] Multi-agent orchestration and specialist agents.
- [ ] Remote isolated workspaces and background tasks.

## Phase 5 — Ecosystem expansion
- [ ] Website and app generation workflows.
- [ ] Chatbot and AI integration builder.
- [ ] Mobile development workflows.
- [ ] Templates, extension SDK and marketplace.
- [ ] Enterprise deployment, compliance and support operations.

## Release gates
No phase is complete because its screens exist. Each capability needs working behavior, server-side authorization, tests, observability, documentation and failure handling. Production deployment additionally requires backup/restore, incident response, security review and operational ownership.
