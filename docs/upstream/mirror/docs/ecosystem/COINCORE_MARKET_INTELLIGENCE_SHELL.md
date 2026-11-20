> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/COINCORE_MARKET_INTELLIGENCE_SHELL.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/COINCORE_MARKET_INTELLIGENCE_SHELL.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# CoinCore — Market Intelligence Shell

**Updated:** 2026-07-28  
**Product:** CoinCore by ODEIAfrica (independent)  
**Vision:** A unified Digital Asset Intelligence Platform for Africa and the world.  
**Tagline:** *"One Platform. All Crypto Data. All Chains. All Intelligence."*  
**Port:** 5224  
**Hosts:** `coincore.localhost` · `coincore.odeiafrica.com`  
**Vision doc:** [`../CoinCore by ODEIAfrica/docs/VISION.md`](../CoinCore%20by%20ODEIAfrica/docs/VISION.md)

## URLs

| Surface | URL |
|---------|-----|
| Home | http://localhost:5224/ |
| App · Markets | http://localhost:5224/app/ |
| **15 modules hub** | http://localhost:5224/app/modules.html |
| Module catalog | http://localhost:5224/app/modules.json |
| Charts | http://localhost:5224/app/charts.html |
| Alerts | http://localhost:5224/app/alerts.html |
| API | http://localhost:5224/app/api.html |
| Watchlist | http://localhost:5224/app/watchlist.html |
| Seed data | http://localhost:5224/app/markets.json |
| **Live API** | http://localhost:5224/v1/markets |
| Health | http://localhost:5224/v1/health |
| Price | http://localhost:5224/v1/price/BTC%2FUSDT |
| Member dashboard | http://localhost:5224/dashboard/ |
| MAC | http://localhost:5224/admin/ |
| Login | http://localhost:5224/login.html |
| Gateway | http://coincore.localhost:8080/ |
| Production | https://coincore.odeiafrica.com/ |

## Honesty (mandatory)

**Phase 1: BTC/ETH `live_feed` via CoinGecko indexer · ODEI domain pairs `curated_internal`.**

| Surface | Label |
|---------|--------|
| Sticky banner | Every HTML page via `/honesty/honesty.js` |
| App markets table | Per-row `source` badge (`live_feed` / `curated_internal`) |
| `GET /v1/markets` | Authoritative live layer — OPMS consumes for `live_feed` flip |
| `markets.json` | Fallback seed + honesty object |
| Status | http://localhost:5224/status.html · `/status.json` |
| MAC | Honesty matrix module |
| Full doc | [`HONESTY.md`](./HONESTY.md) |

Do not label simulated intel as live CoinGecko-class feeds.

## Consumers

ODEI Tokens · DEX · Exchange · Launchpad · Membership entitlement `coincore.quotes.realtime`
## App surfaces (`/app/`)

| Surface | URL |
|---------|-----|
| Markets | http://localhost:5224/app/ |
| Trending | http://localhost:5224/app/trending.html |
| Charts | http://localhost:5224/app/charts.html |
| Portfolio | http://localhost:5224/app/portfolio.html |
| Watchlist | http://localhost:5224/app/watchlist.html |
| Coin profile | http://localhost:5224/app/coin.html?symbol=BTC/USDT |
| Alerts | http://localhost:5224/app/alerts.html |
| API | http://localhost:5224/app/api.html |
| Modules | http://localhost:5224/app/modules.html |
