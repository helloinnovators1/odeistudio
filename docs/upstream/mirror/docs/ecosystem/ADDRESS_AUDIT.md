> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ADDRESS_AUDIT.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ADDRESS_AUDIT.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Address Audit — Independent Product URLs

**Audited:** 2026-07-24 (re-probed evening session)  
**Result:** All **21** listed product websites **200 OK**. See live table: [`PRODUCT_URLS_LIVE_STATUS.md`](PRODUCT_URLS_LIVE_STATUS.md).

## Checklist (Surface · URL · Status)

| Surface | URL | Status |
|---------|-----|--------|
| ODEI Academy | http://localhost:5201/ | 200 |
| ODEI Cloud | http://localhost:5202/ | 200 |
| ODEI AI | http://localhost:5203/ | 200 |
| ODEI Chain | http://localhost:5204/ | 200 |
| ODEI Communications | http://localhost:5205/ | 200 |
| ODEI Core | http://localhost:5206/ | 200 |
| ODEI DeFi | http://localhost:5207/ | 200 |
| ODEI DEX | http://localhost:5208/ | 200 |
| ODEI Earn | http://localhost:5209/ | 200 |
| ODEI Exchange | http://localhost:5210/ | 200 |
| ODEI Foundation | http://localhost:5211/ | 200 |
| ODEI Launchpad | http://localhost:5212/ | 200 |
| ODEI Marketplace | http://localhost:5213/ | 200 |
| ODEI Merchant Platform | http://localhost:5214/ | 200 |
| ODEI Pay | http://localhost:5215/ | 200 |
| ODEI Store | http://localhost:5216/ | 200 |
| ODEI Switch | http://localhost:5217/ | 200 |
| ODEI Tokens | http://localhost:5218/ | 200 |
| ODEI Treasury | http://localhost:5219/ | 200 |
| ODEI Wallet | http://localhost:5220/ | 200 |
| ODEL Hub | http://localhost:5221/ | 200 |

### Wallet Universal Account (also 200)

| Surface | URL |
|---------|-----|
| `/app/` | http://localhost:5220/app/ |
| `/dashboard/` | http://localhost:5220/dashboard/ |
| `/admin/` | http://localhost:5220/admin/ |

Full UA route table: [`PRODUCT_URLS_LIVE_STATUS.md`](PRODUCT_URLS_LIVE_STATUS.md) · [`ODEI_WALLET_UNIVERSAL_ACCOUNT.md`](ODEI_WALLET_UNIVERSAL_ACCOUNT.md)

## Also

| Surface | URL | Status / notes |
|---------|-----|----------------|
| **ODEI Multi-Ecosystem** | http://localhost:5180/ | Master directory |
| OPMS | http://localhost:5173/ | `npm run dev:opms` (IPv6/`localhost` on some Windows) |
| ODEI Studio | http://localhost:3002/ | `npm run dev:web` in Studio folder |
| Domain gateway | http://multi.localhost:8080/ | `npm run dev:gateway` |

## Interconnect

- Registry: `apps/ecosystem-registry.json`
- Master footer links: http://localhost:5180/ → every product URL above
- Shared rails: API `:8000`, Docs `:8765`, Core `:5206`, Identity `:5222`

## Verdict

**PASS** — every listed product has an independent address contract suitable for separate domain hosting; surfaces remain interconnected via the master site and registry.

## Independent domain hosting

**ENABLED** (2026-07-24): Host-header gateway + Caddy/DNS artifacts.

| Check | Result |
|-------|--------|
| `registry.hosting.enabled` | `true` |
| Gateway | http://localhost:8080/ |
| `pay.localhost:8080` → Pay | **200** (`pay.odeiafrica.com`) |
| `multi.localhost:8080` → Master | **200** |
| Docs | `docs/INDEPENDENT_DOMAIN_HOSTING.md` |

Still requires **your DNS + TLS** at the registrar/edge for public `*.odeiafrica.com`.
