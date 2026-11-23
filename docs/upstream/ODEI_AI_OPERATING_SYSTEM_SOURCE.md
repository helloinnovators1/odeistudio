> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/ODEI_AI_OPERATING_SYSTEM.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ai/ODEI_AI_OPERATING_SYSTEM.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI AI Operating System — local_sim / design-edition

## Status and scope

ODEI AI-OS is the unified local platform surface at `http://localhost:5203/v1/*`. Product applications call this gateway rather than embedding separate model integrations. It is an implemented local simulation with durable JSON state, deterministic retrieval, and optional keyed OpenAI/Anthropic calls. It is **not** a production multi-tenant cloud, GPU fleet, regulated-finance control plane, medical-grade vision system, or a claim of hundreds of production agents.

## Local architecture

```text
Academy / Studio / Communications / product apps
                    │
                    ▼
       ODEI AI-OS gateway (:5203 /v1/*)
 router · policy · audit · tenant context · risk checks
     │           │              │
 models       agents         governed tools
     │           │              │
 local_sim   JSON memories   grants + HITL queue
     │
 vector-lite RAG ← docs/ and whitepaper index
```

`apps/serve_product_apps.mjs` serves ODEI AI and hot-loads `apps/ai/api/handler.mjs`. The gateway persists local platform state at `apps/ai/data/ai-os-local-store.json` on first mutation. This file is intentionally local development state, not a durable production data store.

## Layer status

| Layer | Status | Evidence |
|---|---|---|
| L1 Foundation | Implemented local_sim | router, prompt/rules registry, tenant context, durable policy and audit events |
| L2 Multi-model | Implemented local_sim | config-driven catalog and task routing; OpenAI/Anthropic optional, other providers honestly planned/local fallback |
| L3 Multi-agent | Implemented local_sim | 48 named specialists, planner → specialist checkpoint loop, sensitive approval flag |
| L4 Memory | Implemented local_sim | durable session, conversation, task, agent and shared-team records via `POST|GET /v1/memory` |
| L5 Knowledge/RAG | Implemented local_sim | `docs/` ingestion, token-frequency vector-lite retrieval, path citations |
| L6 Tools | Implemented local_sim | structured tool catalog, capability grants, sensitive HITL queue, no external side effects |
| L7 Studio bridge | Implemented local_sim | shared AI-OS agent registry, recorded `POST /v1/studio/handoff`, and deep-links into Studio App `:3002/app`; Studio reads handoff context and remains the independent build client |
| L8 Voice | Implemented local_sim | local STT/TTS request modules and UI controls; no hosted voice model or biometric processing claim |
| L9 Vision | Implemented local_sim | local OCR request module and UI control; no hosted or medical-grade vision claim |
| L10 Marketplace | Implemented local_sim | catalog and durable tenant-local installs via `GET /v1/marketplace`, `POST /v1/marketplace/install`; no remote distribution or billing |
| L11 Developer platform | Implemented local_sim | REST endpoints, JavaScript SDK stub, CLI stub, webhook receiver, local batch queue |
| L12 Security | Implemented local_sim | RBAC context, injection heuristics, request-size limits, token option, and sensitive HITL controls |
| L13 Governance | Implemented local_sim | durable policy records, capability grants, approval queue and audit log |
| L14 Analytics | Implemented local_sim | audit-derived requests, agent/RAG activity, pending approvals and zero-cost estimates |
| L15 AI Cloud | Implemented local_sim | executable local batch-record queue and `GET /v1/cloud/topology` design surface; no GPU, Kubernetes, or multi-cloud scheduler is claimed |

## Core API

- `GET /v1/health`, `GET /v1/platform`, `GET /v1/models`
- `POST /v1/complete` — accepts `taskType`, `tenantId`, `actorId`, context, messages; returns observability data.
- `GET|POST /v1/policies` — local durable tenant policy records.
- `POST /v1/rag/ingest`, `POST /v1/rag/query` — query response includes repository-path citations.
- `GET /v1/agents`, `POST /v1/agents/run`, `GET|POST /v1/memory`
- `GET /v1/tools`, `POST /v1/tools/grants`, `POST /v1/tools/invoke`, `GET /v1/approvals`
- `GET /v1/analytics`, `POST /v1/webhooks/receive`, `POST /v1/batches`, `GET /v1/cloud/topology`
- `GET /v1/marketplace`, `POST /v1/marketplace/install`, `GET /v1/studio/bridge`, `POST /v1/studio/handoff`

The JavaScript local client stub is `apps/ai/sdk/odei-ai-os.js`. The CLI stub is `node apps/ai/bin/odei-ai-os.mjs platform` (or `ingest`, `rag <query>`, `agent <id> <task>`). Both target :5203 by default and are not published packages or production credentials.

When `ODEI_AI_GATEWAY_TOKEN` is configured, mutating routes require `X-ODEI-AI-Token` or a bearer token. Local development remains intentionally open when no token is configured; that is not a production authorization model.

## Product wiring

- **Communications** calls `POST http://localhost:5203/v1/complete`.
- **Studio** checks and optionally consumes `http://localhost:5203/v1/health`, reads the shared AI-OS agent registry, and accepts `odeiAgent` / `odeiTask` deep-link handoff context.
- **Academy** lesson mentor now calls the completion endpoint and falls back to its explicit browser-local response when the gateway is unavailable.
- The ecosystem registry already declares ODEI AI at port 5203.

## Intentional production gaps

Production work still requires real tenant identity/SSO, a database and encrypted audit retention, secret management, per-provider contracts and billing, vector database and document ACLs, authenticated tool connectors, policy enforcement service, distributed rate limits, incident monitoring, SDK/CLI packaging, real voice/vision models, model serving, and GPU orchestration.
