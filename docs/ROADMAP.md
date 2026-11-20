# ODEI Studio Implementation Roadmap

This roadmap is ordered by dependencies. Status must be updated only with repository evidence.

## Phase 0 — Repository and security baseline
- [x] Verify repository access and default branch.
- [x] Establish architecture and initial MAC/provider requirements.
- [x] Add canonical documentation index and ecosystem specifications.
- [x] Audit the upstream Studio/ecosystem source tree and mirror its 68 core documentation files; complete target-repository inventory remains ongoing.
- [ ] Rotate any credential previously exposed in project setup material.
- [x] Add linting and GitHub Actions CI (Ruff + pytest) on Ubuntu/Windows and Python 3.10/3.12.
- [x] Add automated secret scanning (Gitleaks), Python dependency auditing (pip-audit), web dependency auditing (npm audit) and CodeQL for Python/TypeScript.
- [x] Complete initial Gitleaks, pip-audit, npm audit and CodeQL runs successfully; continue triaging future alerts.

## Phase 1 — NEXUS foundation
- [x] Scaffold Python/FastAPI backend foundation; [ ] select and scaffold the frontend framework after reconciling the upstream Next.js/Monaco app.
- [x] Add configuration validation and safe environment handling.
- [x] Implement fail-closed RFC 9068-style RS256/JWKS access-token verification and protected `/api/v1/auth/me` identity route.
- [ ] Obtain a production ODID issuer/JWKS/access-token contract; implement server-side membership provisioning, role/permission policy and project-level authorization only against that verified contract.
- [ ] Connect a confirmed ODID issuer/audience/JWKS, provision active memberships, and enforce tenant/project ownership and permissions.
- [x] Implement read-only project file listing, bounded reads and literal search with .gitignore, path, symlink/reparse-point, binary and size controls.
- [x] Use native Windows handle-relative opens for file reads and `FileIdBothDirectoryInfo` enumeration; add Windows junction-exclusion and directory-handle path-swap regression tests.
- [x] Replace POSIX path-based directory enumeration with `os.fwalk`, descriptor-relative metadata/open operations, `O_NOFOLLOW` and `O_NONBLOCK`.
- [x] Add an in-memory `WorkspaceHandleRegistry` that retains Windows root handles/POSIX descriptors, performs list/read through retained handles, serializes operations and supports revocation; test root path replacement after registration.
- [x] Implement a read-only `odei-companion` prototype with OS folder selection, loopback-only API, exact Origin/Host checks, one-time pairing, short-lived read-only tokens and revocation.
- [x] Support multiple explicitly selected project roots in one companion process with workspace-specific read routes.
- [x] Implement initial browser pairing UI using Chrome LNA, read-only workspace navigation and file preview; keep bearer tokens in memory only.
- [x] Implement initial browser pairing UI using Chrome LNA, read-only workspace navigation and file preview; keep bearer tokens in memory only.
- [ ] Integrate ODID user/tenant authorization, consent/audit lifecycle, signed Windows installer and Windows 10 build 18362 validation. (`loopback-network`, secure HTTPS context, explicit user gesture and `targetAddressSpace: "loopback"`), ODID user/tenant authorization, consent/audit lifecycle, signed Windows installer and Windows 10 build 18362 validation.
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

## Security automation
- [x] Add scheduled/manual/push/PR security workflow for Gitleaks, pip-audit, npm audit and CodeQL for Python plus TypeScript.
- [x] Add weekly Dependabot update proposals for GitHub Actions and Python dependencies.
- [x] Verify secret scan, Python dependency audit and web dependency audit; upgrade vulnerable Vite/Vitest tooling.
- [x] Verify initial CodeQL completion; continue triaging scheduled findings.

## Release gates
No phase is complete because its screens exist. Each capability needs working behavior, server-side authorization, tests, observability, documentation and failure handling. Production deployment additionally requires backup/restore, incident response, security review and operational ownership.
