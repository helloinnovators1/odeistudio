> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/BUILD_ORDER_ROADMAP.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/BUILD_ORDER_ROADMAP.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Multi Ecosystem — Exhaustive Build-Order Roadmap (No Omission)

**Document type:** Deepest holistic autonomous sequencing  
**Revision:** 2026-07-24 (v2 — includes DiCEI **20 Infrastructure Domains** + full suite tokens)  
**Authorities:** Africa Infrastructure Development Roadmap · MC-OS layers · OPMS MVP honesty · Studio phases · DiCEI Super-Layer doc · [`TOKEN_DOMAIN_MAP.md`](TOKEN_DOMAIN_MAP.md) · product `docs/` holistics · docs library  
**Hub:** [`index.html`](index.html)

---

## 0. One-page spine

```
P0   Harden OPMS authz
     → ODEI Core → ODEI Identity (ODID) → ODEI Chain OS → ODEI Cloud → ODEI Communications
P1   ODEI Wallet → ODEI Switch → ODEI Pay (OPAY) → ODUSD → ODEI Tokens → ODEI Academy
P1.5 ODEI Multi-Ecosystem Membership (plans · billing · entitlements)
     | ODEL Hub = MERGE into Academy (do not build)
P2   CoinCore → ODEI DEX (ODEX) → ODEI Treasury → ODEI Launchpad extract (OLCH capital)
     → ODEI Exchange (design / paper only)
P3   ODEI DeFi → ODEI Earn → ODEI AI (ODAI) → ODEI Merchant Platform
P4   ODEI Store → ODEI Marketplace (commerce) → DiCEI Africa Phase-1 rails
     → DiCEI Wave A Verses (CRT, COMX, EDU, DEV) + DICE treasury skeleton
P4b  DiCEI Wave B Verses (MED, MUS, POD, FLM, DSG, FRL, COM, EVT)
P4c  DiCEI Wave C Verses (AIC, NGO, FTH, GAM, SPT, TOUR, DIA)
P4d  DiCEI InfrastructureVerse (INF) + full DICE governance / Senate
P5+  OBNK · OXBT · OBIZ · OGOV · OWLT · OLCH ecosystem · mature ODAI models
∥    ODEI Studio · ODEI Foundation · ODEIAfrica umbrella · Docs library · OPMS live platform
```

**Non-negotiable:** Money rails (Identity/Wallet/Switch/Pay/ODUSD) before DiCEI Verses. Do not launch all 20 Verse token economies on day one.

---

## 1. Principles (complete)

| # | Principle | Implication |
|---|-----------|-------------|
| 1 | Identity-first (MC-OS) | Everything begins with ODID / OPMS ID extract |
| 2 | Core is not an app | Shared platform before product UIs |
| 3 | Africa Phase 1 = Chain + ODID + OPAY + ODUSD | P0–P1 before commerce/DiCEI |
| 4 | Extract > clone | Peel OPMS; do not fork OPMS per product |
| 5 | Honesty labels | Sim CoinCore/DEX/AI until live |
| 6 | Regulated last | Exchange custody after Foundation/Legal |
| 7 | One LXP | Merge ODEL Hub → Academy |
| 8 | Two marketplaces | Extension Marketplace ≠ Commerce Marketplace |
| 9 | Two parallel 20-domain suites | ODEIAfrica **20 Infrastructure Domains** + DiCEI **20 Verses** — neither omitted |
| 10 | Domain/Verse = full stack unit | Users + ecosystem + treasury + council + token |
| 11 | Studio accelerates | Never blocks Wallet/Pay |
| 12 | Docs are operational | Word = narrative; MD + hub = engineering index |

---

## 2. Pre-build decisions

| Decision | Recommendation |
|----------|----------------|
| ODEL Hub | **Merge → Academy** |
| Empty `ODEI Marketplace` | Rename **Commerce Marketplace** |
| ODEI Core | Use `ODEI Core/` (exists); keep Core.docx there |
| OCRE vs DICE | OCRE = ODEIAfrica bridge; **DICE + 20 Verses** = authoritative DiCEI hierarchy |
| Launchpad | Extract capital Launchpad P1–P2; OLCH ecosystem P5–P7 |
| OPMS security | **P0 before extract/share** |
| DiCEI Verse order | Wave A → B → C → INF (below) — not parallel 20 launches |
| Studio fork | Extension-first until Code-OSS clone reliable |

---

## 3. Master sequenced catalog — every folder & domain

### Legend
**Mode:** Harden · Extract · Promote · Expand · Greenfield · Merge · Overlay · Parallel · Umbrella · Deferred  
**Pri:** Critical · High · Medium · Later · Cancel

### 3.1 Platform & live code

| ID | Item | Phase | Mode | Pri | Depends on | First shippable slice |
|----|------|-------|------|-----|------------|------------------------|
| 0a | OPMS authz lockdown | P0 | Harden | Critical | — | Authz on mutating APIs; lock `/auth/demo`, `/env*`; MAC gated |
| 0b | **ODEI Core** | P0 | Greenfield | Critical | Cloud soft | Shared SDK ≥2 consumers |
| 0c | **ODEI Identity** (ODID) | P0–P1 | Extract OPMS ID | Critical | Core | Versioned Identity API |
| 0d | **ODEI Chain OS** | P0–P1 | Promote | Critical | Cloud, validators | Single-org fleet maturity |
| 0e | **ODEI Cloud** | P0 | Thin GF | High | — | Compose + secrets (no MAC `.env` in prod) |
| 0f | **ODEI Communications** | P0–P1 | Thin GF | High | Core | One real notify channel |
| 0g | **ODEIAfrica** | ∥ | Umbrella | Continuous | — | Suite #2 roadmap authority + brand |
| 0h | **ODEI Foundation** | ∥ | Governance | Parallel | Legal | Charter before Exchange custody |
| 0i | **Docs library** (`docs/`) | ∥ | Ops | High | — | Hub + per-folder `docs/` current |
| 0j | **OPMS** (live platform) | Ongoing | Live + extract source | Critical | → consumes Core later | Capital OS; peel modules |
| 0k | **ODEI Studio** | ∥ | Parallel MVP | Enabler | Cloud/AI optional | LLM Phase 2; scaffold stubs |

### 3.2 Money & learning rails

| ID | Item | Phase | Mode | Pri | Depends on | First shippable slice |
|----|------|-------|------|-----|------------|------------------------|
| 1a | **ODEI Wallet** | P1 | **UA shell live** (`apps/wallet/app/` + `/dashboard/`) + OPMS seeds | Critical | Identity, Chain OS, Core | Universal account; TonConnect sim; honest labels — see [`ODEI_WALLET_UNIVERSAL_ACCOUNT.md`](ODEI_WALLET_UNIVERSAL_ACCOUNT.md) |
| 1b | **ODEI Switch** | P1 | GF | Critical | Provider adapters | Failover ≥2 providers |
| 1c | **ODEI Pay** (OPAY) | P1 | Expand OPMS | Critical | Identity, Wallet, Switch, ODUSD | QR + remittance + payroll stub |
| 1d | **ODUSD / ODUSD** | P1 | Engine | Critical | Treasury policy, Chain | Testnet + reserve attestation UI |
| 1e | **ODEI Tokens** | P1 | Promote | High | Token Engine | Registry app; sim market labels |
| 1f | **ODEI Academy** | P1–P2 | Promote | High | Identity, Pay, Wallet | Deployable LXP |
| 1x | **ODEL Hub** | — | **Merge** | Cancel | — | → Academy Learning Hub |

### 3.3 Markets & capital

| ID | Item | Phase | Mode | Pri | Depends on | First shippable slice |
|----|------|-------|------|-----|------------|------------------------|
| 1m | **ODEI Membership** | P1.5 | GF platform | High | Identity, Pay | Catalog + entitlements + one billing rail |
| 2a | **CoinCore** | P2 | GF indexer + **product shell live :5224** | High | Tokens, Membership | Live price/volume API |
| 2b | **ODEI DEX** (ODEX) | P2 | **Trading shell live** (`apps/dex/app/`) + OPMS sim | High | Wallet, Tokens | Sim swap shell — see [`ODEI_DEX_TRADING_SHELL.md`](ODEI_DEX_TRADING_SHELL.md); live pairs later |
| 2c | **ODEI Treasury** | P2 | Promote | High | Pay, ODUSD | Vault types (MC-OS L6) |
| 2d | **ODEI Launchpad** (capital / OLCH) | P1–P2 | Extract OPMS | High | Identity, Tokens, Pay | Campaigns + factory as product |
| 2e | **ODEI Exchange** | P2–P3 | **Custodial shell live** (`apps/exchange/app/`) paper | Careful | Identity, Legal, Treasury | Atlantis Pro IA leaf only; design unchanged — [`ODEI_EXCHANGE_CUSTODIAL_SHELL.md`](ODEI_EXCHANGE_CUSTODIAL_SHELL.md); live custody later |

### 3.4 Yield, AI, merchants

| ID | Item | Phase | Mode | Pri | Depends on | First shippable slice |
|----|------|-------|------|-----|------------|------------------------|
| 3a | **ODEI DeFi** | P3 | GF | Medium | Wallet, DEX, ODUSD | One testnet strategy |
| 3b | **ODEI Earn** | P3 | GF | Medium | Wallet, Tokens, Pay | Rewards ↔ Academy/referrals |
| 3c | **ODEI AI** (ODAI) | P3 | Promote + router | High | Core, data | Shared LLM client |
| 3d | **ODEI Merchant Platform** | P3–P4 | GF | Medium | Pay, Switch, Identity | POS SDK → Pay |

### 3.5 Commerce shell (before Verses)

| ID | Item | Phase | Mode | Pri | Depends on | First shippable slice |
|----|------|-------|------|-----|------------|------------------------|
| 4a | **ODEI Store** | P4 | GF | Medium | Pay, Merchant, Identity | Multi-tenant checkout |
| 4b | **ODEI Marketplace** (commerce) | P4 | GF | Medium | Store/Merchant, Pay | Listings + fee split |
| 4c | **DiCEI Africa** platform shell | P4 | Overlay | High | Pay, Wallet, Identity, ODUSD | Profiles + tips + MoMo/stable |

### 3.6 DiCEIAfrica — 5 Super-Layers (architecture track)

| Layer | Name | Engineering meaning | Phase |
|------:|------|---------------------|-------|
| L1 | Human | Creator profiles, classes, reputation | P4 |
| L2 | Economic | Fees, tips, memberships, Verse treasuries | P4–P4d |
| L3 | Infrastructure | Wallets, Pay, AI Studio, APIs (reuse ODEI rails) | P1 then P4 |
| L4 | Governance | Councils → Senate → Treasury Council → DICE DAO | P4d |
| L5 | Civilization | Continental scale, 50-year infra narrative | P5+ metrics |

### 3.7 DiCEIAfrica — THE 20 INFRASTRUCTURE DOMAINS (no omission)

Each Verse = user class + ecosystem + treasury + governance council + **token economy**.  
**Master reserve:** **DICE**. Bridge from ODEIAfrica suite: **OCRE** (do not substitute for the 20).

#### Wave A — first verticals (after Pay/Wallet) · Phase P4 / P4a

| # | Domain | Token | Pri | Why this wave | First slice |
|--:|--------|-------|-----|---------------|-------------|
| 1 | **CreatorVerse** | **CRT** | Critical | Core influencer/streamer tip economy | Profiles, tips, memberships |
| 14 | **CommerceVerse** | **COMX** | Critical | Merchants / digital sellers; Store bridge | Digital product checkout |
| 2 | **EducationVerse** | **EDU** | High | Aligns ODEI Academy grants/certs | Course listing + rewards |
| 9 | **DeveloperVerse** | **DEV** | High | Aligns Studio / builders | Builder marketplace stub |

#### Wave B — media & services · Phase P4b

| # | Domain | Token | Pri | First slice |
|--:|--------|-------|-----|-------------|
| 3 | **MediaVerse** | **MED** | Medium | Subscriptions for publishers |
| 4 | **MusicVerse** | **MUS** | Medium | Royalty split MVP |
| 5 | **PodcastVerse** | **POD** | Medium | Audio tip/subscribe |
| 6 | **FilmVerse** | **FLM** | Medium | Video drop + fan pass |
| 7 | **DesignVerse** | **DSG** | Medium | Design gig listing |
| 8 | **FreelanceVerse** | **FRL** | Medium | Freelance escrow via Pay |
| 11 | **CommunityVerse** | **COM** | Medium | Community dues/membership |
| 15 | **EventVerse** | **EVT** | Medium | Ticket checkout |

#### Wave C — specialized & diaspora · Phase P4c

| # | Domain | Token | Pri | Depends / note | First slice |
|--:|--------|-------|-----|----------------|-------------|
| 10 | **AI CreatorVerse** | **AIC** | High | After ODEI AI / Studio LLM | Prompt marketplace |
| 12 | **NGOVerse** | **NGO** | Later | Compliance-sensitive | Donation rail |
| 13 | **FaithVerse** | **FTH** | Later | Giving UX | Tithe/offering rail |
| 16 | **GamingVerse** | **GAM** | Medium | Esports creators | Tip + tournament fee |
| 17 | **SportsVerse** | **SPT** | Medium | Sports creators | Fan pass |
| 18 | **TourismVerse** | **TOUR** | Later | Local partners | Experience listing |
| 19 | **DiasporaVerse** | **DIA** | High | Needs Pay corridors | Cross-border tip/remit |

#### Wave D — meta-infrastructure & master token · Phase P4d

| # | Domain / asset | Token | Pri | First slice |
|--:|----------------|-------|-----|-------------|
| 20 | **InfrastructureVerse** | **INF** | High | Operator tooling, Verse registry, plugin APIs |
| — | **DICE** master reserve | **DICE** | Critical | Governance stake, treasury, ecosystem funding |
| — | Creator Councils (per Verse) | — | High | Elect reps per live Verse |
| — | Infrastructure Senate | — | High | 20-domain representation |
| — | Treasury Council | — | High | Grants / infra spend |
| — | DICE Governance DAO | — | Medium | Upgrades, allocations, token policy |

### 3.8 ODEIAfrica suite domain tokens (engineering phase)

| Token | Domain | Phase |
|-------|--------|-------|
| ODEI | Ecosystem master | Continuous |
| ODID | Identity | P0 |
| OPAY | Payments | P1 |
| ODUSD/ODUSD | Stablecoin | P1 |
| ODEX | DEX | P2 |
| OLCH | Launchpad | P1–P2 extract / P5+ ecosystem |
| ODAI | AI | P3 / P6+ models |
| OCRE | Creator bridge → DiCEI | P4+ (with DICE/Verses) |
| OBNK | Banking | P5+ |
| OXBT | Settlement / XB | P5+ |
| OBIZ | Business | P5+ |
| OGOV | Gov DPI | P5–P6 |
| OWLT | Wealth | P6 |

### 3.9 P5+ suite expansions (deferred products)

| ID | Item | Phase | Depends on |
|----|------|-------|------------|
| 5a | OBNK banking rails | P5+ | Exchange design, Legal |
| 5b | OXBT settlement product | P5+ | Switch, Treasury settlement OS |
| 5c | OBIZ business services | P5+ | Merchant, Identity KYB |
| 5d | OGOV gov DPI modules | P5–P6 | Identity, Pay, Legal |
| 5e | OWLT wealth | P6 | Earn, DeFi, Exchange |
| 5f | OLCH Launchpad **ecosystem** | P6–P7 | Capital Launchpad extract done |
| 5g | Mature ODAI / foundation models | P6+ | Model Router + data flywheel |
| 5h | DiCEI Phases 3–5 (creator banking, continental rails) | P5–P10 | DiCEI Word roadmap years 3–10 |

---

## 4. Dependency DAG (hard edges)

```
Cloud → Core → Identity → Wallet → DEX → DeFi
                 │            │
                 ├────────────┼─→ Pay ← Switch
                 │            │     │
                 │            │     ├─→ Merchant → Store → Commerce Marketplace
                 │            │     ├─→ Academy (← Hub merge)
                 │            │     ├─→ Launchpad
                 │            │     └─→ DiCEI shell → Wave A (CRT, COMX, EDU, DEV)
                 │            │              → Wave B → Wave C → INF + DICE DAO
                 │            └─→ Earn
                 ├─→ Communications
                 └─→ AI → Studio / Copilot / AIC Verse

Chain OS → Tokens → CoinCore → DEX
        └→ ODUSD → Pay / Treasury / DiCEI stables

Treasury ← Pay · ODUSD · DICE treasury (later)
Exchange ← Identity · Treasury · Legal · Tokens
```

---

## 5. Phase exit criteria

| Phase | Exit (done when) |
|-------|------------------|
| **P0** | OPMS not casually abuseable on LAN; Core SDK used twice; Identity API live; Chain OS demo-honest; secrets path; one notify channel |
| **P1** | Identity → Wallet → honest Pay intent → Tokens → Academy enroll |
| **P2** | CoinCore feeds Tokens; DEX testnet swap; Treasury vaults; Launchpad extracted; Exchange paper-only |
| **P3** | One DeFi strategy; Earn ledger; Model Router; Merchant SDK → Pay |
| **P4** | Store checkout; Commerce Marketplace; DiCEI profiles+tips on MoMo/stable |
| **P4a** | CRT + COMX live verticals (min); EDU/DEV stubs OK |
| **P4b–c** | Remaining Verses per wave without breaking Pay |
| **P4d** | INF registry + DICE treasury/governance skeleton |
| **P5+** | Suite domains + DiCEI creator banking / continental phases per Word roadmap |

---

## 6. OPMS extract map

| OPMS surface | Becomes | Keep in OPMS |
|--------------|---------|--------------|
| `/id` | ODEI Identity | Capital eligibility |
| `/tokens` + Token Engine | ODEI Tokens | Sale token create |
| `/academy` | ODEI Academy | MAC learning cards |
| Payment Engine + TON Pay | ODEI Pay | Sale settle |
| Campaigns + Token Factory | Capital Launchpad | Issuer console |
| Treasury engine | ODEI Treasury seed | Per-sale views |
| `odei_chain` + Chain OS | Chain OS product | Explorer demos |
| Extension Marketplace | Stay PaaE | ≠ Commerce Marketplace |
| Copilot / Mentor / AI scan | ODEI AI seeds | Until Model Router |

---

## 7. DiCEI phased execution (from Super-Layer Word) mapped to ODEI phases

| DiCEI Word phase | Years | Build | Maps to |
|------------------|-------|-------|---------|
| Phase 1 Monetization | 1–2 | Profiles, tips, MoMo, stables, wallets, AI Studio | ODEI P1 rails + DiCEI P4 shell + Wave A |
| Phase 2 Commerce | 2–3 | Memberships, digital products, communities, subscriptions | Store/Marketplace + Waves A–B |
| Phase 3 Creator Finance | 3–5 | Accounts, treasury, lending, creator banking | P4d DICE treasury + P5+ banking |
| Phase 4 Network | 5–7 | APIs, embedded finance, third parties | INF + DeveloperVerse + Studio |
| Phase 5 Pan-African | 7–10 | Continental rails, identity, reputation, banking net | Civilization layer + ODID/Pay scale |

---

## 8. Anti-patterns

1. All 20 Verse tokens at once before Pay.  
2. Treating OCRE as sufficient DiCEI coverage (omits 20 domains).  
3. DiCEI/Store before Switch/Pay.  
4. Exchange custody before Foundation/Legal.  
5. Second LXP (ODEL Hub).  
6. Fake CoinCore/DEX “live” quotes.  
7. Studio marketed as LLM before Model Router.  
8. Extracting OPMS modules while APIs stay open.  
9. Confusing Extension vs Commerce Marketplace.  
10. ODUSD/DICE reserve claims without attestation.  
11. Waiting for suite Phase 7 to extract capital Launchpad.  
12. Re-burying Core under CoinCore.
13. Treating ODEI as only 12 flat tickers — omit Extended Domains (OACC…OMSG) or the Domain unit model.
14. Confusing ODEI Domains with DiCEI Verses (different masters: ODEI vs DICE).

---

## 9. ODEIAfrica 20 Infrastructure Domains (independent suite)

Deep doc: [`ODEI_INFRASTRUCTURE_DOMAINS.md`](ODEI_INFRASTRUCTURE_DOMAINS.md)

| Tier | Domains |
|------|---------|
| Master | **ODEI** |
| A Official 12 | ODID OPAY ODEX OBNK ODUSD OCRE ODAI OLCH OBIZ OGOV OWLT OXBT |
| B Extended 8 | OACC OSWT OEXC OTRS OACD OCHN OCLD OMSG |

Engineering waves for extended: E0 OCHN/OCLD/OMSG → E1 OACC/OSWT → E2 OTRS/OEXC → E3 OACD.

---

## 10. 90-day slice

| Window | Focus |
|--------|-------|
| Days 1–30 | OPMS authz; Core skeleton; Identity extract RFC; Hub/Marketplace naming; Studio LLM spike; docs hub |
| Days 31–60 | Identity v0; Wallet shell (OACC); Switch interface (OSWT); Pay multi-rail; Tokens promote; Chain OS (OCHN) maturity |
| Days 61–90 | ODUSD testnet UI; Academy (OACD) promote; Launchpad extract RFC; CoinCore 1-chain spike; one notify channel (OMSG) |

**Bar:** Identity + Wallet + honest Pay + Tokens + Academy — no `admin123` on shared host.  
*(DiCEI Verses start after this bar, not instead of it.)*

---

## 11. Coverage checklist (assert no omission)

### Folders / products
| Item | Sequenced? |
|------|------------|
| ODEI Core, Identity, Chain OS, Cloud, Communications | Yes P0 |
| ODEIAfrica, Foundation | Yes ∥ |
| Wallet, Switch, Pay, Tokens, Academy | Yes P1 |
| ODEL Hub | Yes Merge/Cancel |
| CoinCore, DEX, Treasury, Launchpad, Exchange | Yes P2 |
| DeFi, Earn, AI, Merchant | Yes P3 |
| Store, Marketplace, DiCEI Africa | Yes P4 |
| OPMS, Studio, Docs library | Yes ongoing/∥ |
| OBNK, OXBT, OBIZ, OGOV, OWLT, OLCH eco, mature ODAI | Yes P5+ |

### ODEIAfrica 20 Infrastructure Domains (+ ODEI master)
ODID · OPAY · ODEX · OBNK · ODUSD · OCRE · ODAI · OLCH · OBIZ · OGOV · OWLT · OXBT · OACC · OSWT · OEXC · OTRS · OACD · OCHN · OCLD · OMSG — **Yes §9 + ODEI_INFRASTRUCTURE_DOMAINS.md**

### DiCEI master + 20 Verses (21)
DICE · CRT · EDU · MED · MUS · POD · FLM · DSG · FRL · DEV · AIC · COM · NGO · FTH · COMX · EVT · GAM · SPT · TOUR · DIA · INF — **Yes §3.7 Waves A–D**

### DiCEI super-layers (5)
Human · Economic · Infrastructure · Governance · Civilization — **Yes §3.6**

### ODEI super-layers (5)
Trust · Money Movement · Markets & Capital · Intelligence & Enterprise · Civilization — **Yes ODEI_INFRASTRUCTURE_DOMAINS.md**


---

## 11. Related artifacts

| Artifact | Path |
|----------|------|
| Token domain map (canonical) | [`TOKEN_DOMAIN_MAP.md`](TOKEN_DOMAIN_MAP.md) |
| DiCEI Super-Layer extract | `../DiCEI Africa/docs/_dicei_super_layer_extract.txt` |
| Master index | [`../README.md`](../README.md) |
| Per-product holistics | `../<Product>/docs/ODEI_HOLISTIC_DOCUMENTATION.md` |
| Interactive library | [`index.html`](index.html) |
| Rescan note | [`ECOSYSTEM_RESCAN.md`](ECOSYSTEM_RESCAN.md) |

---

*End of exhaustive build-order roadmap v2 — no product, suite token, or DiCEI Infrastructure Domain omitted.*
