# ODEI Studio Implementation Roadmap

This roadmap is ordered by dependencies. Status must be updated only with repository evidence.

## Phase 0 — Repository and security baseline
- [x] Verify repository access and default branch.
- [x] Establish architecture and initial MAC/provider requirements.
- [x] Add canonical documentation index and ecosystem specifications.
- [ ] Inspect complete source tree and CI configuration.
- [ ] Rotate any credential previously exposed in project setup material.
- [ ] Add secret scanning, linting and baseline CI.

## Phase 1 — NEXUS foundation
- [ ] Select and scaffold backend/frontend workspace.
- [ ] Add configuration validation and safe environment handling.
- [ ] Implement authentication and tenant-aware project ownership.
- [ ] Implement project file listing, bounded reads and search.
- [ ] Implement durable task records and task event stream.
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
