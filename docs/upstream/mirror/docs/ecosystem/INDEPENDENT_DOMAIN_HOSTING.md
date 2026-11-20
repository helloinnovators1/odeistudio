> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/INDEPENDENT_DOMAIN_HOSTING.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/INDEPENDENT_DOMAIN_HOSTING.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Independent Domain Hosting — ENABLED

**Updated:** 2026-08-03  
**Status:** **ENABLED** (architecture + local Host gateway + Caddy/DNS artifacts)

> **Namecheap / independent product hosting status (audited 2026-08-03):**  
> Kit readiness ≈ **48%**; go-live on Namecheap ≈ **18%**. Local ports ≠ production.  
> Full product table + cPanel vs VPS path:  
> [`ops/deploy/ODEI_NAMECHEAP_AND_INDEPENDENT_HOSTING_STATUS.md`](ops/deploy/ODEI_NAMECHEAP_AND_INDEPENDENT_HOSTING_STATUS.md) ·  
> [`ops/deploy/NAMECHEAP_PATH.md`](ops/deploy/NAMECHEAP_PATH.md)

> **Environment boundary (audited 2026-07-30):** “Enabled” here means the
> routing/DNS/deployment **kit** exists. It does not mean an independent,
> production-secure runtime is operating. The current edge script launches the
> same static shell server used locally, does not deploy Studio/OPMS workspaces,
> and has no trusted Identity/RBAC or separate production data/secrets. See
> [`ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md`](ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md).

## Honest capability matrix

| Layer | Status | What it means |
|-------|--------|----------------|
| Independent ports | **Enabled** | Each product has its own `:PORT` |
| Production hostnames in registry | **Enabled** | e.g. `pay.odeiafrica.com` |
| Local domain-style URLs | **Enabled** | `http://pay.localhost:8080/` via gateway |
| Host-header reverse proxy | **Enabled** | `hosting/gateway.mjs` + `hosting/Caddyfile` |
| DNS at real registrars | **Kit ready** | Local script + GitHub Action `dns-activate.yml` (needs your keys) |
| Public TLS certificates | **Pending edge** | Caddy/Cloudflare once DNS points here |
| Per-product CI/CD deploy | **GitHub kit ready** | `deploy-edge.yml` + `hosting/deploy_edge.sh` (needs SSH secrets) |
| Edge IP / API key guide | **Saved** | `docs/EDGE_IP_AND_API_KEYS.md` |
| GitHub autonomous hosting | **Enabled** | `docs/GITHUB_HOSTING.md` |

## Formula (now operational)

```
Browser  →  https://{prod_host}     (production DNS + TLS)
     or  →  http://{local_host}:8080/   (local domain simulation)
         →  Gateway (Host header)
         →  127.0.0.1:{port}  (independent product process)
```

Products stay **interconnected** via:
- Master site `multi.odeiafrica.com` / `multi.localhost`
- Shared API `api.odeiafrica.com`
- Identity SSO cookie domain `.odeiafrica.com`
- Registry `apps/ecosystem-registry.json`

## Start local independent-domain mode

```powershell
# 1) Product shells + master
.\START_PRODUCT_APPS.bat

# 2) OPMS / Studio / API / Docs (if needed)
.\START_LOCAL_SERVICES.bat

# 3) Domain gateway
.\START_DOMAIN_GATEWAY.bat
```

Then open:

- http://multi.localhost:8080/
- http://pay.localhost:8080/
- http://core.localhost:8080/
- http://id.localhost:8080/

## Production cutover

1. Get edge IP + registrar API keys → `docs/EDGE_IP_AND_API_KEYS.md`.
2. Push repo to GitHub; add secrets from `hosting/github-secrets.example` → `docs/GITHUB_HOSTING.md`.
3. Run **ODEI Deploy Edge**, then **ODEI DNS Activate** (Namecheap / GoDaddy / IONOS / Cloudflare).
4. Or manually: create DNS from `hosting/dns-records.csv`; run Caddy with `hosting/Caddyfile`.
5. Set Identity cookie domain to `.odeiafrica.com`.

## Host map

| Product | Local host | Production host | Local domain URL | Production URL |
|---------|------------|-----------------|------------------|----------------|
| OPMS (MAC) | `opms.localhost` | `mac.odeiafrica.com` | `http://opms.localhost:8080/` | `https://mac.odeiafrica.com/` |
| ODEI Studio | `studio.localhost` | `studio.odeiafrica.com` | `http://studio.localhost:8080/` | `https://studio.odeiafrica.com/` |
| Docs Library | `docs.localhost` | `docs.odeiafrica.com` | `http://docs.localhost:8080/` | `https://docs.odeiafrica.com/` |
| OPMS API | `api.localhost` | `api.odeiafrica.com` | `http://api.localhost:8080/` | `https://api.odeiafrica.com/` |
| ODEI Multi-Ecosystem | `multi.localhost` | `multi.odeiafrica.com` | `http://multi.localhost:8080/` | `https://multi.odeiafrica.com/` |
| ODEI Academy | `academy.localhost` | `academy.odeiafrica.com` | `http://academy.localhost:8080/` | `https://academy.odeiafrica.com/` |
| ODEI Cloud | `cloud.localhost` | `cloud.odeiafrica.com` | `http://cloud.localhost:8080/` | `https://cloud.odeiafrica.com/` |
| ODEI AI | `ai.localhost` | `ai.odeiafrica.com` | `http://ai.localhost:8080/` | `https://ai.odeiafrica.com/` |
| ODEI Chain OS | `chain.localhost` | `chain.odeiafrica.com` | `http://chain.localhost:8080/` | `https://chain.odeiafrica.com/` |
| ODEI Communications | `comms.localhost` | `comms.odeiafrica.com` | `http://comms.localhost:8080/` | `https://comms.odeiafrica.com/` |
| ODEI Core | `core.localhost` | `core.odeiafrica.com` | `http://core.localhost:8080/` | `https://core.odeiafrica.com/` |
| ODEI DeFi | `defi.localhost` | `defi.odeiafrica.com` | `http://defi.localhost:8080/` | `https://defi.odeiafrica.com/` |
| ODEI DEX | `dex.localhost` | `dex.odeiafrica.com` | `http://dex.localhost:8080/` | `https://dex.odeiafrica.com/` |
| ODEI Earn | `earn.localhost` | `earn.odeiafrica.com` | `http://earn.localhost:8080/` | `https://earn.odeiafrica.com/` |
| ODEI Exchange | `exchange.localhost` | `exchange.odeiafrica.com` | `http://exchange.localhost:8080/` | `https://exchange.odeiafrica.com/` |
| ODEI Foundation | `foundation.localhost` | `foundation.odeiafrica.com` | `http://foundation.localhost:8080/` | `https://foundation.odeiafrica.com/` |
| ODEI Launchpad | `launchpad.localhost` | `launchpad.odeiafrica.com` | `http://launchpad.localhost:8080/` | `https://launchpad.odeiafrica.com/` |
| ODEI Marketplace | `marketplace.localhost` | `marketplace.odeiafrica.com` | `http://marketplace.localhost:8080/` | `https://marketplace.odeiafrica.com/` |
| ODEI Merchant Platform | `merchant.localhost` | `merchant.odeiafrica.com` | `http://merchant.localhost:8080/` | `https://merchant.odeiafrica.com/` |
| ODEI Pay | `pay.localhost` | `pay.odeiafrica.com` | `http://pay.localhost:8080/` | `https://pay.odeiafrica.com/` |
| ODEI Store | `store.localhost` | `store.odeiafrica.com` | `http://store.localhost:8080/` | `https://store.odeiafrica.com/` |
| ODEI Switch | `switch.localhost` | `switch.odeiafrica.com` | `http://switch.localhost:8080/` | `https://switch.odeiafrica.com/` |
| ODEI Tokens | `tokens.localhost` | `tokens.odeiafrica.com` | `http://tokens.localhost:8080/` | `https://tokens.odeiafrica.com/` |
| ODEI Treasury | `treasury.localhost` | `treasury.odeiafrica.com` | `http://treasury.localhost:8080/` | `https://treasury.odeiafrica.com/` |
| ODEI Wallet | `wallet.localhost` | `wallet.odeiafrica.com` | `http://wallet.localhost:8080/` | `https://wallet.odeiafrica.com/` |
| ODEL Hub | `odel.localhost` | `odel.odeiafrica.com` | `http://odel.localhost:8080/` | `https://odel.odeiafrica.com/` |
| ODEI Identity | `id.localhost` | `id.odeiafrica.com` | `http://id.localhost:8080/` | `https://id.odeiafrica.com/` |
| DiCEI Africa | `dicei.localhost` | `dicei.odeiafrica.com` | `http://dicei.localhost:8080/` | `https://dicei.odeiafrica.com/` |
| CoinCore | `coincore.localhost` | `coincore.odeiafrica.com` | `http://coincore.localhost:8080/` | `https://coincore.odeiafrica.com/` |
| Membership | `membership.localhost` | `membership.odeiafrica.com` | `http://membership.localhost:8080/` | `https://membership.odeiafrica.com/` |
| OCS | `ocs.localhost` | `ocs.odeiafrica.com` | `http://ocs.localhost:8080/` | `https://ocs.odeiafrica.com/` |

## Regenerator

`python _enable_independent_domain_hosting.py`

## Full product websites

Each product on the host map (Academy → ODEL Hub) has a **unique multi-page website** under `apps/<id>/` (Website IA, no shared shell).  
Regenerate: `python _build_full_product_websites.py` · Verify: `python hosting/verify_product_websites.py` · See `docs/PRODUCT_WEBSITE_AUDIT.md`.
