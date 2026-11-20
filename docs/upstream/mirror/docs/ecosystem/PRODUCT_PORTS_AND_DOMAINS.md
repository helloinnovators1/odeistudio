> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/PRODUCT_PORTS_AND_DOMAINS.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/PRODUCT_PORTS_AND_DOMAINS.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Product Ports & Domains — Independent Addresses, Interconnected Stack

**Updated:** 2026-09-03  
**Principle:** Each product has its **own local port** and **future production hostname**, while sharing auth/API/docs rails (interconnect).

**Complete product map:** [`ODEI_MULTI_ECOSYSTEM_PRODUCT_MAP.md`](ODEI_MULTI_ECOSYSTEM_PRODUCT_MAP.md)

**Live Surface · URL · Status:** [`PRODUCT_URLS_LIVE_STATUS.md`](PRODUCT_URLS_LIVE_STATUS.md)

**Registry (machine-readable):** [`../apps/ecosystem-registry.json`](../apps/ecosystem-registry.json)

---

## Why

OPMS already runs at `http://localhost:5173/`. ODEI Studio is split: **website** `http://localhost:5226/` and **App** `http://localhost:3002/app`.  
The same formula is applied to every product so each can later be hosted on an **independent domain** without untangling a monolith UI.

## Interconnect (shared)

| Rail | Address |
|------|---------|
| OPMS API (interim shared backend) | `http://127.0.0.1:8002` |
| Docs library | `http://localhost:8765/docs/` |
| OPMS MAC UI | `http://localhost:5173/` |
| ODEI Studio website | `http://localhost:5226/` |
| ODEI Studio App | `http://localhost:3002/app` |
| Future ODEI Core | `http://localhost:5206/` → `https://core.odeiafrica.com` |

Cross-origin: product shells expose `window.ODEI_INTERCONNECT`. Production should use a shared parent domain cookie / SSO via **ODEI Identity** (`id.odeiafrica.com`).

---

## Address map

| ID | Product | Port | Local URL | Named local | Production host |
|----|---------|-----:|-----------|-------------|-----------------|
| `multi-ecosystem` | **ODEI Multi-Ecosystem** (master) | 5180 | http://localhost:5180/ · `/civilizational/` · `/ecosystem-map.html` | `multi.localhost` | `multi.odeiafrica.com` |
| `opms` | OPMS (MAC) | 5173 | http://localhost:5173/ | `opms.localhost` | `mac.odeiafrica.com` |
| `studio` | ODEI Studio (website) | 5226 | http://localhost:5226/ | `studio.localhost` | `studio.odeiafrica.com` |
| `studio-app` | ODEI Studio App | 3002 | http://localhost:3002/app | `app.studio.localhost` | `app.studio.odeiafrica.com` |
| `docs` | Docs Library | 8765 | http://localhost:8765/ | `docs.localhost` | `docs.odeiafrica.com` |
| `api` | OPMS API | 8002 | http://localhost:8002/ | `api.localhost` | `api.odeiafrica.com` |
| `academy` | ODEI Academy | 5201 | http://localhost:5201/ | `academy.localhost` | `academy.odeiafrica.com` |
| `cloud` | ODEI Cloud | 5202 | http://localhost:5202/ | `cloud.localhost` | `cloud.odeiafrica.com` |
| `ai` | ODEI AI | 5203 | http://localhost:5203/ | `ai.localhost` | `ai.odeiafrica.com` |
| `chain` | ODEI Chain OS | 5204 | http://localhost:5204/ | `chain.localhost` | `chain.odeiafrica.com` |
| `communications` | ODEI Communications | 5205 | http://localhost:5205/ · **chat desk** `/app/chat.html` · Video Chat Meet overlay | `comms.localhost` | `comms.odeiafrica.com` |
| `core` | ODEI Core | 5206 | http://localhost:5206/ | `core.localhost` | `core.odeiafrica.com` |
| `defi` | ODEI DeFi | 5207 | http://localhost:5207/ | `defi.localhost` | `defi.odeiafrica.com` |
| `dex` | ODEI DEX | 5208 | http://localhost:5208/ · **`/app/`** trading shell · `/dashboard/` · `/admin/` | `dex.localhost` | `dex.odeiafrica.com` |
| `earn` | ODEI Earn | 5209 | http://localhost:5209/ | `earn.localhost` | `earn.odeiafrica.com` |
| `exchange` | ODEI Exchange | 5210 | http://localhost:5210/ | `exchange.localhost` | `exchange.odeiafrica.com` |
| `foundation` | ODEI Foundation | 5211 | http://localhost:5211/ | `foundation.localhost` | `foundation.odeiafrica.com` |
| `launchpad` | ODEI Launchpad | 5212 | http://localhost:5212/ | `launchpad.localhost` | `launchpad.odeiafrica.com` |
| `marketplace` | ODEI Marketplace | 5213 | http://localhost:5213/ | `marketplace.localhost` | `marketplace.odeiafrica.com` |
| `merchant` | ODEI Merchant Platform | 5214 | http://localhost:5214/ | `merchant.localhost` | `merchant.odeiafrica.com` |
| `pay` | ODEI Pay | 5215 | http://localhost:5215/ | `pay.localhost` | `pay.odeiafrica.com` |
| `store` | ODEI Store | 5216 | http://localhost:5216/ | `store.localhost` | `store.odeiafrica.com` |
| `switch` | ODEI Switch | 5217 | http://localhost:5217/ | `switch.localhost` | `switch.odeiafrica.com` |
| `tokens` | ODEI Tokens | 5218 | http://localhost:5218/ | `tokens.localhost` | `tokens.odeiafrica.com` |
| `treasury` | ODEI Treasury | 5219 | http://localhost:5219/ | `treasury.localhost` | `treasury.odeiafrica.com` |
| `wallet` | ODEI Wallet | 5220 | http://localhost:5220/ · **`/app/`** UA · `/dashboard/` · `/admin/` | `wallet.localhost` | `wallet.odeiafrica.com` |
| `odel-hub` | ODEL Hub | 5221 | http://localhost:5221/ | `odel.localhost` | `odel.odeiafrica.com` |
| `odel-manager` | **ODEL Manager** | 5240 | http://localhost:5240/app/ | — | (Hub campus console) |
| `odel-lms` | **ODeLHubLMS** | 5241 | http://localhost:5241/ | — | Hub LMS · shared desk chrome reference |
| `odel-chat` | **ODELChat** | 5242 | http://localhost:5242/ | — | (uses OMSG :5205) |
| `online-banking` | **OnlineBanking** (partner) | 5243 | http://localhost:5243/ | — | Partner desk chrome shell |
| `online-banking-laravel` | **OnlineBanking Laravel** | 5244 | http://localhost:5244/ | — | Laravel 5.7 app (PHP 7.4 / Docker); not host PHP 8.2 |
| `odelhub-pay` | **ODELHUB Pay** | 5231 | http://localhost:5231/ | — | Settlement · not ODEI Pay :5215 |
| `identity` | ODEI Identity | 5222 | http://localhost:5222/ | `id.localhost` | `id.odeiafrica.com` |
| `dicei` | DiCEI Africa | 5223 | http://localhost:5223/ | `dicei.localhost` | `dicei.odeiafrica.com` |
| `coincore` | **CoinCore by ODEIAfrica** | 5224 | http://localhost:5224/ · **`/app/`** markets · `/dashboard/` · `/admin/` | `coincore.localhost` | `coincore.odeiafrica.com` |
| `membership` | **ODEI Membership** | 5225 | http://localhost:5225/ · **`/app/`** plans · `/dashboard/` · `/admin/` | `membership.localhost` | `membership.odeiafrica.com` |
| `assessmentverse` | **AssessmentVerse OS** (Flask print desk) | 5001 | http://127.0.0.1:5001/ | — | `python app.py` in `AssessmentVerseOS\AI Students Report Genarator` — [INDEX.md](../AssessmentVerseOS/AI%20Students%20Report%20Genarator/docs/INDEX.md) · [RESULTS_CARDS_AND_PROMOTION.md](../AssessmentVerseOS/AI%20Students%20Report%20Genarator/docs/RESULTS_CARDS_AND_PROMOTION.md) |

---

## Run product shells

```powershell
cd "C:\Users\Software Innovations\Desktop\ODEI Multi Ecosystem\apps"
node serve_product_apps.mjs
```

Or: `START_PRODUCT_APPS.bat` from ecosystem root / `apps/`.

Does **not** replace OPMS/Studio/Docs/API — start those separately (`START_LOCAL_SERVICES.bat`).  
Does **not** start AssessmentVerse `:5001` — that is Flask, not a product shell.

## Production hosting formula

```
https://{prod_host}/  →  product frontend (this shell → full app)
https://api.odeiafrica.com/ → shared APIs (evolve from OPMS API → Core)
https://id.odeiafrica.com/  → ODID SSO
```

Each product CI/CD deploys **only its app** to its host; interconnect URLs come from registry/env.

## Regenerator

`python _generate_product_apps.py`
