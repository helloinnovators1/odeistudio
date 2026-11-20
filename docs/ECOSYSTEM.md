# ODEI Studio — Full Ecosystem Handbook

**Status:** Product and architecture specification. Implementation status is tracked separately in the roadmap and repository.

## 1. Vision

ODEI Studio is an African-built AI-native Development Operating System (AI-DOS): a unified environment where people and AI agents understand, create, test, secure, deploy and operate software. It should work for individual builders, teams, agencies, enterprises, educators and ecosystem partners.

The platform is not merely a code editor with a chatbot. It combines a developer workspace, code intelligence, agent orchestration, secure execution, integrations, governance and operations.

## 2. Product principles

- **Human-directed autonomy:** agents can perform bounded work independently while people retain control over consequential actions.
- **Evidence over appearance:** a feature is operational only when its behavior, permissions, persistence, tests and failure modes are verified.
- **African-first, globally useful:** support constrained connectivity, cost awareness, regional realities and global engineering standards.
- **Provider-neutral architecture:** adapters normalize integrations without pretending providers have identical capabilities.
- **Secure by default:** least privilege, tenant isolation, secret vaulting, isolated execution and auditable actions.
- **Composable workspace:** multi-card, multi-tab layouts with persistent project context.
- **Open integration:** APIs, webhooks and carefully governed tool/MCP connections.
- **Incremental delivery:** ship usable slices, not a large collection of nonfunctional screens.

## 3. Ecosystem map

### A. ODEI NEXUS — AI Software Engineering Agent
The first priority product module. Understands a repository, plans tasks, edits multiple files, runs approved commands, tests, diagnoses failures, proposes repairs and produces reviewable diffs.

### B. ODEI Studio Workspace
The primary development experience:
- project and workspace switcher;
- file explorer and repository search;
- editor with language services;
- agent chat and task plans;
- terminal and command approvals;
- diff/review panel;
- application preview;
- diagnostics, logs and test results;
- multi-card and multi-tab layouts.

### C. Code Intelligence
Repository ingestion, file and symbol indexing, language-server integration, dependency maps, semantic retrieval, project rules, architecture maps and change impact analysis.

### D. Agent Platform
Agent registry, task planner, specialist agents, tool registry, policies, execution queues, durable task state, approval gates, retries, cancellation and traces.

### E. Execution Fabric
Local development adapter and isolated remote workspaces. Supports bounded shell execution, dependency installation, tests, builds, previews and browser automation. Production credentials must not be mounted into untrusted tasks.

### F. Master Admin Console (MAC)
The authoritative control plane for platform configuration, identity, tenants, provider connections, environment configuration, secret references, integrations, policies, feature flags and administration.

### G. Master Admin Dashboard (MAD)
Operational and executive visibility over service health, queues, deployments, spend, provider status, incidents, security events and usage. It reads authoritative telemetry; it does not become a second configuration authority.

### H. Integration Hub
GitHub, model providers, databases, storage, queues, observability, cloud/hosting, registrars, DNS, billing and notification adapters. Vercel is a separate integration boundary.

### I. Identity, Teams and Governance
Organizations, workspaces, memberships, roles, invitations, MFA policy, audit, quotas, data retention and enterprise controls.

### J. Ecosystem extensions
Future modules may include AI chatbot creation, website/app generation, mobile app workflows, enterprise integration automation, templates, education and a marketplace. These must build on shared platform services rather than fork authentication, agents or billing.

## 4. Primary user journeys

### Build or modify a project
Create/open project → inspect repository → state objective → receive plan → approve scope → agent edits in isolated workspace → inspect diff → run tests → repair → review → commit or create PR.

### Create a new application
Choose template or describe requirements → clarify constraints → generate architecture and milestones → scaffold → implement vertical slice → preview → test/security review → deploy after explicit authorization.

### Connect an integration
Select provider → review scopes and data access → authorize → validate credentials server-side → discover account/resources/capabilities → store secret reference → audit connection → monitor health.

### Operate the platform
MAC configuration change → validate → approval if required → apply → verify actual provider/service state → emit audit event → MAD reflects measured outcome.

## 5. Product boundaries

- MAC owns platform configuration and governance.
- MAD visualizes measured operational state.
- NEXUS owns coding task planning and execution, subject to policy.
- Workspace owns the interactive developer experience.
- Integration adapters own provider-specific API behavior.
- Execution services own isolation, resource limits and process lifecycle.
- MongoDB stores application metadata and durable records, not plaintext secret material.
- Vercel is not silently included in the general non-Vercel hosting management scope.

## 6. Architecture at a glance

Experience plane → API/application services → orchestration and policy → agent tools → isolated execution and provider adapters. Cross-cutting services provide identity, tenancy, audit, secrets, telemetry, billing/quotas and durable storage.

## 7. Delivery strategy

Build a thin, end-to-end NEXUS vertical slice first: create project → inspect files → plan → make a bounded edit → show diff → run a test → report result. Add capabilities only when the prior slice is reliable. Then integrate the workspace UI, MAC/MAD and additional ecosystem modules.

## 8. Definition of done

A feature is done only when:
- acceptance criteria are explicit;
- server-side authorization and tenant isolation are enforced;
- errors and partial failures are handled;
- data persistence and migrations are defined;
- automated tests cover success and failure paths;
- logs and metrics avoid sensitive data;
- user-visible state reflects verified outcomes;
- docs and operational runbooks are updated.
