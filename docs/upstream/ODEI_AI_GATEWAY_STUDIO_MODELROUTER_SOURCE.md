> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ai/ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI AI Gateway ↔ Studio ModelRouter (P0)

**Date:** 2026-07-31 (UI artifact viewer + CLI verify: **2026-08-30**)  
**Status:** **P0 shipped + E2E verified** — live local gateway on `:5203`; Studio consumes it; Agents UI shows `REQUIREMENTS.md` AI section; products remain **independent**  
**Workspace:** `e:\ODEI Multi Ecosystem`

Peers: [`ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md`](./ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md) · [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](../studio/STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) · [`STUDIO_MODELROUTER_VERIFY.md`](../studio/STUDIO_MODELROUTER_VERIFY.md) · [`HONESTY_POLICY.md`](./HONESTY_POLICY.md)

---

## 0. Product split (do not reverse)

| Product | Role | Port |
|---------|------|------|
| **ODEI AI** | Intelligence layer — ModelRouter, rules, optional provider completions | `:5203` `/v1/*` |
| **ODEI Studio** | Creator/dev — Agents UX, template builds, thin AI client | App `:3002` · API `:4000` |

Studio **consumes** AI. Do **not** merge products. Template `/api/v1/build` remains the default artifact pipeline and **fallback** when the gateway is down.

---

## 1. How to run

1. Start product shells (includes AI `:5203`): `npm run dev` / `serve_product_apps` from repo root (or `npm run dev:all`).  
2. Materialize env: `npm run setup:ai-env` and `npm run setup:studio-env`.  
3. Start Studio stack: `npm run dev:studio-all` → App `:3002/app`, API `:4000`, path-bridge `:4010`.  
4. Probe:

```bash
curl -s http://localhost:5203/v1/health
curl -s http://localhost:5203/v1/models
curl -s -H "X-ODEI-Studio-Key: odei-studio-local-desk-erms-suite-9" http://localhost:4000/api/v1/models
curl -s -H "X-ODEI-Studio-Key: odei-studio-local-desk-erms-suite-9" http://localhost:4000/api/v1/ai/health
npm run verify:studio-stack
npm run verify:studio-ai-build
```

Handler: `apps/ai/api/handler.mjs` (hot-reloaded by `serve_product_apps` under `/v1/*`).

### Agents UI (manual)

1. Open **http://localhost:3002/app**  
2. Enable **Use AI ModelRouter on build** (default on unless Offline sim preference is active).  
3. Run a build → open **REQUIREMENTS.md** in the artifact viewer → confirm **`## AI ModelRouter analysis`** at the bottom (green highlight).

See [`STUDIO_MODELROUTER_VERIFY.md`](../studio/STUDIO_MODELROUTER_VERIFY.md) for troubleshooting.

---

## 2. Gateway endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/v1/health` | open | Liveness + honesty |
| `GET` | `/v1/models` | open | Catalog: `local_sim` / `configured` / `planned` |
| `POST` | `/v1/route` | optional token | `{ task, messages?, prefer?, modelId? }` → `{ modelId, provider, reason }` |
| `POST` | `/v1/complete` | optional token | Stub or real provider completion |
| `GET` | `/v1/rules` | open | Org/dev rules (`api/rules/default.json` or custom) |
| `POST` | `/v1/rules` | optional token | Replace/reset in-memory rules |

**CORS:** Studio `:3002`, website `:5226`, localhost variants.

**Auto routing:** heuristic on task complexity + prefer `cost` | `balance` | `intelligence`. Always can fall back to `local_sim`.

---

## 3. Environment variables

| Var | Product | Purpose |
|-----|---------|---------|
| `ODEI_AI_GATEWAY_TOKEN` | AI | If set, required on mutating routes (`X-ODEI-AI-Token` or `Authorization: Bearer`) |
| `OPENAI_API_KEY` | AI | Marks GPT placeholder **configured**; enables OpenAI complete |
| `ANTHROPIC_API_KEY` | AI | Marks Claude placeholder **configured** |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | AI | Marks Gemini placeholder **configured** (complete still local_sim unless wired further) |
| `XAI_API_KEY` / `GROK_API_KEY` | AI | Marks Grok placeholder **configured** |
| `ODEI_OPENAI_MODEL` / `ODEI_ANTHROPIC_MODEL` | AI | Optional model ids for provider calls |
| `ODEI_AI_URL` | Studio API | Default `http://localhost:5203` |
| `ODEI_AI_GATEWAY_TOKEN` | Studio API | Forwarded to AI when set |
| `ODEI_AI_DEFAULT` | Studio API | `true` = builds use AI unless `options.useAi: false` |
| `ODEI_AI_TIMEOUT_MS` | Studio API | Gateway fetch timeout (default 12000) |
| `ODEI_STUDIO_API_KEY` | Studio API | Existing Studio auth (unchanged) |

**Honesty:** Without provider keys, catalog shows frontier models as **planned**. With keys, status is **configured** (local demo) — **never** “production multi-tenant LLM.”

---

## 4. How Studio uses AI

```
Agents UI / extension
    → POST :4000/api/v1/build  { options.useAi, modelId, consent, context }
    → (optional) Studio API → ODEI_AI_URL /v1/route + /v1/complete
    → always   Studio template BuildPipeline for artifacts
```

- `GET /api/v1/models` — proxy to AI catalog  
- `GET /api/v1/ai/health` — probe gateway  
- Build response includes `ai` + `honesty.pipeline` = `ai_routed` | `template_fallback`
- When AI completes, `@odei/build` appends **`## AI ModelRouter analysis`** to `REQUIREMENTS.md` (and architecture docs) via `appendAiSection()` using `options.aiCompletion` populated by the API
- Agents UI (`build-results.tsx`) renders full artifact **content** — not filenames only

### Consent model

| Context | Default | Behavior |
|---------|---------|----------|
| Workspace **name** / **path** | Allowed | Sent when client provides them |
| File **snippets** | **Off** (`consent.includeRepoSnippets: false`) | Only if user opts in; **client-supplied** excerpts only; size-capped (gateway + Studio). **Never** auto-read whole repo on the server |

---

## 5. Extension

- Setting `odei.modelRouterUrl` default: `http://localhost:5203`  
- Status bar item probes `GET /v1/health`  
- Empty string disables the AI probe; templates still work  
- Not Cursor Tab AI

---

## 6. Honesty labels

| Label | Meaning |
|-------|---------|
| `local_sim` | Stub / echo completion — always available |
| `configured` | Provider env key present; call attempted |
| `planned` | Listed for UI honesty; not live |
| `ai_routed` | Studio build attached AI route/complete |
| `template_fallback` | Template agents only (AI off or down) |

Desktop Code-OSS remains **scaffold only** until CI produces a binary.

---

## 7. Verify

```bash
# Stack probes (:5226, :3002/app, :4000, :4010, :5203, API key gate)
npm run verify:studio-stack

# Full ModelRouter build — ai_routed + REQUIREMENTS.md AI section
npm run verify:studio-ai-build

# Typecheck (optional)
cd "ODEI Studio" && npm run typecheck -w @odei/api
cd "ODEI Studio" && npm run typecheck -w @odei/web
```

Manual UI: **http://localhost:3002/app** → build with ModelRouter on → **REQUIREMENTS.md** viewer.

Do **not** claim GPT-5 / Claude / Grok / Gemini as ODEI-live unless `/v1/models` shows `status: configured` (and even then: not multi-tenant production).
