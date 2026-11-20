> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/ODEI Studio/docs/TECHNICAL_SPEC.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/docs/TECHNICAL_SPEC.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio — Technical Specification

**Version:** 0.1.0 (Phase 1 MVP)  
**Organization:** ODEIAfrica  
**Classification:** Internal — Engineering  
**Source Blueprint:** ODEI Studio v1.0 Foundational Blueprint  
**Last Updated:** June 27, 2026

---

## 1. Introduction

This specification translates the ODEI Studio Foundational Blueprint into implementable engineering requirements for Phase 1 MVP. It defines architecture, data models, API contracts, module boundaries, and the VS Code fork strategy.

### 1.1 Design Principles

1. **Goal-first, not code-first** — Users submit goals; the system produces products
2. **Agent specialization** — Each agent has a defined role, phase, and capability set
3. **Monorepo cohesion** — Shared types, unified TypeScript, workspace packages
4. **Cursor-compatible IDE strategy** — Fork Code-OSS (microsoft/vscode), not wrap it
5. **Incremental delivery** — Template-based generation now; LLM generation in Phase 2

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      USER INTERFACES                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  Web App     │  │ VS Code Ext  │  │  ODEI Studio IDE     │ │
│  │  (Next.js)   │  │              │  │  (Code-OSS Fork)     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘ │
└─────────┼─────────────────┼─────────────────────┼───────────┘
          │                 │                     │
          └─────────────────┼─────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ODEI STUDIO API (:4000)                     │
│  POST /api/v1/build  │  POST /api/v1/goals/plan  │  GET /agents│
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   @odei/build (BuildPipeline)                │
│  Goal → Plan → Execute Tasks → Collect Artifacts             │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              @odei/orchestrator (OrchestratorCore)           │
│  ┌──────────┐  ┌───────────┐  ┌─────────────────────────┐   │
│  │ Planner  │  │ TaskQueue │  │ AgentRegistry (9 agents)│   │
│  └──────────┘  └───────────┘  └─────────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    @odei/shared (Domain Types)               │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Phase 2 Additions (Planned)

```
OrchestratorCore
    ├── WorkspaceMemory (MongoDB)
    ├── ContextEngine (Qdrant embeddings)
    ├── ModelRouter (OpenAI / Claude / Gemini)
    └── BackgroundWorkerQueue (Redis + RabbitMQ)
```

---

## 3. Repository Structure

```
odei-studio/
├── apps/
│   └── web/                    # Next.js goal interface
├── packages/
│   ├── shared/                 # Domain types, constants, utilities
│   ├── orchestrator/           # Agent orchestration core
│   ├── build/                  # ODEI Build pipeline
│   └── api/                    # Express REST API
├── extensions/
│   └── odei-studio/            # VS Code extension
├── vscode/
│   ├── product.overrides.json  # ODEI branding for Code-OSS
│   └── README.md               # Fork build instructions
├── scripts/
│   ├── fork-vscode.ps1         # Clone microsoft/vscode
│   └── apply-product-branding.ps1
├── docs/
│   ├── TECHNICAL_SPEC.md       # This document
│   └── MVP_SCOPE.md
├── package.json                # npm workspaces root
└── tsconfig.base.json
```

---

## 4. Domain Model

### 4.1 Core Entities

```typescript
Goal {
  id: string
  title: string
  description: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  workspaceId: string
  createdAt: ISO8601
  updatedAt: ISO8601
}

Task {
  id: string
  goalId: string
  title: string
  description: string
  phase: BuildPhase
  assignedAgent: AgentRole
  status: TaskStatus
  dependencies: string[]
  output?: TaskOutput
}

ExecutionPlan {
  id: string
  goalId: string
  summary: string
  phases: BuildPhase[]
  tasks: Task[]
  estimatedTaskCount: number
}

BuildResult {
  id: string
  goalId: string
  plan: ExecutionPlan
  artifacts: GeneratedArtifact[]
  status: 'planning' | 'building' | 'completed' | 'failed'
}
```

### 4.2 Build Phases (Ordered)

```
requirements → architecture → database → backend → frontend → testing → documentation → deployment
```

### 4.3 Agent Roles (Phase 1)

| Role | Phase(s) | Responsibility |
|------|----------|----------------|
| `chief-executive` | requirements | Goal analysis, coordination |
| `planner` | requirements, architecture | Goal decomposition |
| `architect` | architecture, database | System design |
| `database-engineer` | database | Schema creation |
| `backend-engineer` | backend | API implementation |
| `frontend-engineer` | frontend | UI implementation |
| `qa-engineer` | testing | Test generation |
| `documentation` | documentation | Docs generation |
| `reviewer` | testing, documentation | Quality checks |

---

## 5. API Specification

**Base URL:** `http://localhost:4000`  
**Content-Type:** `application/json`

### 5.1 Health Check

```
GET /health
→ 200 { status, service, version, timestamp }
```

### 5.2 List Agents

```
GET /api/v1/agents
→ 200 { agents: AgentDefinition[] }
```

### 5.3 Plan Goal (No Execution)

```
POST /api/v1/goals/plan
Body: { title, description, priority?, workspaceId, includeTests?, includeDocs? }
→ 201 { goal, plan }
```

### 5.4 Execute Build

```
POST /api/v1/build
Body: { goal: { title, description, priority, workspaceId }, options?: BuildOptions }
→ 201 BuildResult
```

### 5.5 Get Build

```
GET /api/v1/build/:buildId
→ 200 BuildResult | 404
```

### 5.6 List Builds

```
GET /api/v1/builds
→ 200 { builds: BuildResult[] }
```

### 5.7 Goal Task Progress

```
GET /api/v1/goals/:goalId/tasks
→ 200 { tasks, progress: { total, completed, failed, running, pending, percent } }
```

---

## 6. Orchestrator Specification

### 6.1 Goal Decomposition Algorithm

1. Parse goal title and description for domain keywords
2. Generate base task templates for each build phase
3. If SACCO/fintech domain detected, inject domain-specific tasks:
   - Loan management module
   - Savings & member management
   - Member dashboard
4. Optionally append testing and documentation tasks
5. Chain tasks with sequential dependencies
6. Assign agents via `PHASE_AGENT_MAP`

### 6.2 Task Queue Semantics

- Tasks enter queue with status `queued`
- Only tasks whose dependencies are all `completed` are eligible
- `getReady()` returns eligible tasks in queue order
- Failed tasks halt the build pipeline

### 6.3 Event System

| Event | Trigger |
|-------|---------|
| `plan.created` | Plan generated for goal |
| `task.queued` | Task added to queue |
| `task.started` | Agent begins task |
| `task.completed` | Agent finishes successfully |
| `task.failed` | Agent fails |
| `build.started` | BuildPipeline.run() begins |
| `build.completed` | All tasks completed |
| `build.failed` | Any task failed |

---

## 7. ODEI Build Specification

### 7.1 Pipeline Flow

```
BuildRequest
  → Create Goal (generate ID, timestamps)
  → OrchestratorCore.planGoal()
  → Loop: getNextTasks() → execute → complete/fail
  → Collect artifacts from each completed task
  → Return BuildResult
```

### 7.2 Artifact Generation (Phase 1 + ModelRouter enrichment)

Phase 1 uses **template-based generation**. Each build phase has predefined templates:

| Phase | Artifacts | Format |
|-------|-----------|--------|
| requirements | REQUIREMENTS.md | Markdown |
| architecture | ARCHITECTURE.md | Markdown |
| database | schema.prisma | Prisma |
| backend | main.py | Python/FastAPI |
| frontend | page.tsx | React/Next.js |
| testing | test_api.py | Python/pytest |
| documentation | README.md | Markdown |

**ModelRouter (P0 shipped):** When `options.useAi: true` and ODEI AI `:5203` completes successfully, the API sets `options.aiCompletion` and `@odei/build` appends:

- `## AI ModelRouter analysis` to **REQUIREMENTS.md**
- `## AI ModelRouter architecture notes` to **ARCHITECTURE.md** (when applicable)

Implementation: `packages/build/src/index.ts` → `appendAiSection()`. Agents UI renders full artifact content in `apps/web/src/components/build-results.tsx`.

Verify: `npm run verify:studio-ai-build` from ecosystem root. See [`../../docs/studio/STUDIO_MODELROUTER_VERIFY.md`](../../docs/studio/STUDIO_MODELROUTER_VERIFY.md).

Phase 2 may replace more template bodies with provider-backed LLM output; today AI **enriches** templates — it does not replace the orchestrator.

### 7.3 Output Path Convention

```
generated/{project-slug}/{phase}/{filename}
```

Example: `generated/sacco-management-system/backend/main.py`

---

## 8. VS Code Fork Strategy

Following Cursor's approach with [microsoft/vscode](https://github.com/microsoft/vscode) (Code-OSS):

### 8.1 Fork Model

```
odei-studio/                    ← This monorepo (orchestrator, build, API)
vscode/upstream/                ← Cloned Code-OSS (gitignored, ~1GB)
  └── product.json              ← Patched with ODEI branding
  └── extensions/odei-studio/   ← Symlinked or copied from ../../extensions/
```

### 8.2 Branding Overrides (`vscode/product.overrides.json`)

| Field | Value |
|-------|-------|
| `nameShort` | ODEI Studio |
| `nameLong` | ODEI Studio — AI-Native Development OS |
| `applicationName` | odei-studio |
| `dataFolderName` | .odei-studio |
| `win32MutexName` | odeistudio |
| `urlProtocol` | odei-studio |

### 8.3 Build Requirements

- Node.js 20+
- Python 3.11+
- 8 GB RAM minimum (16 GB recommended)
- ~10 GB disk space
- Windows: Visual Studio Build Tools
- Build time: 30-60 minutes first compile

### 8.4 Phase 1 Approach

1. **Now:** VS Code extension connects to ODEI API (works in any VS Code / Cursor)
2. **Phase 2:** Full Code-OSS fork build with ODEI branding and built-in extension
3. **Phase 3:** Deep IDE integration (custom AI panel in workbench, modified `src/vs/`)

### 8.5 Key Code-OSS Modification Points (Phase 2+)

| File | Modification |
|------|-------------|
| `product.json` | ODEI branding |
| `src/vs/workbench/` | ODEI AI panel in sidebar |
| `extensions/` | Built-in ODEI Studio extension |
| `build/lib/` | Custom build targets |
| `resources/` | ODEI icons and splash |

---

## 9. Technology Decisions (Phase 1 Locked)

| Layer | Choice | Alternatives Deferred |
|-------|--------|----------------------|
| Language | TypeScript | — |
| Monorepo | npm workspaces | pnpm (Phase 2) |
| API | Express 5 | FastAPI (Phase 2 Python service) |
| Web | Next.js 15 | — |
| IDE Base | Code-OSS fork | Extension-only fallback |
| Database | In-memory (Phase 1) | MongoDB (Phase 2) |
| Cache | In-memory (Phase 1) | Redis (Phase 2) |
| Vector Store | None (Phase 1) | Qdrant (Phase 2) |
| AI Models | Templates (Phase 1) | OpenAI/Claude via Model Router (Phase 2) |

---

## 10. Security (Phase 1 Baseline)

- No authentication (localhost-only demo)
- CORS restricted to local Studio / gateway origins (not open)
- No secrets in repository
- `.env` gitignored
- Phase 2: Keycloak integration, RBAC, secrets vault

This baseline is **development-only**, not a production security model. The
browser defaults to `http://localhost:4000` unless `NEXT_PUBLIC_API_URL` is set
at build time; there is still no trusted user/workspace boundary. Edge DNS may
advertise `studio.odeiafrica.com`, but `deploy_edge.sh` does not deploy Studio.

### 10.1 User-uploaded images/files

Phase 1.5 local foundation: `POST /api/v1/uploads` accepts base64 PNG/JPEG/WebP/GIF
with magic-byte verification and a 5 MB cap into `.uploads/{workspaceId}/`.
Optional `ODEI_STUDIO_API_KEY` gates the API. Builds may pass `attachmentIds`.
Agents do not yet consume image bytes. **Not** signed cloud storage, virus scan,
or ODID workspace isolation — required before public exposure.
`docs/ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md`.

---

## 11. Testing Strategy

| Package | Framework | Coverage Target |
|---------|-----------|-------------------|
| `@odei/orchestrator` | Node.js test runner | Goal decomposition, task queue, events |
| `@odei/build` | Node.js test runner | Full pipeline, artifact generation |
| `@odei/api` | Manual / Phase 2 automated | Endpoint validation |
| `@odei/web` | Phase 2 Playwright | E2E build flow |

Run: `npm run test` from repository root.

---

## 12. Deployment (Phase 1)

Local development only:

```bash
npm install
npm run build
npm run dev        # API on :4000
npm run dev:web    # Web on :3002
```

Production hostnames and gateway entries elsewhere in the ecosystem are routing
scaffolding; they do not change this local-only classification. A production
Studio deployment needs a built web/API process definition, non-localhost API
configuration, authentication/RBAC, durable persistence, secrets, observability,
and an explicit deployment pipeline.

---

## 13. References

- ODEI Studio v1.0 Foundational Blueprint (source document)
- Cursor Deep Autonomous Research Report (competitive baseline)
- [microsoft/vscode](https://github.com/microsoft/vscode) — Code-OSS repository
- [VS Code Extension API](https://code.visualstudio.com/api)
- [VS Code Build Wiki](https://github.com/microsoft/vscode/wiki/How-to-Contribute)

---

*This specification governs Phase 1 MVP implementation. Changes require update to both this document and MVP_SCOPE.md.*
