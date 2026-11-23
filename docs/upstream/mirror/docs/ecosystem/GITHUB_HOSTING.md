> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/GITHUB_HOSTING.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/GITHUB_HOSTING.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# GitHub → Registrars → Edge hosting for ODEI Multi-Ecosystem

**Updated:** 2026-08-18  
**Status:** Kit enabled (CI dry-run verified). Live DNS/deploy needs your GitHub secrets + VPS. GitHub remote is live: https://github.com/infoedutechos/ODEI-Multi-Ecosystem (`main`, first secrets-safe commit `3b4f8ae`). Vercel project env still needs a dashboard paste — [GITHUB_MONGODB_VERCEL.md](./GITHUB_MONGODB_VERCEL.md).

## What this enables

| Capability | How |
|------------|-----|
| Host product addresses independently | `apps/ecosystem-registry.json` + gateway Host routing |
| Activate DNS at Namecheap / GoDaddy / IONOS / Cloudflare | `.github/workflows/dns-activate.yml` + `hosting/activate_dns.py` |
| Deploy & run on a public edge | `.github/workflows/deploy-edge.yml` + `hosting/deploy_edge.sh` |
| Continuous verification | `ci-hosting-kit.yml` (artifacts) · `dns-verify-public.yml` (resolution) |
| Local simulation (no GitHub) | `START_PRODUCT_APPS.bat` + `START_DOMAIN_GATEWAY.bat` |

```
GitHub repo
  ├─ push / workflow_dispatch
  ├─ dns-activate ──API──► Namecheap | GoDaddy | IONOS | Cloudflare
  │                         (pay.odeiafrica.com → ODEI_EDGE_IP)
  └─ deploy-edge ──SSH──► VPS
                            ├─ node apps/serve_product_apps.mjs
                            ├─ node hosting/gateway.mjs  (:8080)
                            └─ Caddy (TLS) ← DNS A/CNAME
```

## One-time setup

1. **Own the apex** at https://www.namecheap.com · https://www.godaddy.com · https://www.ionos.com (or any registrar).
2. **Create a VPS**; note its public IP → that is `ODEI_EDGE_IP`. Details: `docs/EDGE_IP_AND_API_KEYS.md`.
3. **Put this folder on GitHub** — canonical remote:

   https://github.com/infoedutechos/ODEI-Multi-Ecosystem

   Atlas + Vercel env notes: [`GITHUB_MONGODB_VERCEL.md`](./GITHUB_MONGODB_VERCEL.md)
4. **Add Actions secrets** from `hosting/github-secrets.example`  
   (Repo → Settings → Secrets and variables → Actions).
5. **Optional but recommended:** Point registrar nameservers to **Cloudflare**, then use Cloudflare secrets for DNS + TLS.

## Run from GitHub Actions

| Workflow | When | What |
|----------|------|------|
| **ODEI Hosting Kit CI** | push/PR touching hosting | Dry-run DNS payloads + artifact checks |
| **ODEI DNS Activate** | manual | Apply DNS at chosen provider |
| **ODEI Deploy Edge** | push to main / manual | rsync apps+hosting to VPS, restart gateway |
| **ODEI Public DNS Verify** | schedule / manual | Resolve all `*.odeiafrica.com` |

### Activate DNS (example)

Actions → **ODEI DNS Activate** → Run workflow → provider `cloudflare` (or `godaddy` / `namecheap` / `ionos`).

### Deploy edge

Actions → **ODEI Deploy Edge** → Run workflow  
(requires `EDGE_SSH_HOST`, `EDGE_SSH_USER`, `EDGE_SSH_KEY`).

## Supported registrars / DNS hosts

- https://www.namecheap.com — API or `registrars/namecheap-hosts.csv`
- https://www.godaddy.com — API or `registrars/godaddy-records.json`
- https://www.ionos.com — Control Panel / API (`IONOS_ZONE_ID` for API)
- Cloudflare — recommended even if domain bought elsewhere

## Local commands (same scripts CI uses)

```powershell
python _enable_registrar_activation.py
python hosting\activate_dns.py --provider dry-run
python hosting\ci_verify_kit.py
python hosting\verify_domains.py --public-only
```

## Honest limits

- GitHub **cannot** buy a domain or invent registrar ownership.
- Live apply needs **your** API keys + a real edge IP that serves traffic.
- Until DNS propagates, `verify_domains.py --public-only` will report `NO_PUBLIC_DNS` (expected).

## Regenerators

```powershell
python _enable_registrar_activation.py
python _enable_github_hosting.py
```
