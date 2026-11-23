> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_MULTI_ECOSYSTEM_WHOLE.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ecosystem/ODEI_MULTI_ECOSYSTEM_WHOLE.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Multi-Ecosystem — Whole-system documentation (canonical)

**Status:** Canonical staff + builder map · **Honesty:** companion directory + independent products · **local_sim** until declared otherwise  
**Updated:** 2026-09-18  
**Command Center:** http://localhost:5180/command/ · **prod:** https://odeicore.vercel.app/command/ · **This doc (CC):** http://localhost:5180/command/ecosystem.html  
**GitHub · Atlas · Vercel:** http://localhost:5180/command/GITHUB_MONGODB_VERCEL.md · [`docs/ops/deploy/COMMAND_CENTER_GITHUB_MONGODB_VERCEL.md`](../ops/deploy/COMMAND_CENTER_GITHUB_MONGODB_VERCEL.md)  
**Docs library:** http://localhost:8765/docs/?doc=docs/ODEI_MULTI_ECOSYSTEM_WHOLE.md  
**Machine registry:** `apps/ecosystem-registry.json`  
**Ports map:** [`docs/PRODUCT_PORTS_AND_DOMAINS.md`](../PRODUCT_PORTS_AND_DOMAINS.md)
**GoldCity integration:** [`docs/integrations/GOLDCITY_EMPIRE.md`](../integrations/GOLDCITY_EMPIRE.md) · CC http://localhost:5180/command/goldcity.html

This is the **single autonomous markdown** for the **whole ODEI Multi-Ecosystem**. Per-product `ODEI_HOLISTIC_DOCUMENTATION.md` files remain product-local. This file is the **hub** they hang from. Command Center **Documentation** module publishes it. ODEI AI RAG may ingest `docs/` including this file (`local_sim` vector-lite).

**Not claimed:** a trained ODEI foundation LLM, production MoMo/card rails, or that every civilizational-map ring is live.

---

## 1. What the Multi-Ecosystem is

ODEI Multi-Ecosystem is a **directory of independent products** that share rails (auth kit, modular UI, honesty, docs library) without being one monolith.

| Surface | URL | Job |
|---------|-----|-----|
| Companion directory | http://localhost:5180/ | Front door · product cards |
| Civilizational map | http://localhost:5180/civilizational/ | Architecture rings (companion; not every ring live) |
| Ecosystem map | http://localhost:5180/ecosystem-map.html | Registry grouping |
| **Command Center** | http://localhost:5180/command/ | Staff MAC directory + this documentation + Intelligence honesty |
| **Download Center** (public) | http://localhost:5180/downloads.html |
| **Download Center** (staff) | http://localhost:5180/command/downloads.html |
| Whole-ecosystem markdown (this file) | http://localhost:5180/command/ecosystem.html | Canonical CC documentation |
| Docs library | http://localhost:8765/docs/ | Markdown reader |
| User guide index | [`docs/guides/00_USER_GUIDE_INDEX.md`](guides/00_USER_GUIDE_INDEX.md) | End-user guides |
| Hub OS product truth | [`ODEL Hub OS/docs/HUB_OS_PRODUCT_TRUTH.md`](../ODEL%20Hub%20OS/docs/HUB_OS_PRODUCT_TRUTH.md) | Campus/Hub independence |

**Honesty:** `platformNarrative: false` on the master site. Local HTTP 200 ≠ production. Primary public wedge: **ODEI Academy Curriculum Explorer beta** (`:5201`).

---

## 2. Command Center

| Item | Value |
|------|--------|
| URL | http://localhost:5180/command/ |
| Secrets | http://localhost:5180/command/secrets.html |
| Whole-ecosystem doc | http://localhost:5180/command/ecosystem.html |
| Raw markdown | http://localhost:5180/command/ODEI_MULTI_ECOSYSTEM_WHOLE.md |
| Catalog | `apps/multi-ecosystem/command/macs.json` |
| Placement spec | [`docs/ODEI_COMMAND_CENTER.md`](ODEI_COMMAND_CENTER.md) |
| Job | Staff directory of **all** product MACs · hosting secrets · **canonical ecosystem documentation** · **ODEI AI / LLM honesty** · **all-category Download Center** |
| Not | OPMS itself · a restyle of product UIs · a production LLM console |

Staff gate: `/command/` → login → staff / master_admin.

**Modules (Command Center workspace):** Consoles · Hosting · Master Admin · Health · Documentation · Intelligence · **Downloads** · Links.

---

## 3. Multi-dimensional Autonomous ODEI Multi-Ecosystem LLM (honest)

**Name:** ODEI AI / **ODAI** — intelligence infrastructure, not an IDE.  
**Gateway:** http://localhost:5203/ · API `http://localhost:5203/v1/*`  
**GPT UI:** http://localhost:5203/gpt.html  
**Tools:** http://localhost:5203/tools.html  
**Governance:** http://localhost:5203/governance-console.html  

### 3.1 Architecture (what “multi-dimensional” means)

```text
Product apps (Academy · Studio · Communications · LMS · Manager · …)
                         │
                         ▼
            ODEI AI-OS gateway (:5203 /v1/*)
     router · policy · audit · tenant · tools
         │            │             │
      models       agents        RAG (docs/)
         │            │             │
   local_sim      JSON memory    vector-lite
   + optional keyed OpenAI/Anthropic
```

| Dimension | Today | Honesty |
|-----------|-------|---------|
| Gateway / router | Live P0 `/v1/complete`, `/v1/health`, `/v1/models` | Default **`local_sim`** if no provider keys |
| Agents / orchestration | Forge catalog + `/v1/agents` | local_sim run loop — not unsupervised production agents |
| Memory | `/v1/memory` | Durable JSON on this seat, not cloud HA |
| RAG / knowledge | `/v1/rag` over `docs/` | vector-lite + path citations; this whole-ecosystem file is in `docs/` |
| Tools / forge | `/v1/forge/tools` | Local tools; no silent external side effects |
| Studio bridge | `ODEI_AI_URL` + `/v1/studio/handoff` | Studio stays independent |
| **ODEI foundation model** | **Not trained / not shipped** | Build-order **P6+** — [`docs/BUILD_ORDER_ROADMAP.md`](BUILD_ORDER_ROADMAP.md) |

### 3.2 What is not live

Production multi-tenant LLM hosting · Cursor-class model pools · MCP marketplace billing · cloud VM agents as production · Gemini/Grok complete paths until keyed · **a single proprietary “ODEI Multi-Ecosystem Based LLM” weights file**.

**Canonical AI docs:** [`docs/ODEI_AI_HOLISTIC_RESEARCH.md`](ODEI_AI_HOLISTIC_RESEARCH.md) · [`docs/ODEI_AI_OPERATING_SYSTEM.md`](ODEI_AI_OPERATING_SYSTEM.md) · [`docs/research/ai/ODEI_AI_IMPLEMENTATION_ROADMAP.md`](research/ai/ODEI_AI_IMPLEMENTATION_ROADMAP.md) · [`ODEI AI/docs/ODEI_HOLISTIC_DOCUMENTATION.md`](../ODEI%20AI/docs/ODEI_HOLISTIC_DOCUMENTATION.md)

---

## 4. Product address map (no omission of live shells)

Run: `npm run dev` from repo root.

| ID | Product | Port | Local |
|----|---------|-----:|-------|
| multi-ecosystem | Multi-Ecosystem (master) | 5180 | http://localhost:5180/ |
| opms | OPMS MAC | 5173 | http://localhost:5173/ |
| studio | ODEI Studio website | 5226 | http://localhost:5226/ |
| studio-app | ODEI Studio App | 3002 | http://localhost:3002/app |
| docs | Docs Library | 8765 | http://localhost:8765/ |
| academy | ODEI Academy | 5201 | http://localhost:5201/ |
| cloud | ODEI Cloud | 5202 | http://localhost:5202/ |
| ai | ODEI AI / ODAI | 5203 | http://localhost:5203/ |
| chain | ODEI Chain OS | 5204 | http://localhost:5204/ |
| communications | ODEI Communications / OMSG | 5205 | http://localhost:5205/app/chat.html |
| core | ODEI Core | 5206 | http://localhost:5206/ |
| defi | ODEI DeFi | 5207 | http://localhost:5207/ |
| dex | ODEI DEX | 5208 | http://localhost:5208/ |
| earn | ODEI Earn | 5209 | http://localhost:5209/ |
| exchange | ODEI Exchange | 5210 | http://localhost:5210/ |
| foundation | ODEI Foundation | 5211 | http://localhost:5211/ |
| launchpad | ODEI Launchpad | 5212 | http://localhost:5212/ |
| marketplace | ODEI Marketplace | 5213 | http://localhost:5213/ |
| merchant | ODEI Merchant Platform | 5214 | http://localhost:5214/ |
| pay | ODEI Pay | 5215 | http://localhost:5215/ |
| store | ODEI Store | 5216 | http://localhost:5216/ |
| switch | ODEI Switch | 5217 | http://localhost:5217/ |
| tokens | ODEI Tokens | 5218 | http://localhost:5218/ |
| treasury | ODEI Treasury | 5219 | http://localhost:5219/ |
| wallet | ODEI Wallet | 5220 | http://localhost:5220/ |
| odel-hub | ODEL Hub OS | 5221 | http://localhost:5221/ |
| identity | ODEI Identity | 5222 | http://localhost:5222/ |
| dicei | DiCEI Africa | 5223 | http://localhost:5223/ |
| coincore | CoinCore | 5224 | http://localhost:5224/ |
| membership | ODEI Membership | 5225 | http://localhost:5225/ |
| odelhub-pay | ODELHUB Pay | 5231 | http://localhost:5231/ |
| odel-manager | ODEL Manager | 5240 | http://localhost:5240/app/ |
| odel-lms | ODeLHubLMS | 5241 | http://localhost:5241/ |
| odel-chat | ODELChat | 5242 | http://localhost:5242/ |
| online-banking | OnlineBanking partner | 5243 | http://localhost:5243/ |
| assessmentverse | AssessmentVerse Flask desk | 5001 | http://127.0.0.1:5001/ |

Full named hosts: [`docs/PRODUCT_PORTS_AND_DOMAINS.md`](PRODUCT_PORTS_AND_DOMAINS.md).

---

## 5. ODEL Manager (campus) — Courses Short forms + ERMS

**Cache:** `desk-erms-suite-9` · Console: http://localhost:5240/app/ · Smoke: **148** checks

| View | URL |
|------|-----|
| Courses | http://localhost:5240/app/#/courses |
| Regular · Full catalog | http://localhost:5240/app/#/courses/regular/catalog |
| Regular · Short forms | http://localhost:5240/app/#/courses/regular/short |
| Inservice · Full catalog | http://localhost:5240/app/#/courses/in_service/catalog |
| Inservice · Short forms | http://localhost:5240/app/#/courses/in_service/short |
| Students roster | http://localhost:5240/app/#/students |
| ERMS Regular requisition | http://localhost:5240/app/#/erms/request/regular/requisition |
| ERMS Inservice requisition | http://localhost:5240/app/#/erms/request/in_service/requisition |

**Catalogs:** Regular **11** programmes / **339** units · Inservice **20** / **500** — rebuild: `npm run build:manager-catalog-regular` · `npm run build:manager-catalog-inservice`.

**Short forms:** **Edit short form** per row → field is editable. **Auto-save** on input (400 ms debounce) and **blur**. **Save** locks the row. **Enter** saves and locks. **Save as defaults** stores the track set. **Regenerate** uses defaults then `deriveCourseShortName()`. Empty catalog: button **Add courses on Full catalog first**.

**ERMS:** Roster auto-fill (YR/TRIM/CAT), centre profiles, validation panel, per-student unit interleave, PDF import. Map: [`docs/ERMS_EXAMINATIONS_DEPARTMENT_SUBMISSION.md`](ERMS_EXAMINATIONS_DEPARTMENT_SUBMISSION.md) · Work records: [`docs/WORK_RECORD_2026-08-26.md`](WORK_RECORD_2026-08-26.md) · [`docs/WORK_RECORD_2026-08-27.md`](WORK_RECORD_2026-08-27.md)

Guide: [`docs/guides/products/odel-manager.md`](guides/products/odel-manager.md)

---

## 6. Documentation lattice (no single-file monopoly)

| Kind | Where |
|------|--------|
| **This canonical whole-ecosystem markdown** | `docs/ODEI_MULTI_ECOSYSTEM_WHOLE.md` + CC copy `apps/multi-ecosystem/command/ODEI_MULTI_ECOSYSTEM_WHOLE.md` |
| User guides | `docs/guides/` · index `00_USER_GUIDE_INDEX.md` |
| Per-product holistic | `*/docs/ODEI_HOLISTIC_DOCUMENTATION.md` |
| Command Center placement | `docs/ODEI_COMMAND_CENTER.md` |
| Hub campus truth | `ODEL Hub OS/docs/HUB_OS_PRODUCT_TRUTH.md` |
| **Download Center** | http://localhost:5180/downloads.html · staff http://localhost:5180/command/downloads.html · API `/v1/downloads` |

---

## 7. Download Center (all categories)

**Did not exist as a whole-ecosystem surface.** ODELHUB Pay keeps its own MAC catalogue (`/admin/master#project-download`) for live tuition/credentials. Wallet has a product-local Download IA page. The Multi-Ecosystem **Download Center** is the hub for **every directory category**.

| Category | Covers |
|----------|--------|
| Learn | Academy, Hub OS, OCS, AssessmentVerse |
| Identity | Identity, Membership, Core |
| Money | Pay, Wallet, Exchange, DEX, treasury rails |
| Build | OPMS, Studio, Cloud, AI, Communications, Launchpad |
| Commerce | Marketplace, Merchant, Store |
| Infra | Chain, Foundation, Multi-Ecosystem, Docs library |
| Creator | DiCEI |
| Campus | ODEL Manager, LMS, Chat + link to ODELHUB Pay MAC downloads |
| Partners | Partner Projects, UMSC-family shells |
| User guides | `docs/guides/` audiences, onboarding, products |
| Maps & registry | Whole-ecosystem markdown, ports, `ecosystem-registry.json` |
| Intelligence | ODEI AI docs (`local_sim`; no foundation weights) |
| Ops & Command | Command Center spec, how-to-run |
| **Android APKs** | local_sim `.apk` packs per registry product (`downloads.html#apks`) |

**Downloads:** per-file markdown/JSON · **local_sim Android APK packs** · category ZIP · `?kind=documentation` · `?category=apks`. **Not:** Play Store production, `.env`, live tuition, ODEI Studio vscode dumps.

---

## 8. Related URLs (ops)

| What | URL |
|------|-----|
| Command Center Documentation | http://localhost:5180/command/ecosystem.html |
| Command Center Downloads | http://localhost:5180/command/downloads.html |
| Public Download Center | http://localhost:5180/downloads.html |
| Download catalog API | http://localhost:5180/v1/downloads |
| Command Center Intelligence | http://localhost:5180/command/# (module **Intelligence**) |
| **GitHub · Atlas · Vercel (CC)** | http://localhost:5180/command/GITHUB_MONGODB_VERCEL.md |
| **Production site / CC / Atlas ping** | https://odeicore.vercel.app/ · https://odeicore.vercel.app/command/ · https://odeicore.vercel.app/api/mongo |
| **Vercel project odeicore** | https://vercel.com/odeldevelopers-projects/odeicore/ |
| **GitHub repo** | https://github.com/infoedutechos/ODEI-Multi-Ecosystem |
| ODEI AI gateway | http://localhost:5203/v1/health |
| User guides | http://localhost:8765/docs/guides/ |
| Ecosystem tour | [`docs/guides/onboarding/ecosystem-tour.md`](../guides/onboarding/ecosystem-tour.md) |

---

## 9. GoldCity Empire (acquisition gateway) — what ODEI implements

**Partner prod:** https://goldcity-empire.vercel.app  
**Docs:** [`integrations/GOLDCITY_EMPIRE.md`](integrations/GOLDCITY_EMPIRE.md) · backlog [`integrations/ODEI_IMPLEMENTABLE_FROM_GC01_GC16.md`](integrations/ODEI_IMPLEMENTABLE_FROM_GC01_GC16.md)  
**Staff:** http://localhost:5180/command/goldcity.html

| ODEI owns (this repo) | GoldCity owns (external) |
|-----------------------|--------------------------|
| `POST :5222/v1/identity/sync` ODID ingest | Play economy · GCECP/GCEC · ENTER ODEI UI |
| `GET /v1/catalog/services` honesty overlay | Outbound sync queue + Partner Hub MAC |
| Partner registry + Command Center ops | TON GCEC jetton · GC14 stress · claims |
| Token non-merge (GCEC ≠ ODEI suite) | Local ODID mint before sync |

**Wire:** GoldCity `ODEI_GATEWAY_URL=http://localhost:5222` + `ODEI_GATEWAY_SYNC_ENABLED=1`. Sync **never** mints balances.

**Not claimed here:** rebuilding Mini App economy, merging GCEC into ODEI tickers, or a foundation LLM.
