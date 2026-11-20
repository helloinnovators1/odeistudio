# ODEI Studio Implementation Roadmap

This roadmap is ordered by dependencies. Status must be updated only with repository evidence. A checked item means the described repository artifact or test exists; it does not imply production readiness.

## Phase 0 — Repository and security baseline
- [x] Verify repository access and default branch.
- [x] Establish architecture and initial MAC/provider requirements.
- [x] Add canonical documentation index and ecosystem specifications.
- [x] Audit the upstream Studio/ecosystem source tree and preserve all 68 Markdown/text source documents with provenance.
- [ ] Rotate any credential previously exposed in project setup material; verify rotation in the source environment.
- [x] Add linting and GitHub Actions CI (Ruff + pytest) on Ubuntu/Windows and Python 3.10/3.12.
- [x] Add automated secret scanning (Gitleaks), Python dependency auditing (pip-audit), web dependency auditing (npm audit) and CodeQL for Python/TypeScript.
- [x] Complete initial Gitleaks, pip-audit, npm audit and CodeQL runs successfully on commit fe1b5673a6ff6833514ac4751cd4932347813c99.
- [ ] Verify the latest security-workflow correction on the current branch; see IMPLEMENTATION_STATUS.md for the discovered local-package audit failure and remediation commit.

## Phase 1 — NEXUS foundation
- [x] Scaffold Python/FastAPI backend foundation.
- [x] Add configuration validation and safe environment handling.
- [x] Implement fail-closed RFC 9068-style RS256/JWKS access-token verification and protected /api/v1/auth/me identity route.
- [ ] Obtain a production ODID issuer/JWKS/access-token contract; implement server-side membership provisioning, role/permission policy and project-level authorization only against that verified contract.
- [x] Implement read-only project file listing, bounded reads and literal search with .gitignore, path, symlink/reparse-point, binary and size controls.
- [x] Use native Windows handle-relative opens for file reads and FileIdBothDirectoryInfo enumeration; add Windows junction-exclusion and directory-handle path-swap regression tests.
- [x] Use POSIX os.fwalk and descriptor-relative metadata/open operations with O_NOFOLLOW and O_NONBLOCK.
- [x] Add an in-memory WorkspaceHandleRegistry that retains Windows root handles/POSIX descriptors, performs list/read through retained handles, serializes operations and supports revocation.
- [x] Implement a read-only odei-companion prototype with OS folder selection, loopback-only API, exact Origin/Host checks, one-time pairing, short-lived read-only tokens and revocation.
- [x] Support multiple explicitly selected project roots in one companion process with workspace-specific read routes.
- [x] Implement initial browser pairing UI using Chrome Local Network Access, read-only workspace navigation and file preview; keep bearer tokens in memory only.
- [ ] Integrate ODID user/tenant authorization, explicit consent/audit lifecycle, signed Windows installer and Windows 10 build 18362 validation.
- [x] Implement durable tenant-scoped task records and a separate append-only task event stream with transactional state/event writes.
- [ ] Add policy-controlled tool registry.
- [ ] Add patch application with hash/concurrency checks.
- [ ] Add isolated command runner with timeout/resource limits.
- [ ] Add test runner and structured diagnostics.
- [ ] Deliver end-to-end coding-agent vertical slice.

## Phase 2 — Workspace experience
- [ ] Integrate the upstream React/Next.js/TypeScript/Monaco Agents and Editor experience after settling the canonical service boundary.
- [ ] Deliver project explorer, editor, tabs and multi-card/multi-tab persistence.
- [ ] Add agent chat, task plan and approval UI.
- [ ] Add diff/review panel and terminal integration.
- [ ] Add preview and diagnostics.
- [ ] Add persistent tasks and reconnect/resume behavior.

## Phase 3 — MAC and MAD
- [ ] Implement Studio MAC identity, organizations, roles and tenant administration.
- [ ] Add secret references and vault integration.
- [ ] Add environment configuration lifecycle.
- [ ] Add provider connection registry and capability discovery.
- [ ] Add audit log and privileged approvals.
- [ ] Implement MAD operational metrics with source/freshness definitions.

## Phase 4 — Integrations and agent maturity
- [ ] Integrate GitHub App and webhook verification.
- [ ] Integrate ODEI AI gateway, model routing, quotas and cost attribution.
- [ ] Implement provider adapters by verified capability.
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
- [x] Verify initial secret scan, Python dependency audit, web dependency audit and CodeQL completion.
- [ ] Verify the corrected local editable-package exclusion and all security jobs on the latest branch commit.
- [ ] Continue triaging CodeQL and dependency alerts; never treat scanner configuration as a clean security certification.

## Release gates
No phase is complete because its screens exist. Each capability needs working behavior, server-side authorization, tests, observability, documentation and failure handling. Production deployment additionally requires backup/restore, incident response, security review and operational ownership.
