> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/ODEI Studio/docs/MVP_SCOPE.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/docs/MVP_SCOPE.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio — Phase 1 MVP Scope

**Version:** 0.1.0  
**Organization:** ODEIAfrica  
**Status:** In Development  
**Last Updated:** June 27, 2026

---

## 1. MVP Vision

Deliver a working proof-of-concept that demonstrates the core ODEI Studio value proposition:

> **Human defines a goal → ODEI Studio plans, orchestrates agents, and generates a product scaffold.**

Phase 1 is **not** the full AI-DOS. It is the minimum viable slice that proves multi-agent orchestration, goal decomposition, artifact generation, and VS Code fork integration.

---

## 2. MVP Definition

### In Scope (Phase 1)

| # | Capability | Deliverable | Status |
|---|-----------|-------------|--------|
| 1 | **Monorepo scaffold** | npm workspaces, TypeScript, shared packages | ✅ Done |
| 2 | **Agent Orchestrator** | Planner, task queue, agent registry, event system | ✅ Done |
| 3 | **ODEI Build** | Goal → plan → execute → artifacts pipeline | ✅ Done |
| 4 | **REST API** | `/build`, `/goals/plan`, `/agents` endpoints | ✅ Done |
| 5 | **Web UI** | Goal input form, build results display | ✅ Done |
| 6 | **VS Code Fork Setup** | Clone script, product branding, fork docs | ✅ Done |
| 7 | **VS Code Extension** | ODEI panel, build-from-goal command | ✅ Done |
| 8 | **SACCO Demo Path** | Domain-specific task decomposition | ✅ Done |
| 9 | **Unit Tests** | Orchestrator + Build pipeline tests | ✅ Done |
| 10 | **Documentation** | Tech spec, MVP scope, README | ✅ Done |

### Out of Scope (Deferred to Phase 2+)

| Capability | Phase | Reason |
|-----------|-------|--------|
| Image / file uploads | Phase 2+ | Requires Identity, object storage, MIME validation, scanning |
| LLM integration (OpenAI/Claude) | Phase 2 | Requires API keys, model router |
| MongoDB / Redis / Qdrant persistence | Phase 2 | In-memory sufficient for MVP |
| Authentication (Keycloak/Auth0) | Phase 2 | Single-user demo first |
| Sidebar tabs beyond Build (Agents, Memory, Deploy, Security, Monitor, Docs, Marketplace) | Phase 2+ | Phase 1 UI chrome only — Build is the sole live tab |
| Background autonomous workers | Phase 3 | Requires queue infrastructure |
| Agent Marketplace | Phase 4 | Needs orchestrator maturity |
| Full VS Code fork build | Phase 2 | Requires 8GB+ RAM, hours to compile |
| Mobile (Flutter/RN) | Phase 5+ | Web + IDE first |
| Deployment automation (ODEI Deploy) | Phase 3 | Build first |
| Enterprise RBAC / SSO | Phase 5 | MVP is single-workspace |
| Foundation models (ODEI Models) | Phase 8 | Use third-party models first |

---

## 3. Success Criteria

Phase 1 MVP is **complete** when:

1. ✅ `npm install && npm run build` succeeds across all packages
2. ✅ `npm run test` passes orchestrator and build tests
3. ✅ API accepts a goal and returns generated artifacts
4. ✅ Web UI submits a goal and displays plan + artifacts
5. ✅ VS Code extension connects to API and triggers builds
6. ✅ VS Code fork script clones Code-OSS and applies ODEI branding
7. ✅ SACCO goal produces domain-specific tasks (loans, savings, member dashboard)

---

## 4. User Stories

### US-1: Define a Goal
**As a** developer  
**I want to** describe a software project in natural language  
**So that** ODEI Studio can plan and build it autonomously

**Acceptance:** Submit "Build a SACCO Management System" → receive execution plan with 8+ tasks

### US-2: View Agent Plan
**As a** developer  
**I want to** see which agents will work on which tasks  
**So that** I understand the autonomous engineering process

**Acceptance:** Plan shows phases (requirements → architecture → database → backend → frontend → testing → docs) with assigned agents

### US-3: Receive Generated Artifacts
**As a** developer  
**I want to** receive scaffolded code, schemas, and documentation  
**So that** I have a starting point for my project

**Acceptance:** Build produces REQUIREMENTS.md, ARCHITECTURE.md, schema.prisma, main.py, page.tsx, test_api.py, README.md

### US-4: Build from VS Code
**As a** developer using ODEI Studio IDE  
**I want to** trigger a build from within the editor  
**So that** I never leave my development environment

**Acceptance:** Command palette → "ODEI: Build from Goal" → artifacts appear in output panel

---

## 5. Demo Scenario: SACCO Management System

The primary demo path validates African fintech relevance:

```
Input:  "Build a SACCO Management System"
        "Cooperative savings and loan platform for East Africa"

Output: Execution Plan (10+ tasks)
        ├── Requirements analysis
        ├── System architecture design
        ├── Database schema (MongoDB/Prisma)
        ├── Backend API (FastAPI)
        ├── SACCO loan management module
        ├── SACCO savings & member management
        ├── Member dashboard UI (Next.js)
        ├── Test suite (pytest)
        └── Documentation (README, API docs)
```

---

## 6. Timeline Estimate

| Week | Milestone |
|------|-----------|
| 1 | Monorepo + Orchestrator + Build pipeline (this sprint) |
| 2 | LLM integration, template → AI-generated artifacts |
| 3 | MongoDB persistence, workspace memory |
| 4 | VS Code fork first build, extension polish |
| 5-6 | Context engine (indexing, embeddings) |
| 7-8 | Alpha release with 10 beta users |

---

## 7. Metrics

| Metric | Target (Phase 1) |
|--------|-------------------|
| Goal → Plan latency | < 2 seconds |
| Goal → Artifacts latency | < 5 seconds |
| Test coverage (core packages) | > 80% |
| Agent types active | 9 |
| Artifact types generated | 7 |
| API endpoints | 6 |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| VS Code fork build complexity | High | Extension-first approach; fork build in Phase 2 |
| Template-based artifacts feel generic | Medium | LLM integration in Phase 2 for dynamic generation |
| Scope creep toward full AI-DOS | High | This document as scope boundary |
| No persistence = data loss on restart | Low | Acceptable for MVP demo |

---

*This document is the scope boundary for Phase 1. Any feature not listed in "In Scope" requires explicit approval to add.*
