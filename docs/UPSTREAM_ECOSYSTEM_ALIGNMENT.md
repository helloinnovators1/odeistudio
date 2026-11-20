# Upstream Ecosystem Alignment — ODEI Studio

**Purpose:** consolidate the relevant product requirements, implementation evidence and engineering lessons from the ODEI Multi-Ecosystem repository into this repository's canonical documentation.
**Source repository:** [infoedutechos/ODEI-Multi-Ecosystem](https://github.com/infoedutechos/ODEI-Multi-Ecosystem)
**Source tree inspected:** `b9878e8dcc34942ec10fa5fddea34028a5456b42` (2026-09-18 tree)
**Target repository:** [helloinnovators1/odeistudio](https://github.com/helloinnovators1/odeistudio)
**Status:** source audit completed; selected architecture and requirements incorporated here. This document is not a claim that the upstream implementation has been copied, deployed or independently tested in this repository.

---

## 1. Executive finding

The source repository contains a substantial prior ODEI Studio implementation under `ODEI Studio/`, alongside ecosystem-level services and product documentation. It provides valuable implementation evidence that was not represented in the initial Python-only backend foundation of this repository.

The source includes:

- A Next.js/React Studio experience with Agents and Editor surfaces, Monaco components, project explorer, tabs, build results and a VS Code extension.
- A Node.js/TypeScript API, deterministic build pipeline, shared domain types and a multi-agent orchestration package.
- A local `@odei/path-bridge` companion for user-selected absolute filesystem roots.
- A ModelRouter client that connects Studio to the separate ODEI AI gateway.
- VS Code/Code-OSS integration scripts and a product-branded extension.
- A separate Studio website/MAC surface, distinct from the Agents application and editor.
- Ecosystem-level documentation covering Studio audits, workspace access, hosting, identity, MACs, AI gateway, provider boundaries and operational honesty.

**Architecture decision:** treat this upstream implementation as a first-class product reference and migration source. Do not blindly merge its Node/TypeScript stack into the current FastAPI backend. First define one canonical runtime boundary and migrate capabilities deliberately, with tests and compatibility contracts. Avoid running two competing APIs, two task stores or two authentication systems for the same product.

## 2. Source inventory and evidence

### 2.1 Studio product source

The inspected source paths include:

| Source path | Evidence / capability |
|---|---|
| `ODEI Studio/apps/web/` | React/Next.js Agents and Editor experiences |
| `ODEI Studio/apps/web/src/components/editor/` | Monaco editor, tabs, explorer, file viewer, panels and command palette |
| `ODEI Studio/apps/web/src/lib/fs-access.ts` | Browser File System Access API integration |
| `ODEI Studio/apps/web/src/lib/path-bridge-client.ts` | Browser client for the local path companion |
| `ODEI Studio/apps/web/src/lib/desktop-bridge.ts` | Cursor/VS Code URI handoffs for local open, Git clone and Remote-SSH |
| `ODEI Studio/packages/api/` | Express API and ODEI AI gateway client |
| `ODEI Studio/packages/orchestrator/` | Agent registry, task queue, goal decomposition and events |
| `ODEI Studio/packages/path-bridge/` | Local filesystem companion and path security checks |
| `ODEI Studio/extensions/odei-studio/` | VS Code-compatible extension |
| `ODEI Studio/vscode/` and `scripts/` | Code-OSS fork, branding and integration scripts |
| `ODEI Studio/docs/` | Product-level scope, architecture and documentation index |

The source README describes the Agents application at `/app`, the Editor at `/editor`, the Studio API on port 4000, and the path bridge on port 4010. These are source-repository runtime conventions, not ports already configured or verified in this repository.

### 2.2 Ecosystem documentation source

The source repository also contains relevant operational documentation:

- `docs/studio/STUDIO_DEEP_AUDIT.md`
- `docs/studio/STUDIO_EDITOR_WORKSPACE_SCAN.md`
- `docs/studio/STUDIO_HOLISTIC_SCAN_REMEDIATION.md`
- `docs/studio/STUDIO_MAC_FULLY_OPERATIONAL_INVESTIGATION.md`
- `docs/studio/STUDIO_MAC_REMEDIATION.md`
- `docs/studio/STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md`
- `docs/studio/STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md`
- `docs/studio/STUDIO_EDITOR_PHASE_2B.md`
- `docs/studio/STUDIO_EDITOR_PHASE_2C.md`
- `docs/studio/STUDIO_MODELROUTER_VERIFY.md`
- `docs/ai/ODEI_AI_OPERATING_SYSTEM.md`
- `docs/ai/ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`
- `docs/ecosystem/ODEI_MULTI_ECOSYSTEM_WHOLE.md`
- `docs/ecosystem/PRODUCT_MAC_CONSOLES.md`
- `apps/multi-ecosystem/HOSTING.md`
- `apps/multi-ecosystem/HONESTY.md`

These source documents have different dates and maturity assumptions. The current repository should retain the useful product requirements while recording its own implementation evidence separately.

## 3. Product surface map — keep these distinct

ODEI Studio has several related but separate surfaces:

1. **Studio website:** public product information, documentation and entry points.
2. **Agents application:** goal composer, plans, build progress, generated artifacts, AI interaction and task history.
3. **Editor workspace:** local or remote project selection, Explorer, tabs, Monaco, diffs, diagnostics, terminal integration and previews.
4. **Desktop extension / IDE:** commands and context inside VS Code-compatible editors; eventually a branded Code-OSS distribution.
5. **Local filesystem companion:** explicitly user-authorized access to selected local folders where browser APIs are insufficient.
6. **Studio API and orchestration runtime:** durable goals, plans, tasks, agents, tool calls, artifacts and policy decisions.
7. **Studio MAC:** staff-only configuration and administration for Studio itself.
8. **Studio MAD / operational dashboard:** service health, agent activity, queue state, execution cost, deployments, incidents and audit visibility.
9. **ODEI AI gateway:** a separate intelligence service for model routing, provider policy and AI capabilities. Studio is a client, not the gateway's owner.
10. **Ecosystem Command Center:** cross-product directory/control surface. It is not the Studio MAC.

The source investigation explicitly distinguishes the Studio website MAC from the Agents application and Editor. Preserve this separation in routes, identity policy, navigation and deployment.

## 4. Local desktop and folder ingestion requirements

The upstream path-bridge design resolves an important limitation: a browser-only PWA cannot silently discover arbitrary absolute paths on a Windows computer.

The source implementation provides a local Node companion with:

- Loopback binding to `127.0.0.1`, not `0.0.0.0`.
- A user-selected root allowlist.
- Native folder picker and explicit absolute-path resolution.
- Directory listing and bounded file reads.
- File writes, rename and delete operations.
- Optional bearer/header token, rate limiting and origin allowlist.
- Lexical path traversal checks and realpath checks for symlink/junction escapes.
- Operation/path metadata logging without file contents.
- A public health probe that reports whether a token is required.

### Required ODEI policy

- Folder access must begin with an explicit user action and a clear folder picker.
- Never scan the entire Desktop, user profile, drives or arbitrary paths by default.
- Keep the selected-root allowlist scoped to the local companion process/session; provide a visible revoke/reset action.
- Default to read-only indexing. Editing, rename, delete, terminal execution and Git mutations require distinct permissions and user confirmation.
- Exclude secrets, credentials, private keys, dependency/build caches, binary files and files ignored by Git; bound file count, per-file bytes, aggregate bytes, depth and scan time.
- Do not upload file contents to an AI provider without explicit consent, explain what will be sent, and enforce server-side size limits.
- Bind to loopback only. Use an unpredictable token, strict Origin checks, rate limiting, request-size limits and safe error messages.
- A localhost token is not a substitute for loopback binding, browser-origin protections or operating-system user consent.
- Revalidate filesystem paths at operation time. A `realpath` check followed by a separate open/write can still have a time-of-check/time-of-use race. Production-grade implementation must use safe file-handle/open flags where supported, reject symlink traversal, and re-check the opened handle's identity and containment before reading or mutating.
- Do not expose the local bridge to a public network or remote browser. Remote workspaces require a separate authenticated, sandboxed execution service.

### Access modes and honest UX

| Mode | What it can do | Limitation |
|---|---|---|
| Browser File System Access API | User-selected directory handles and supported read/write | Browser support and permission persistence vary |
| `webkitdirectory` / file drop | Import a folder's files into a virtual tree | Does not grant arbitrary absolute paths or direct disk writes |
| Local path companion | User-selected absolute paths, directory listing and controlled file operations | Requires local installation, loopback security and explicit root selection |
| VS Code / Cursor URI handoff | Ask an installed desktop IDE to open a folder, clone a repository or connect via SSH | Does not itself execute those operations inside the web application |
| Remote isolated workspace | Server-side project files and sandboxed tools | Requires authenticated tenancy, isolation, quotas and lifecycle controls |

## 5. Agent and build architecture

The upstream TypeScript orchestrator provides a useful product domain model:

- Agent registry with specialized roles.
- Goal decomposition into ordered engineering phases.
- Task queue with dependency-aware readiness.
- Task lifecycle updates and structured events.
- Progress aggregation by goal.
- Build pipeline that gathers generated artifacts.
- Domain-specific task templates (the source includes a SACCO example).

The source README lists engineering roles such as planner, architect, database engineer, backend engineer, frontend engineer, QA, documentation and reviewer. The upstream technical specification includes requirements, architecture, database, backend, frontend, testing, documentation and deployment phases.

### Target architecture for this repository

Retain the stronger safety boundaries already introduced in the Python implementation:

- Planning is a proposal, not authorization.
- A plan must be persisted and reviewed before tools execute.
- Every task is tenant- and project-scoped.
- Tool permissions are explicit, typed, minimal and time-bounded.
- Tool execution occurs in ODEI-controlled isolated workspaces, never directly in the API process.
- File changes are represented as reviewable patches/diffs with hashes and concurrency checks.
- Shell, package install, network access, Git push, deployment, DNS and secret operations are separate capabilities with approval gates.
- Every tool call records actor, tenant, project, task, capability, arguments metadata, result, duration and policy decision. Do not store raw secrets or unnecessary file contents in audit records.
- Cancellation, timeout, retry limits, resource quotas and cleanup are mandatory.
- Validation includes unit/integration tests, lint, type checks, security checks and build verification before a task becomes review-ready.

The current Python task state machine and Responses API planner are an initial foundation, not yet the upstream multi-agent build system. The upstream orchestrator is currently deterministic/template-oriented in its documented baseline; it must not be described as a production autonomous coding agent without verified model-backed execution and sandbox tests.

## 6. ODEI AI gateway boundary

The upstream repository documents ODEI AI / ODAI as an independent gateway used by Studio and other products. Studio's ModelRouter client can query gateway health/models/agents/rules and request routing/completion. Repository snippets are consent-gated and bounded in the source client.

Adopt these boundaries:

- Studio owns the development task, project context, review UX and build lifecycle.
- ODEI AI owns model-provider routing, provider credentials, model policy and gateway-level observability.
- Do not duplicate provider API keys in Studio when the gateway can own them.
- Pass the minimum necessary context; default to not transmitting repository snippets.
- Keep gateway tokens server-side. Never expose gateway credentials in client bundles.
- Report provider/model identity and whether a response was live, simulated, fallback or unavailable.
- A local simulation or template fallback must never be presented as a real model completion.
- Add per-tenant budgets, rate limits, provider allowlists, cost attribution and redaction before production.

## 7. Studio MAC and MAD requirements

The upstream Studio MAC audit describes a local Phase 1.5 console that is distinct from the Agents and Editor surfaces. Its operational pattern is useful: staff access gate, live API-backed data, explicit refresh, honest maturity labels and functional actions rather than static sample rows.

### MAC modules

- Overview and service health.
- Organizations, users, roles and staff access.
- Projects and workspace registry.
- AI gateway connection and model policies.
- Provider integrations and capability matrix.
- Hosting projects, deployment targets and environments.
- Domains, registrars, DNS and TLS.
- Database connections and migrations.
- Secret references and environment variables.
- Agent registry, tools, permissions and approvals.
- Task queues, build records and artifacts.
- GitHub repositories, installations and webhooks.
- Audit events, security incidents and policy settings.
- Feature flags, product configuration and platform settings.

### MAD metrics

- API and worker health with probe timestamps.
- Queue depth, task latency, failures and retries.
- Active agent runs and tool invocation outcomes.
- Model/provider usage, spend, quotas and fallback rates.
- Workspace storage and execution resource usage.
- Deployment status and recent release history.
- Security events, denied operations and pending approvals.
- Integration connection status and last successful sync.

Every metric needs a real source, freshness timestamp, tenant scope and authorization rule. Static KPIs, hard-coded “healthy” pills and demo rows are not acceptable as operational evidence.

### Identity and privilege

The source audits explicitly identify production ODID/JWT and server-side RBAC as remaining requirements. For this repository, all protected routes must validate a trusted identity and resolve organization membership on the server. A client-supplied `organization_id`, `owner_id`, role or email is never sufficient proof of access. Require MFA/step-up authentication for high-risk administration where supported; audit all privileged changes.

## 8. Hosting, integrations and honesty

The source ecosystem separates product hosting, environment configuration, registrar/DNS operations and AI gateway concerns. Retain a provider-neutral adapter interface, but expose capabilities only where official provider APIs and the connected account support them.

For each provider, record:

- Authentication type and required scopes.
- Account/project discovery.
- Read operations.
- Create/update/delete operations.
- Deployment/build operations.
- Environment-variable operations.
- Domain/DNS/TLS operations.
- Logs, metrics and webhook support.
- Rate limits, plan restrictions and regional limitations.
- Tested fixtures, contract tests and last verification date.

Do not treat a static admin screen, environment variable example, local health check, mock adapter or successful DNS lookup as proof of provider control. Keep the previously defined Vercel integration boundary explicit; do not silently merge it into general hosting management.

## 9. Source maturity and migration caveats

The upstream source is valuable, but it is not a blanket production-readiness certificate.

The inspected documentation itself identifies historical or remaining limitations, including:

- Template-based or local-simulation agent behavior in parts of the system.
- API and identity boundaries that were not production ODID/JWT complete at the time of audit.
- In-memory build/task state in the documented baseline.
- Upload limitations and the need for signed object storage, scanning, quotas, retention and deletion before public exposure.
- Local path bridge security risks and local-machine trust assumptions.
- Code-OSS fork build complexity and desktop distribution work.
- Planned panels and capabilities that must not be mislabeled as live.
- Provider and ecosystem services whose local HTTP availability does not prove production availability.

Some later source files add capabilities beyond the older Phase 1 documentation. Every migration candidate must be checked against its current code, tests, dependencies and deployment configuration before it is marked implemented here.

## 10. Architecture reconciliation with this repository

This repository currently contains a Python/FastAPI backend foundation with a Responses API planner, task state machine, MongoDB task store and read-only file scanner. The upstream Studio implementation is primarily TypeScript/Node/Next.js and has its own API, orchestrator, build package and local path bridge.

Do not operate both implementations as competing authorities.

### Proposed bounded service ownership

| Capability | Canonical owner in target architecture | Migration rule |
|---|---|---|
| Browser workspace, Monaco, Agents UI | Studio web app | Port or adapt upstream components after selecting the frontend framework |
| Local folder access | Local path companion | Reuse security concepts; independently audit TOCTOU and browser-origin threat model |
| Identity and tenancy | Central identity/auth service + API authorization | Verify signed claims and membership server-side |
| Task lifecycle and persistence | Python API initially | Keep one source of truth; migrate only through versioned contracts |
| Planning and model calls | ODEI AI gateway / Python orchestration adapter | Avoid duplicated provider credentials |
| Agent/tool execution | Isolated execution service | Never execute arbitrary model-generated shell commands in API process |
| GitHub operations | Dedicated GitHub integration adapter | App installation tokens, minimal scopes and webhook signature checks |
| MAC/MAD | Studio control-plane API + separate web surfaces | Never conflate MAC, MAD, Agents app and ecosystem Command Center |
| Hosting/DNS | Provider adapters | Capability matrix and contract tests per provider |

This is a proposed migration boundary, not a claim that all these services already exist.

## 11. Implementation work order derived from the source audit

1. Keep the Python API's current tests/lint green; remove CI blockers before expanding scope.
2. Finalize the target service boundaries and API contracts so the upstream TypeScript runtime is not accidentally duplicated.
3. Build identity verification, organization membership and project authorization before any workspace or agent endpoint is exposed.
4. Implement MongoDB lifecycle/readiness and split unbounded task events into a separately indexed event collection with retention.
5. Harden project-file access and define a local path companion protocol, token lifecycle, user-picked roots and revocation.
6. Implement authenticated workspace list/read/search with strict budgets and consent-aware AI context.
7. Implement patch/diff/review and approval records.
8. Implement sandboxed execution, test runs, cancellation, quotas and audit.
9. Integrate the upstream UI concepts: Agents home, editor workspace, Monaco, Explorer, tabs, bottom panel, task progress and artifact viewer.
10. Implement ODEI AI gateway adapter with explicit live/local_sim/fallback status and bounded context.
11. Implement GitHub App and provider adapters using documented capability contracts.
12. Implement Studio MAC and MAD as distinct staff surfaces with live data.
13. Add desktop extension/Code-OSS packaging, offline capability and release signing.
14. Run end-to-end security, tenant isolation, Windows filesystem, API contract, UI, provider and deployment tests before release.

## 12. Source references

All references below are paths in the inspected source repository:

- [ODEI Studio README](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/README.md)
- [ODEI Studio holistic documentation](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/docs/ODEI_HOLISTIC_DOCUMENTATION.md)
- [ODEI Studio technical specification](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/docs/TECHNICAL_SPEC.md)
- [ODEI Studio MVP scope](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/docs/MVP_SCOPE.md)
- [Path bridge security](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/packages/path-bridge/src/security.ts)
- [Path bridge README](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/packages/path-bridge/README.md)
- [Studio deep audit](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_DEEP_AUDIT.md)
- [Workspace scan](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_EDITOR_WORKSPACE_SCAN.md)
- [Holistic remediation](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_HOLISTIC_SCAN_REMEDIATION.md)
- [MAC investigation](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_MAC_FULLY_OPERATIONAL_INVESTIGATION.md)
- [MAC remediation](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_MAC_REMEDIATION.md)
- [ODEI AI operating system](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ai/ODEI_AI_OPERATING_SYSTEM.md)
- [Whole ecosystem map](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ecosystem/ODEI_MULTI_ECOSYSTEM_WHOLE.md)
- [Product MAC catalog](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ecosystem/PRODUCT_MAC_CONSOLES.md)

---

**Maintenance rule:** update this alignment document when upstream architecture or source code materially changes. Keep implementation status, test results and security claims grounded in the target repository's own commits and CI—not inherited from upstream documentation.


### Additional source-audit cautions

- The inspected path-bridge package inventory contains implementation files and a README but no dedicated path-bridge test file in that package. This target repository must add security tests for traversal, junction/symlink escape, token handling, Origin/CSRF behavior, Windows drive/case semantics, race conditions and destructive-operation confirmation before adopting the bridge.
- The source desktop-bridge module includes seeded recent-project examples with historical Windows paths. Seeded UI examples are not evidence that those folders exist on the current machine and must never be used to authorize filesystem access. The actual user must pick the directory or explicitly grant a handle.
- The upstream technical specification and holistic documentation are older than several Phase 1.5 source audits. The audit records should be treated as dated evidence, not as a substitute for re-running the current test suite and inspecting current runtime behavior.
