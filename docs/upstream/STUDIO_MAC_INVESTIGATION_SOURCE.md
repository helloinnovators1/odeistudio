> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_MAC_FULLY_OPERATIONAL_INVESTIGATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_MAC_FULLY_OPERATIONAL_INVESTIGATION.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio MAC — Fully Operational Investigation

**Audited:** 2026-07-30  
**Remediated:** 2026-07-30 — see [`STUDIO_MAC_REMEDIATION.md`](STUDIO_MAC_REMEDIATION.md) · [`STUDIO_HOLISTIC_SCAN_REMEDIATION.md`](STUDIO_HOLISTIC_SCAN_REMEDIATION.md)  
**Workspace:** `e:\ODEI Multi Ecosystem`  
**Nature:** Original pass was research only; remediation closed Phase 1.5 gaps below.  
**Related:** [`STUDIO_DEEP_AUDIT.md`](STUDIO_DEEP_AUDIT.md) · [`ODEI_COMMAND_CENTER.md`](ODEI_COMMAND_CENTER.md) · [`PRODUCT_MAC_CONSOLES.md`](PRODUCT_MAC_CONSOLES.md) · `apps/studio/status.json` · `ODEI Studio/status.json` · `apps/multi-ecosystem/command/macs.json`

---

## Executive summary (post-remediation)

**Is Studio MAC fully operational for local Phase 1.5?** **Yes** (API-hydrated, honest ceilings).  
**Is it production / ODID / OPMS-depth complete?** **No.**

Staff operators on `:5226/admin/` get live surface probes, agents/builds/uploads from `:4000`, compose actions that hit the API, and correct catalog labeling. Template agents, in-memory builds, and local uploads remain the honesty ceiling.

### Top 5 gaps — remediation status

| # | Gap | Status |
|---|-----|--------|
| 1 | No API wiring | **Fixed** — `mac-studio.js` |
| 2 | CORS blocks website→API | **Fixed** — `:5226` in `DEV_ORIGINS` |
| 3 | Health pill fake-OK | **Fixed** — real probes |
| 4 | Placeholder REC-1001 modules | **Fixed** — Build OS + planned panel |
| 5 | Auth / catalog incompleteness | **Fixed** — `studio` in product IDs + docs/manifest |

---

## Three surfaces (do not confuse)

| Surface | URL | Role | Is it the MAC? |
|---------|-----|------|----------------|
| **Studio website MAC** | `http://localhost:5226/admin/` | Operator console (shared kit SPA) | **Yes — this investigation’s subject** |
| **Studio App (Agents)** | `http://localhost:3002/app` | Cursor-inspired build workspace for members/operators | **No** — product UI that *uses* the API |
| **Editor Window** | `http://localhost:3002/editor` | Phase 2a desktop bridge (Open/Clone/SSH guidance) | **No** — IDE bridge, not admin console |
| *(also)* **Studio API** | `http://localhost:4000` | Express build/upload/agents | Backend the MAC *should* call |
| *(also)* **VS Code / Cursor extension** | `ODEI Studio/extensions/odei-studio` | Desktop operator surface for Open/Clone/SSH + API | Parallel operator rail, not browser MAC |

Command Center catalogs website and app separately (`studio` vs `studio-app` in `macs.json`). The App entry’s `"mac": "http://localhost:3002/app"` is a **misnomer** — that URL is the Agents workspace, not a Master Admin Console.

---

## A. What “MAC” means in ODEI

### Shared kit

| Piece | Path | Job |
|-------|------|-----|
| Shell SPA | `apps/_shared/mac/mac.js` · `mac.css` | Hash-routed modules, KPI deck, Ctrl+K search, Composer/Manage stubs |
| Per-product copy | `apps/*/admin/` | `index.html` + `config.json` + often a local `mac.js`/`mac.css` fork |
| Auth | `apps/_shared/auth/odei-auth.js` | Roles: `member` → `operator` / `admin` / `master_admin`; staff invite; `enforceSurfaceAccess('staff')` on MAC |
| Modular workspace | `apps/_shared/modular/` | Extra multi-tab mount inside MAC (`data-odei-modular="mac"`) |
| Honesty | `apps/_shared/honesty/` (copied per product) | Maturity banners — never claim live early |
| Dashboard (member) | `apps/*/dashboard/` | Member surface; MAC link shown only for staff |

**Login → MAC gating (evidence):**

1. Default signup → `member` → `/dashboard/`
2. Staff invite (`ODEI-OPERATOR` / `ODEI-ADMIN` / `ODEI-MAC` on localhost only) → staff role → `/admin/`
3. MAC pages call `ODEIAuth.enforceSurfaceAccess('staff')` — unauthenticated → login; member → `/dashboard/?denied=staff`
4. Studio MAC: `apps/studio/admin/index.html` lines 54–55

### Command Center catalog & health probes

- Catalog: `apps/multi-ecosystem/command/macs.json`
- UI: `apps/multi-ecosystem/command/command.js` — `probeUrl(site)` + `probeUrl(mac)` per row (HTTP fetch; `ok` / `degraded` / `down`)
- Studio website row: port **5226**, MAC `http://localhost:5226/admin/`
- Studio App row: port **3002**, “mac” points at `/app` (Agents UI health only)
- **Does not** probe Studio API `:4000` as its own console row

### Maturity ladder (honest labels used in Studio)

| Label | Meaning |
|-------|---------|
| `live` | Website shell serving |
| `local_live` | App/API up locally with real HTTP |
| `local_sim` / `local_validated` | Deterministic / disk-validated, not production |
| `planned` | Not built |

---

## B. Current Studio MAC state

### Files audited

| File | Role |
|------|------|
| `apps/studio/admin/index.html` | Shell + staff gate + honesty + modular |
| `apps/studio/admin/config.json` | Modules, KPIs, honesty, nav (updated 2026-07-30) |
| `apps/studio/admin/mac.js` | Generic shared-kit SPA (**no** `ODEI_MAC` export, **no** API hydrate) |
| `apps/studio/admin/mac.css` | Dark OPMS-inspired chrome |

### What pages claim vs what is wired

| Module / claim | Wired to real data? | Reality |
|----------------|---------------------|---------|
| Dashboard KPIs (`Active operators: 6`, `API health: OK`) | **No** | Static JSON |
| Activity feed | **No** | Static narrative |
| Honesty matrix | **Partial** | Honest *labels* in config; not live probes |
| Platform modules catalog | **No** | Static vision catalog |
| Agents / Builds / Uploads / Workspaces / Api Keys | **No** | Sample rows (`AGT-PLAN`, `BLD-1001`, …) |
| Analytics → Developer | **No** | Generic `REC-1001` placeholders |
| System health rows | **No** | Static status strings |
| Composer “New …” | **No** | `alert(product + " MAC · compose — connect product API next.")` |
| `#mac-health` pill | **No** | Always `ok` class + config string |

### Auth gating

- **Staff gate present** on MAC (`enforceSurfaceAccess('staff')`) — good
- Member dashboard hides MAC link until staff (`apps/studio/dashboard/index.html`)
- Public marketing `index.html` does **not** advertise `/admin/` in the audited hero links
- Modular workspace still lists `/admin/` and Command Center cards for anyone who mounts it (topology discoverable after login surfaces; Command Center itself is staff-gated on `:5180`)

### Branding / honesty

- Website styles: Studio green (`#00a86b`) + Instrument Serif / DM Sans — **Studio-branded**, not Exchange purple leftovers
- MAC chrome: shared dark shell (OPMS-inspired) — intentional kit look
- Honesty block in `config.json` correctly states Phase 1.5 / template agents / local uploads / optional API key

### Port / registry map

| Layer | Port / path | Evidence |
|-------|-------------|----------|
| Website | `:5226` | `config.json`, `apps/studio/status.json` |
| App | `:3002/app` | `ODEI Studio/status.json` |
| Editor | `:3002/editor` | same |
| API | `:4000` | `packages/api/src/index.ts` |
| Prod hosts | `studio.odeiafrica.com` / `app.studio.odeiafrica.com` | status + registry |

---

## C. Reference “fully operational” MACs

### 1. Communications (OMSG) — best shared-kit reference for *wired* MAC

| Checklist item | Status | Evidence |
|----------------|--------|----------|
| Login + staff elevation | Yes | `enforceSurfaceAccess('staff')` |
| Domain store behind MAC | Yes | `comms-store.js` + `mac-comms.js` |
| Live KPIs from store | Yes (`local_sim` / chat `local_live`) | `mac-comms.js` patches `state.config.kpis` |
| Module rows hydrated | Yes | channels, templates, delivery, audiences, … |
| `ODEI_MAC.refresh` hook | Yes | `communications/admin/mac.js` exposes `window.ODEI_MAC` |
| Honesty / status | Present | store + config labels |
| Real remote `/v1/*` mutate | Partial — chat local_live; notify mostly local_sim | honesty in config |
| Deploy/ops hooks | Limited | product-local |

**Operational checklist distilled:** staff gate → domain store/API → hydrate `config` at boot → expose refresh → honest labels → Composer/Manage that *mutate* the store (Communications hydrate is stronger than Studio; many products still stub composers).

### 2. OPMS (`:5173/admin`) — reference *full* React MAC

| Checklist item | Status | Evidence |
|----------------|--------|----------|
| Full product MAC (not shared static kit) | Yes | OPMS README routes `/admin/*` |
| JWT + RBAC | Yes (demo JWT) | OPMS README Auth row |
| Live domain modules | Yes (tokens, vesting, factories, …) | `/admin/tokens`, chains, jetton, … |
| Backend API | Separate FastAPI (`:8002`) | Command Center notes |
| Interconnect / marketplace | Yes | Marketplace, event bus (simulated where noted) |

OPMS is the **design/IA north star**. Shared-kit MACs (including Studio) are Phase 1 shells aiming toward that depth — not OPMS clones.

### 3. CoinCore — honesty-forward shared kit

- Strong honesty matrix documenting `/v1/markets` live_feed vs simulated OHLCV
- MAC shell still largely config-driven (no Communications-style hydrate helper found)
- Useful as **honesty pattern**, not as “fully wired” reference

---

## D. Studio-specific MAC domain (Build OS)

### Modules a fully operational Studio MAC must own

| Domain | Operator need | API / surface available today |
|--------|---------------|-------------------------------|
| **Builds** | List/inspect/re-run builds | `GET /api/v1/builds`, `GET /api/v1/build/:id`, `POST /api/v1/build` |
| **Agents** | Roster / template vs LLM | `GET /api/v1/agents` |
| **Goals / tasks** | Plan progress | `POST /api/v1/goals/plan`, `GET /api/v1/goals/:id/tasks` |
| **Uploads** | Validated local images | `POST/GET /api/v1/uploads` |
| **Workspaces** | Tenancy | Implicit `workspaceId` on builds — **no** dedicated workspace CRUD API |
| **API keys** | Interim gate status | Env `ODEI_STUDIO_API_KEY`; MAC should show auth mode from `GET /` or `/health` |
| **System health** | Website / App / Editor / API | Need multi-origin probes; API `GET /health` |
| **Editor bridge** | Extension install, Open/Clone/SSH ops | Extension + `:3002/editor` — not MAC-wired |
| **Extension install** | Operator guide / version | `extensions/odei-studio` package |

### Studio API routes a MAC could call

From `ODEI Studio/packages/api/src/index.ts`:

| Method | Path | Notes |
|--------|------|-------|
| GET | `/` | Service meta, auth mode, docs |
| GET | `/health` | `status: ok`, persistence honesty |
| GET | `/api/v1/agents` | Orchestrator registry |
| POST | `/api/v1/goals/plan` | Create goal + plan |
| GET | `/api/v1/goals/:goalId/tasks` | Tasks + progress |
| POST | `/api/v1/uploads` | Base64 image → `.uploads/` |
| GET | `/api/v1/uploads/:id` | File or `?meta=1` |
| POST | `/api/v1/build` | Template pipeline (not LLM) |
| GET | `/api/v1/build/:buildId` | Single build |
| GET | `/api/v1/builds` | List in-memory builds |

Auth: optional `ODEI_STUDIO_API_KEY` via `X-ODEI-Studio-Key` or Bearer.

### Critical connectivity gap: website MAC ↔ API

```
DEV_ORIGINS = [
  localhost:3002, 127.0.0.1:3002,
  studio.localhost:8080, studio.localhost,
  localhost:8080, 127.0.0.1:8080
]
```

**`http://localhost:5226` is absent.** Even if `mac-studio.js` were written tomorrow, browser fetches from the website MAC to `:4000` would fail CORS until `:5226` (and optionally `studio.localhost:5226`) are allowlisted.

App `:3002` can talk to the API today; **MAC cannot**.

### VS Code extension vs browser MAC

| Capability | Extension | Website MAC |
|------------|-----------|-------------|
| Call API `:4000` | Yes (no browser CORS) | Blocked until CORS + client |
| Open/Clone/SSH | Native | Via Editor Phase 2a links only |
| Staff RBAC | IDE settings / trust | `ODEIAuth` session |
| Fleet / multi-tenant ops | Weak | Natural home for MAC |

Fully operational Studio ops likely need **both**: MAC for fleet/KPIs/honesty; extension for desktop filesystem rails.

---

## E. Fully operational definition + gap matrix

**Definition (concrete):** Studio MAC is fully operational when a staff user on `:5226/admin/` can:

1. Authenticate with staff role (or master_admin) and be denied as member  
2. See **live** health for Website, App, Editor, API (real probes, honest down states)  
3. Load **live** KPIs: build count, agent count, upload count, API auth mode from `:4000`  
4. Browse/manage **real** builds, agents, uploads (at least read; write for builds/uploads where safe)  
5. Never claim LLM / signed S3 / ODID until those exit criteria pass  
6. Appear correctly in Command Center + product MAC docs  
7. Optionally deep-link to App / Editor / extension install without conflating those UIs as “the MAC”

| Capability | Required for fully operational Studio MAC | Current status | Evidence path | Gap |
|------------|-------------------------------------------|----------------|---------------|-----|
| Staff auth gate | Yes | **Done (local_sim)** | `apps/studio/admin/index.html` + `odei-auth.js` | Prod ODID still planned |
| Honesty banner / matrix | Yes | **Done (labels)** | `config.json` honesty + honesty mount | Must stay accurate as features land |
| Shared MAC shell UX | Yes | **Done** | `admin/mac.js` · tabs · Ctrl+K | Shell ≠ operational |
| Command Center listing | Yes | **Partial** | `macs.json` has studio | Missing from `PRODUCT_MAC_CONSOLES.md` / manifest |
| Live API health pill | Yes | **Missing** | Static `config.health` | Probe `GET :4000/health` |
| Live App/Editor/Website probes | Yes | **Missing** | Static system-health rows | Multi-origin probe panel |
| CORS MAC→API | Yes | **Missing** | `DEV_ORIGINS` omits `:5226` | Add origin |
| Agents module ← API | Yes | **Missing** | Sample `AGT-*` rows | `GET /api/v1/agents` |
| Builds module ← API | Yes | **Missing** | Sample `BLD-*` | `GET /api/v1/builds` |
| Uploads module ← API | Yes | **Missing** | Sample `UP-*` | List endpoint incomplete (GET by id only); need index or MAC-side tracking |
| Workspaces CRUD | Yes (ops) | **Missing** | Sample `ws_*` | No workspace API |
| API key ops panel | Yes | **Missing** | Static KEY rows | Read `/health.auth`; no key mint API |
| Composer mutations | Yes | **Stub** | `alert(…)` | Wire POST build/upload |
| Analytics / Reports / Users / … | Nice-to-have later | **Placeholder** | `REC-1001` | Defer or remove until real |
| Master admin seed includes studio | Yes | **Missing** | `ECOSYSTEM_PRODUCT_IDS` has no `studio` | Add product id |
| ODID JWT on MAC + API | Production yes | **Planned** | honesty matrix Authentication | Phase 3 |
| LLM agent pipeline | Product yes; MAC observe | **Planned / local_sim** | template agents | Phase 2 |
| Signed cloud uploads | Production yes | **Planned** | local_validated | Phase 2+ |
| Extension install ops | Yes | **Partial** | Extension exists | MAC docs/deep-link only |
| Confuse App as MAC | Must avoid | **Catalog risk** | `macs.json` studio-app `mac` = `/app` | Clarify label |

**Nothing above marked Done without file evidence.** Phase 1.5 / `local_sim` / `local_validated` remain the honest ceiling for build pipeline and uploads.

---

## F. Recommended implementation roadmap (research only)

### P0 — Auth honesty + health (unblocks trust)

1. Probe `GET http://localhost:4000/health` from MAC; paint `#mac-health` from real result (fail → warn, not fake `ok`)  
2. System-health module: probe `:5226`, `:3002/app`, `:3002/editor`, `:4000/health`  
3. Add `:5226` (+ named vhost if used) to API `DEV_ORIGINS`  
4. Add `studio` to `ECOSYSTEM_PRODUCT_IDS` / master seed  
5. Fix catalog docs: `PRODUCT_MAC_CONSOLES.md`, Command Center note that studio-app is **not** a MAC  
6. Strip or clearly badge generic placeholder modules (Analytics…) as `planned`

### P1 — Live build/upload/agent KPIs

1. Add `mac-studio.js` (Communications pattern) hydrating from API  
2. Expose `window.ODEI_MAC = { state, refresh }` like Communications  
3. Dashboard KPIs from `/api/v1/builds`, `/api/v1/agents`, `/health`  
4. Builds / Agents Manage tables from live JSON  
5. Uploads: add `GET /api/v1/uploads` list endpoint (today only get-by-id) then bind MAC  
6. Optional API key header from operator-entered session storage (never claim ODID)

### P2 — Workspace / editor bridge ops

1. Workspace registry API (or document single `ws_default` honestly)  
2. MAC deep-links: Open App, Open Editor, Extension install instructions  
3. Editor bridge status from honesty / status.json  
4. Build composer that POSTs `/api/v1/build` with honesty toast (`local_sim`)

### P3 — Production ODID

1. Replace localStorage roles with Identity JWT  
2. API rejects anonymous; MAC uses bearer from ODID  
3. Signed object storage + malware scan  
4. LLM agents; MAC observes live runs  
5. Edge deploy of MAC + API with locked CORS

---

## Cross-links updated by this investigation

- This document: `docs/STUDIO_MAC_FULLY_OPERATIONAL_INVESTIGATION.md`
- `apps/studio/status.json` — `mac` surface pointer
- `ODEI Studio/status.json` — `mac` honesty note
- `docs/ODEI_COMMAND_CENTER.md` — Studio MAC vs App clarification
- `docs/PRODUCT_MAC_CONSOLES.md` — Studio row + investigation link
- `apps/multi-ecosystem/command/macs.json` — note clarifying studio-app is not MAC
- `docs/README.md` — catalog entry

---

## Verdict restated

Studio MAC is a **staff-gated, honesty-aware Phase 1.5 operator shell**. It is **not** fully operational as a Build OS admin console. Closest shared-kit peer for the *wiring pattern* is **Communications** (`mac-comms.js` + store). Closest *product depth* peer is **OPMS**. Closing the top five gaps (API wire + CORS + real health + replace placeholders + catalog/auth seed) is the minimum path from shell → operational.

