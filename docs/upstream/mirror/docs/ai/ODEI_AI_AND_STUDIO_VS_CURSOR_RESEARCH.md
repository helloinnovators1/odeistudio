> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ai/ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI AI × ODEI Studio vs Cursor — Holistic Research

**Date:** 2026-07-31  
**Status:** Research + **P0 done** — live ODEI AI gateway `:5203` + Studio ModelRouter consumer (products stay independent)  
**Workspace:** `e:\ODEI Multi Ecosystem`  
**Confirmed product direction:** Keep **ODEI AI** and **ODEI Studio** as **independent** flagship products; Studio **consumes** AI; do **not** merge them  
**Authority peers:** [`ODEI_AI_HOLISTIC_RESEARCH.md`](./ODEI_AI_HOLISTIC_RESEARCH.md) · [`CURSOR_COM_AND_AGENTS_SURFACE_RESEARCH.md`](./CURSOR_COM_AND_AGENTS_SURFACE_RESEARCH.md) · [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) · [`ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`](./ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md) · [`ODEI_ECOSYSTEM_STACK_STRATEGY.md`](./ODEI_ECOSYSTEM_STACK_STRATEGY.md) · [`BUILD_ORDER_ROADMAP.md`](./BUILD_ORDER_ROADMAP.md) · [`HONESTY_POLICY.md`](./HONESTY_POLICY.md) · [`ODEI AI/docs/ODEI_HOLISTIC_DOCUMENTATION.md`](../ODEI%20AI/docs/ODEI_HOLISTIC_DOCUMENTATION.md) · [`ODEI Studio/docs/TECHNICAL_SPEC.md`](../ODEI%20Studio/docs/TECHNICAL_SPEC.md)

**Canvas (visual summary):** open beside chat → [`odei-ai-studio-vs-cursor-research.canvas.tsx`](/Users/Software%20Innovations/.cursor/projects/e-ODEI-Multi-Ecosystem/canvases/odei-ai-studio-vs-cursor-research.canvas.tsx).

---

## 0. Executive verdict

| Question | Answer |
|----------|--------|
| What is Cursor’s CLI model ecosystem? | A **multi-provider routing + billing layer** over frontier models (OpenAI, Anthropic, Google, Cursor-first Grok/Composer, others) with `/model` switching, Auto modes, MCP/ACP, agents, and CI print mode — **not** ODEI’s stack. |
| What is the Cursor “workspace”? | An **AI operating surface** unifying desktop IDE, Agents Window, web/mobile cloud agents, CLI, and team admin/billing — product chrome + proprietary AI services on a Code-OSS base. |
| Should ODEI merge AI + Studio? | **No.** Independence matches monorepo ADRs, build-order (AI = shared infra; Studio = creator/dev platform), and how Cursor itself separates IDE chrome from model/routing services. |
| Are GPT-5 / Claude / Grok “available” in ODEI? | **Only if configured.** Gateway lists them as `planned` unless provider env keys make them `configured`. Default live model is `local_sim` / Auto heuristic. Do not advertise frontier availability without keys. |

**One-line truth:** Cursor shows *why* intelligence infrastructure and creator IDE must stay separate products that integrate by contract; ODEI should copy that split, not Cursor’s proprietary stack.

---

## 1. Method & sources

1. **Inventory** — `apps/ai/`, `ODEI AI/`, `apps/studio/`, `ODEI Studio/` (what exists vs planned).  
2. **Internal docs** — Studio Cursor parity suite, stack strategy, Studio TECHNICAL_SPEC / status / honesty, ODEI AI holistic + Website IA.  
3. **Public Cursor cross-check** (2026-07-31) — WebFetch / WebSearch of official docs; community forum CLI model lists treated as **reported**, not inventing availability.  
4. **Architecture implications** — mapping Cursor capabilities → ODEI AI vs Studio vs shared rails; phased integration only.

### 1.1 Public sources fetched / searched

| Source | Role |
|--------|------|
| [cursor.com/docs/models-and-pricing](https://cursor.com/docs/models-and-pricing) | **Verified** — provider catalog, Auto modes, Cursor Models pool (Grok 4.5, Composer 2.5), Teams/Enterprise notes |
| [cursor.com/docs/cli/overview](https://cursor.com/docs/cli/overview) | **Verified** — `agent` interactive + print/CI, modes, Cloud handoff |
| [cursor.com/docs/cli/using](https://cursor.com/docs/cli/using) | **Verified** — MCP via `mcp.json`, ACP, rules, worktrees, `/model`-class workflows documented via related CLI/agent docs |
| [cursor.com/docs/subagents](https://cursor.com/docs/subagents) | **Verified** — subagent model pin / inherit; models reference link |
| [cursor.com/docs/agent/agents-window](https://cursor.com/docs/agent/agents-window) · [cloud-agent](https://cursor.com/docs/cloud-agent) · Cursor 3 changelog | **Verified** — Agents Window, web agents dashboard, multi-surface workspace |
| Forum threads (`agent models`, Grok vs usage) | **Reported** — example CLI slugs (e.g. `gpt-5.4-*`, `sonnet-4.6-*`, `grok`, `gemini-3.1-pro`, `auto`); lists **change** and may differ from IDE |

**Honesty rule for this doc:** Prefer “verified on docs date” vs “user/forum reported.” Never invent a model ID as ODEI-live.

---

## 2. Cursor CLI model ecosystem

### 2.1 What it is (strategic)

Cursor does **not** own every model weight. It operates a **gateway product**:

- Account + plan pools (Cursor Models vs Other Models)  
- Model picker / CLI `/model` + `--model` / `agent models` / `cursor-agent --list-models`  
- **Auto** routing modes (Cost / Balance / Intelligence; team **Cursor Router** on Auto)  
- Tool runtime (editor + CLI agents, MCP, rules, subagents)  
- Org controls (block models, Max Mode legacy, Teams marketplace for rules/skills/plugins)

**ODEI lesson:** ODEI AI should be this **gateway + governance + marketplace** layer. ODEI Studio should be a **client** (plus IDE chrome), not the host of org AI billing or provider keys.

### 2.2 Verified vs reported model landscape

#### Verified (official Models & Pricing, fetched 2026-07-31)

Providers and families on Cursor’s priced catalog include (non-exhaustive; see live docs for current IDs):

| Family | Provider (docs) | Notes |
|--------|-----------------|-------|
| **Composer 2.5**, **Grok 4.5** | Cursor / SpaceXAI joint | **Cursor Models** pool; first-party agentic coding |
| **GPT-5 / 5.x / Codex / Mini / Nano / Luna / Sol / Terra** | OpenAI | Many variants; some Max Mode / hidden-by-default |
| **Claude Sonnet / Opus / Haiku / Fable** (4.x–5 line) | Anthropic | Thinking / fast / long-context variants; policy gates |
| **Gemini** (2.5 Flash, 3.x Pro/Flash, 3.1 Pro, …) | Google | Flash/Pro/image preview variants |
| **Kimi**, **GLM** | Moonshot, Z.ai | Listed; often hidden by default |
| **Auto** Cost / Balance / Intelligence | Cursor Router | Routes per request; Teams/Enterprise optimization modes |

#### Reported (CLI / forum — do not treat as frozen ODEI inventory)

Community `agent models` dumps and related threads have listed slugs such as `auto`, `composer-*`, `gpt-5*`, `gpt-5.*-codex-*`, `sonnet-4.*`, `opus-4.*`, `gemini-3.1-pro`, `grok`. Caveats **verified in spirit by Cursor staff replies**:

- CLI model list can be a **subset** of the IDE (e.g. some Haiku tiers intentionally missing).  
- Subagents often **do not inherit** the parent model; usage may show a different slug (e.g. Composer fast / GPT medium).  
- Valid slugs: list with `agent models` / `cursor-agent --list-models`; invalid pins **silently fall back**.

#### User notes (treated as strategic input, not ODEI inventory)

User research emphasizing multi-provider GPT / Codex / Claude / Grok / Auto / Gemini, `/model` switching, CLI+agents+MCP+CI, and lessons for ODEI **aligns** with public docs. Those models are **Cursor’s** (or providers’) — **not** shipped by ODEI until an ODEI AI gateway routes them under ODEI auth/billing/honesty labels.

### 2.3 CLI / agents / MCP / CI capabilities (verified shape)

| Capability | Cursor behavior | ODEI implication |
|------------|-----------------|------------------|
| Interactive CLI | `agent` — Agent / Plan / Ask | Future **ODEI AI CLI** or Studio CLI that calls AI gateway — not fork Cursor CLI |
| Print / CI | `agent -p` + `--model` + output formats | ODEI AI: machine API + CI-friendly JSON; Studio optional wrapper |
| Model switch | `/model`, `--model`, list-models | ODEI AI: registry IDs; Studio UI picker binds to AI, not local provider SDKs |
| MCP | CLI respects `mcp.json` like editor | ODEI AI owns MCP policy/allowlist; Studio/extension configures project MCP |
| ACP | `agent acp` for custom clients | Pattern for “any IDE → ODEI AI” without merging products |
| Cloud handoff | `&` → cursor.com/agents | ODEI later: cloud agents under AI product; Studio attaches UX |
| Rules / AGENTS.md | Shared with editor | Studio workspaces ship rules; **evaluation & tool policy** stay AI |
| Subagents | Pin / inherit / team overrides | ODEI AI agent runtime; Studio orchestrates *build goals*, not provider routing |

---

## 3. Cursor.com workspace surfaces

### 3.1 What “Cursor workspace” means

Not a single window — an **operating system for agents**:

| Surface | Role (verified) |
|---------|-----------------|
| **Desktop IDE** | Code-OSS-derived workbench + proprietary AI (Tab, chat, Composer, indexing) |
| **Agents Window** (Cursor 3) | Agent-first UI across local / worktree / cloud / SSH; parallel agents |
| **Web** | [cursor.com/agents](https://cursor.com/agents) — start/manage cloud agents (deep-dive: [`CURSOR_COM_AND_AGENTS_SURFACE_RESEARCH.md`](./CURSOR_COM_AND_AGENTS_SURFACE_RESEARCH.md)) |
| **Mobile** | Cursor iOS — cloud agents |
| **CLI** | Same modes/tools; CI/scripts; worktrees |
| **Integrations** | Slack, GitHub/Bitbucket, Linear, Teams (per docs/changelog) |
| **Team dashboard** | Billing, usage, SSO, model/admin policy, team marketplace (rules/skills/plugins), secrets for cloud agents |

### 3.2 Mapping to ODEI surfaces (today)

| Cursor surface | Closest ODEI today | Owner (target) |
|----------------|--------------------|----------------|
| Desktop IDE | Extension 0.3.0 on Cursor/VS Code; Desktop Code-OSS **scaffold only** | **Studio** |
| Agents home UX | Next `:3002/app` (Cursor-*like* chrome; template builds) | **Studio** |
| Editor | `:3002/editor` Monaco + path-bridge | **Studio** |
| Cloud agents dashboard | Marketing IA only (`apps/ai` Agents page) | **ODEI AI** (planned) |
| CLI agent | None ODEI-owned | **ODEI AI** CLI/SDK later; Studio may wrap |
| Team admin / AI billing | Product MACs (shells); no org AI metering | **ODEI AI** + Identity/Pay |
| Model registry / marketplace | `apps/ai` IA pages (not live gateway) | **ODEI AI** |
| MCP / tool governance | Not shipped | **ODEI AI** |

---

## 4. Inventory — what exists vs planned

### 4.1 ODEI AI

| Path | Exists | Reality |
|------|--------|---------|
| `apps/ai/` | **Yes** — full marketing site `:5203` / `ai.odeiafrica.com` | Static shell: product tiles for Agents, Model Registry, Marketplace, Safety; status/security/roadmap; MAC |
| `ODEI AI/` | **Yes** — docs suite + Word briefs | Holistic doc: maturity = briefs + OPMS heuristics; **Studio LLM deferred**; must become **Model Router** |
| Live Model Router / gateway API | **Yes (P0)** | `apps/ai/api/handler.mjs` on `:5203` `/v1/*` — local_sim + optional configured providers; see [`ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`](./ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md) |
| Live RAG / MCP governance / org AI billing | **No** | IA + papers only |
| OPMS Copilot/Mentor/Fraud | **Partial** | Rule-based / optional `SCF_LLM_*` — **not** ODEI AI product gateway |

### 4.2 ODEI Studio

| Path | Exists | Reality |
|------|--------|---------|
| `apps/studio/` | **Yes** — website + MAC `:5226` | Marketing; honesty banners; API-hydrated MAC Phase 1.5 |
| `ODEI Studio/apps/web` | **Yes** — Next `:3002` `/app` + `/editor` | Cursor-like Agents + Monaco editor; **not** full Cursor.com |
| `ODEI Studio/packages/api` | **Yes** — Express `:4000` | Template orchestrator + **ModelRouter consumer** (`ODEI_AI_URL` → `:5203`); template fallback when AI down |
| Path-bridge `:4010` | **Yes** | Absolute FS companion (Phase 2b) |
| Extension `odei-studio` **0.3.0** | **Yes** | Host Git/Terminal/LSP; `odei.modelRouterUrl` default `:5203` + status-bar health |
| Desktop Code-OSS | **Scaffold** | `ODEI Studio/desktop/` — **no binary** |
| Live LLM agents | **Planned** | status.json: LLM agents planned; honesty: never claim live LLM team |

### 4.3 Confirmed split (do not reverse)

```
ODEI AI  = intelligence infrastructure
           routing · MCP policy · RAG · governance · model/agent marketplace · org AI billing

ODEI Studio = creator / developer platform
           IDE chrome · builders · deploy · Agents UX
           ──consumes──► ODEI AI (API)

Shared rails = Identity (ODID) · registry/ports · honesty · Pay (seats) · Core (later)
```

---

## 5. Mapping table — Cursor capability → ODEI ownership

| Cursor capability | ODEI AI | ODEI Studio | Shared rails |
|-------------------|---------|-------------|--------------|
| Multi-provider model catalog | **Own** registry + allowlists | UI picker / display only | — |
| Auto / router | **Own** ModelRouter | Call with intent + constraints | — |
| Org AI billing / usage meters | **Own** | Show Studio-consumed usage | Pay / Identity |
| Tab / FIM completion (optional) | Model + ranking service | Editor integration surface | — |
| Chat / Composer / agents runtime | Agent runtime + tools policy | Agents home, goal UX, build orchestration | — |
| Rules / skills store | Marketplace + eval gates | Project `.odei` / workspace rules UX | — |
| MCP server registry & policy | **Own** | Project `mcp` config UX | — |
| IDE chrome (explorer, SCM UI, PTY) | **Do not own** | **Own** (web + extension + future Desktop) | — |
| Path / workspace FS | — | Path-bridge + Desktop FS | — |
| Cloud agent VMs | **Own** (future) | Attach / handoff UX | Core cloud |
| Team admin (AI policy) | **Own** AI admin | Studio product MAC (builds/uploads) | Identity SSO |
| CI agent print mode | **Own** API | Optional Studio CLI wrapper | — |
| Template / goal builders | — | **Own** `@odei/build` today | — |
| Extension host / marketplace (IDE) | — | **Own** (Open VSX later) | — |
| Claiming “GPT-5 live” | Only when **gateway live** + honesty | Never alone | Honesty policy |

---

## 6. Why independence is correct for this monorepo

1. **Stack ADR** — Products keep **independent domains/ports**; interconnect by URL/contract (`ODEI_ECOSYSTEM_STACK_STRATEGY`, `INDEPENDENT_DOMAIN_HOSTING`). Merging AI+Studio into one host fights that formula.  
2. **Build order** — ODEI AI is **P3 shared infrastructure** for Copilot, Mentor, SCF, Studio, Pay fraud, etc. Studio is a **consumer**, not the only consumer.  
3. **Cursor’s own split** — Code-OSS IDE chrome ≠ proprietary model routing/billing. ODEI should mirror the *boundary*, not the closed IP.  
4. **Honesty & maturity** — AI marketing IA can advance without implying Studio is “full Cursor”; Studio can ship editor phases without fake model claims.  
5. **Failure isolation** — Router outages, provider key rotation, and model policy stay in AI; IDE/PWA/path-bridge stay in Studio.  
6. **Commercial clarity** — ODAI token / AI marketplace / ethics board (Website IA) are AI-domain products; Studio seats/deploy are Studio-domain.

**Anti-pattern:** Putting provider SDKs and org AI billing inside Studio API “because Agents UI lives there.” That recreates per-app prompt spaghetti the holistic AI doc already rejects.

---

## 7. Integration contract — Studio calls AI

### 7.1 Direction

```
Studio Web / Extension / future Desktop / CI
        │  HTTPS + ODID (planned) / interim API key
        ▼
ODEI AI Gateway (planned)  ──► Provider APIs / local models / tools / MCP
        │
        ├── ModelRouter (select + budget + policy)
        ├── Context / RAG (consented)
        ├── Agent runtime (tools, MCP, audit)
        └── Usage / billing events → Pay
```

Studio API `:4000` remains the **build orchestrator**. It should **delegate** LLM plan/generate steps to ODEI AI — not become the multi-tenant model host.

### 7.2 Suggested API shapes (contract sketch — not implemented)

| Endpoint (AI gateway) | Purpose | Studio caller |
|-----------------------|---------|---------------|
| `GET /v1/models` | Registry (id, provider, status, honesty flags) | Picker, extension status |
| `POST /v1/route` or `POST /v1/chat/completions` | Routed generation with policy envelope | Agents chat, plan |
| `POST /v1/agents/runs` | Long-running agent job | Automations / cloud later |
| `GET /v1/runs/{id}` | Status / artifacts metadata | Build UI |
| `POST /v1/mcp/invoke` (or session-bound tools) | Governed tool calls | Extension / CLI |
| Honesty headers / body fields | `model_live: false` until wired | All clients |

**Studio today:** `POST /api/v1/build` = templates. Extension `odei.modelRouterUrl` = optional future base URL for probe — **empty means not shipped**.

### 7.3 ModelRouter ownership

| Layer | Owner |
|-------|-------|
| Routing policy, keys, budgets, evals, audit | **ODEI AI** |
| `odei.modelRouterUrl` / client SDK | **Studio** (thin client) |
| Template fallback when AI down | **Studio** (honest degrade) |

### 7.4 MCP

| Concern | Owner |
|---------|-------|
| Allowlist, secrets, org MCP catalog, audit | **ODEI AI** |
| Workspace `mcp.json` UX, enable/disable per project | **Studio** |
| Claiming “MCP marketplace live” | Only after AI ships catalog |

### 7.5 Honesty phases

| Phase | Claim allowed |
|-------|----------------|
| **Now (P0)** | Template agents + Studio can call ODEI AI gateway; live = `local_sim` / Auto; frontier only if `configured` via env keys |
| **P1** | MCP tools under AI policy |
| **P2** | Marketplace listings with signed provenance — still no fake frontier claims |

---

## 8. Ownership boundaries — what each must NOT own

### 8.1 Studio should NOT own

- Model hosting / provider API key vault for the **org**  
- Org-wide AI billing, quotas, model blocklists  
- Cross-product Model Registry & agent marketplace of record  
- Claiming Cursor Tab / proprietary Cursor models  
- Unconstrained “execute anything” companion as AI substitute  

### 8.2 ODEI AI should NOT own

- Full IDE chrome (explorer, SCM UI, PTY, DAP, extension host)  
- Path-bridge / absolute FS companion  
- Studio marketing site / Studio product MAC for builds-uploads  
- Code-OSS fork branding and desktop updater  
- Forcing all Studio UX into `ai.odeiafrica.com`  

### 8.3 Shared (neither “merges” the products)

- ODID JWT, registry ports, honesty kits, Pay seats, Core notify later  

---

## 9. Phased roadmap (integration only — no merge)

### P0 — Wire Studio ModelRouter stub → real ODEI AI gateway — **DONE (2026-07-31)**

- Stand up minimal ODEI AI gateway (`apps/ai/api/handler.mjs` on `:5203`).  
- Point `odei.modelRouterUrl` / Studio API at gateway (`ODEI_AI_URL`).  
- Keep template `/api/v1/build` as fallback.  
- **Exit met:** `GET /v1/models` returns live `local_sim` (+ `auto`); frontier IDs are `planned` unless keys → `configured`. See [`ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`](./ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md).

### P1 — MCP

- AI: MCP allowlist + audit.  
- Studio: project MCP config + consent UX.  
- Extension uses AI-governed tools, not raw host bypass for org policy.

### P2 — Marketplace

- AI: model/agent/skill marketplace + governance (Website IA).  
- Studio: browse/install UX that **calls AI**, does not re-host catalog.  
- Token/governance (ODAI) stays AI-domain.

**Explicit non-goals for these phases:** Implement full ModelRouter inside this research task; merge `apps/ai` + Studio into one product; claim GPT-5/Claude availability in ODEI marketing.

---

## 10. Strategic lessons from Cursor (for ODEI)

1. **Gateway > weights** — Product power is routing, policy, pools, and surfaces — not owning every model.  
2. **One intelligence plane, many clients** — Desktop, web, CLI, CI, mobile all hit the same AI services.  
3. **Honest degrade** — Cursor still separates pools and hidden models; ODEI must label stub vs live.  
4. **Do not clone Cursor IP** — Learn the architecture letter; build ODEI AI + Studio Desktop (C via D→C) per existing parity investigation.  
5. **Independence scales the ecosystem** — Wallet, Pay, OPMS, Studio all need AI without becoming Studio.

---

## 11. Cross-links & honesty pointers

| Artifact | Update / pointer |
|----------|------------------|
| This doc | Canonical research |
| [`docs/README.md`](./README.md) | Operator docs row |
| [`apps/studio/status.json`](../apps/studio/status.json) · [`ODEI Studio/status.json`](../ODEI%20Studio/status.json) | Point at this research; ModelRouter stub |
| [`apps/studio/honesty/honesty.json`](../apps/studio/honesty/honesty.json) | Never claim live multi-vendor ODEI models |
| [`apps/ai/status.html`](../apps/ai/status.html) | Honesty note: marketing status ≠ live Model Router |
| [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) | Peer: IDE parity path; next AI slice = ODEI AI not Cursor Tab |

---

## 12. Document control

| Field | Value |
|-------|-------|
| Authoring mode | Autonomous global research + P0 implementation |
| Implementation | **P0 gateway + Studio consumer** (see [`ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`](./ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md)) |
| Next engineering step | **P1:** MCP allowlist + audit under ODEI AI |
