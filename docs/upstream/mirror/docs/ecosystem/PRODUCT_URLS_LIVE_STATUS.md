> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/PRODUCT_URLS_LIVE_STATUS.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/PRODUCT_URLS_LIVE_STATUS.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Product URLs — Live Status

**Updated:** 2026-08-19  
**Honesty:** Local HTTP 200 ≠ production. Academy Curriculum Explorer beta is the first public wedge. Communications public messaging is live on `local_sim_public_preview` (not Twitter/Telegram scale). Marketplace Core is `local_sim` only.

**Command:** `npm run dev` (product shells)  
**Result:** Product shells include CoinCore (:5224), Membership (:5225), Studio website (:5226)

| Surface | URL | Status |
|---------|-----|--------|
| ODEI Academy | http://localhost:5201/ | 200 · Curriculum Explorer beta |
| Academy explorer | http://localhost:5201/app/ | Curriculum framework map |
| ODEI Cloud | http://localhost:5202/ | 200 |
| ODEI AI | http://localhost:5203/ | 200 |
| ODEI Chain | http://localhost:5204/ | 200 |
| ODEI Communications | http://localhost:5205/ | 200 · public messaging local_sim |
| Comms public channels | http://localhost:5205/app/public.html | publicMessagingClaims true (scoped) |
| Comms chat | http://localhost:5205/app/chat.html | Desk chrome · professional UI · Meet Video Chat (`data-meet=6`) · dock · **⚙ Manage** |
| Comms Video Chat doc | apps/communications/app/VIDEO-CHAT.md | Meet-inspired overlay `data-meet=6` |
| Comms Video Chat docs/URL catalog | docs/OMSG_VIDEO_CHAT_DOCS_AND_URLS.md | Current + previous docs & URLs |
| Comms calls status | http://localhost:5205/v1/calls/status | Signaling + ICE honesty |
| Comms ICE servers | http://localhost:5205/v1/calls/ice-servers | STUN + optional `ODEI_TURN_*` |
| OnlineBanking partner | http://localhost:5243/ | Desk chrome shell |
| OnlineBanking Laravel | http://localhost:5244/ | PHP 7.4 / Docker |
| LMS desk | http://localhost:5241/ | Desk chrome reference |
| Comms viral feed | http://localhost:5205/app/feed.html | For You timeline · `/v1/feed/*` |
| Comms VoiceClub | http://localhost:5205/app/voiceclub.html | Voice rooms · Sana assistant |
| Comms Twitter/imo parity | http://localhost:5205/app/platform-parity.html | Capability catalog |
| Comms WA/TG Business Tools | http://localhost:5205/app/parity.html | ≠ Video Chat |
| Academy ecosystem tour | http://localhost:5201/app/course.html?id=biz-ecosystem-tour | Guide-aligned course |
| Docs ecosystem tour | http://localhost:8765/docs/?doc=docs%2Fguides%2Fonboarding%2Fecosystem-tour.md | User guide reader |
| ODEI Core | http://localhost:5206/ | 200 |
| ODEI DeFi | http://localhost:5207/ | 200 |
| ODEI DEX | http://localhost:5208/ | 200 |
| ODEI Earn | http://localhost:5209/ | 200 |
| ODEI Exchange | http://localhost:5210/ | 200 |
| ODEI Foundation | http://localhost:5211/ | 200 |
| ODEI Launchpad | http://localhost:5212/ | 200 |
| ODEI Marketplace | http://localhost:5213/ | 200 |
| MKTPlace Core | http://localhost:5213/core/ | local_sim engines only |
| ODEI Merchant Platform | http://localhost:5214/ | 200 |
| ODEI Pay | http://localhost:5215/ | 200 |
| ODEI Store | http://localhost:5216/ | 200 |
| ODEI Switch | http://localhost:5217/ | 200 |
| ODEI Tokens | http://localhost:5218/ | 200 |
| ODEI Treasury | http://localhost:5219/ | 200 |
| ODEI Wallet | http://localhost:5220/ | 200 |
| ODEL Hub | http://localhost:5221/ | 200 |
| ODEI Identity | http://localhost:5222/ | 200 |
| DiCEI Africa | http://localhost:5223/ | 200 |
| **CoinCore by ODEIAfrica** | http://localhost:5224/ | independent · Phase 1 BTC/ETH live_feed |
| **ODEI Membership** | http://localhost:5225/ | browser_local · productionReady false |
| **ODEI Studio website** | http://localhost:5226/ | private preview |
| Multi-Ecosystem companion | http://localhost:5180/ | companion directory (score 34) |
| Civilizational map | http://localhost:5180/civilizational/ | architecture companion · icons + rings · not platform launch |
| Ecosystem map | http://localhost:5180/ecosystem-map.html | registry grouping |
| ODEL Manager website | http://localhost:5240/ | Website shell · Theme Store |
| ODEL Manager Student Portal | http://localhost:5240/portal/ · http://localhost:5240/portal/#/dashboard | Futuristic learner dashboard · Paper light readable · ◂/▸ sidebar |
| ODEL Manager app | http://localhost:5240/app/ | Hub campus console · Courses · ERMS · CATs |
| Command Center | http://localhost:5180/command/ | MAC hub · secrets slots |
| Docs portal | http://localhost:8765/ | companion |

## ODEI Exchange — Custodial shell (OEXC) surfaces

Canonical map: [`ODEI_EXCHANGE_CUSTODIAL_SHELL.md`](ODEI_EXCHANGE_CUSTODIAL_SHELL.md)  
IA leaf reference: [Atlantis Exchange Pro](https://atlantispro.io/) (features only; design unchanged)

| Surface | URL | Status |
|---------|-----|--------|
| Exchange App Home | http://localhost:5210/app/ | 200 |
| Markets | http://localhost:5210/app/markets.html | 200 |
| Spot | http://localhost:5210/app/spot.html | 200 |
| Margin | http://localhost:5210/app/margin.html | 200 |
| Wallets | http://localhost:5210/app/wallets.html | 200 |
| Orders | http://localhost:5210/app/orders.html | 200 |
| Staking | http://localhost:5210/app/staking.html | 200 |
| Lending | http://localhost:5210/app/lending.html | 200 |
| Bots | http://localhost:5210/app/bots.html | 200 |
| Fees | http://localhost:5210/app/fees.html | 200 |
| VIP | http://localhost:5210/app/vip.html | 200 |
| Referral | http://localhost:5210/app/referral.html | 200 |
| API | http://localhost:5210/app/api.html | 200 |
| Listings | http://localhost:5210/app/listings.html | 200 |
| Compliance | http://localhost:5210/app/compliance.html | 200 |
| Account | http://localhost:5210/app/account.html | 200 |
| Catalog | http://localhost:5210/app/catalog.json | 200 |
| Member dashboard | http://localhost:5210/dashboard/ | 200 |
| MAC | http://localhost:5210/admin/ | 200 |

## ODEI DEX — Trading shell (ODEX) surfaces

Canonical map: [`ODEI_DEX_TRADING_SHELL.md`](ODEI_DEX_TRADING_SHELL.md)

| Surface | URL | Status |
|---------|-----|--------|
| DEX App Home | http://localhost:5208/app/ | 200 |
| Swap | http://localhost:5208/app/swap.html | 200 |
| Pools | http://localhost:5208/app/pools.html | 200 |
| Trade | http://localhost:5208/app/trade.html | 200 |
| Orders | http://localhost:5208/app/orders.html | 200 |
| Analytics | http://localhost:5208/app/analytics.html | 200 |
| Account | http://localhost:5208/app/account.html | 200 |
| Markets catalog | http://localhost:5208/app/markets.json | 200 |
| Member dashboard | http://localhost:5208/dashboard/ | 200 |
| MAC | http://localhost:5208/admin/ | 200 |

## ODEI Wallet — Universal Account (OACC) surfaces

Canonical map: [`ODEI_WALLET_UNIVERSAL_ACCOUNT.md`](ODEI_WALLET_UNIVERSAL_ACCOUNT.md)

| Surface | URL | Status |
|---------|-----|--------|
| Wallet App Home | http://localhost:5220/app/ | 200 |
| Send | http://localhost:5220/app/send.html | 200 |
| Receive | http://localhost:5220/app/receive.html | 200 |
| Swap | http://localhost:5220/app/swap.html | 200 |
| Activity | http://localhost:5220/app/activity.html | 200 |
| NFTs | http://localhost:5220/app/nfts.html | 200 |
| Multi-Rail | http://localhost:5220/app/rails.html | 200 |
| Connect | http://localhost:5220/app/connect.html | 200 |
| Bridge | http://localhost:5220/app/bridge.html | 200 |
| Buy / On-ramp | http://localhost:5220/app/buy.html | 200 |
| Security | http://localhost:5220/app/security.html | 200 |
| Contacts | http://localhost:5220/app/contacts.html | 200 |
| Account | http://localhost:5220/app/account.html | 200 |
| Chains catalog | http://localhost:5220/app/chains.json | 200 |
| Member dashboard | http://localhost:5220/dashboard/ | 200 |
| MAC | http://localhost:5220/admin/ | 200 |
| Login | http://localhost:5220/login.html | 200 |

## CoinCore — Market intelligence shell

Canonical map: [`COINCORE_MARKET_INTELLIGENCE_SHELL.md`](COINCORE_MARKET_INTELLIGENCE_SHELL.md)

| Surface | URL |
|---------|-----|
| Home | http://localhost:5224/ |
| App | http://localhost:5224/app/ |
| Charts | http://localhost:5224/app/charts.html |
| Alerts | http://localhost:5224/app/alerts.html |
| API | http://localhost:5224/app/api.html |
| Watchlist | http://localhost:5224/app/watchlist.html |
| markets.json | http://localhost:5224/app/markets.json |
| **GET /v1/markets** | http://localhost:5224/v1/markets |
| **GET /v1/health** | http://localhost:5224/v1/health |
| Dashboard | http://localhost:5224/dashboard/ |
| MAC | http://localhost:5224/admin/ |

## ODEI Membership — Platform shell

Canonical map: [`ODEI_MEMBERSHIP_PLATFORM_SHELL.md`](ODEI_MEMBERSHIP_PLATFORM_SHELL.md)

| Surface | URL |
|---------|-----|
| Home | http://localhost:5225/ |
| App · Plans | http://localhost:5225/app/ |
| Entitlements | http://localhost:5225/app/entitlements.html |
| Billing | http://localhost:5225/app/billing.html |
| Organizations | http://localhost:5225/app/orgs.html |
| plans.json | http://localhost:5225/app/plans.json |
| **GET /v1/plans** | http://localhost:5225/v1/plans |
| **GET /v1/entitlements/me** | http://localhost:5225/v1/entitlements/me |
| Dashboard | http://localhost:5225/dashboard/ |
| MAC | http://localhost:5225/admin/ |

## Related surfaces

| Surface | URL | Notes |
|---------|-----|--------|
| ODEI Multi-Ecosystem (master) | http://localhost:5180/ | Directory of all products |
| Domain gateway | http://multi.localhost:8080/ | Host-header routing |
| OPMS MAC | http://127.0.0.1:5173/ | **Not** started by `npm run dev` — use `npm run dev:opms` or `npm run dev:all` |
| ODEI Studio web | http://localhost:3002/ | **Not** started by `npm run dev`; a 200 page still requires separate API `:4000` for builds. Root `dev:all` currently starts web only; use `npm run dev:studio-all` for both |
| ODEI Studio API | http://localhost:4000/health | Required by Studio web; unavailable in the 2026-07-30 probe. Local-only, no auth, open CORS |
| Docs library | http://localhost:8765/docs/ | `npm run dev:docs` |

## How to start / re-probe

```powershell
cd "E:\ODEI Multi Ecosystem"
npm run dev:all    # shells + Studio :3002 + OPMS :5173 + OPMS API :8002 + docs
# or shells only:
npm run dev
```

Full address map (ports + production hosts): [`PRODUCT_PORTS_AND_DOMAINS.md`](PRODUCT_PORTS_AND_DOMAINS.md)  
Audit checklist: [`ADDRESS_AUDIT.md`](ADDRESS_AUDIT.md)  
Run guide: [`HOW_TO_RUN_LOCAL.md`](HOW_TO_RUN_LOCAL.md)
