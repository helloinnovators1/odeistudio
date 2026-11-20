> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/apps/multi-ecosystem/HOSTING.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/apps/multi-ecosystem/HOSTING.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# HOSTING — ODEI Multi-Ecosystem

**Updated:** 2026-08-19  
**Product id:** `multi-ecosystem`  
**Local port:** 5180  
**Local URL:** http://localhost:5180/  
**Prod host (registry):** `multi.odeiafrica.com`

> Honesty: registry hostname ≠ live on Namecheap. Local :5180 ≠ production hosting.

| Field | Value |
|-------|-------|
| Hosting mode | **hybrid** |
| Ready for Namecheap? | **PARTIAL** |
| API handler | `apps/multi-ecosystem/api/handler.mjs` |
| Upstream | `127.0.0.1:5180` |
| Pack artifact | `npm run pack:hosting -- multi-ecosystem` → `dist/hosting/multi-ecosystem-*.tgz` |

## What works today (local)

- Product shell via `npm run dev` / `apps/serve_product_apps.mjs` (when `apps/multi-ecosystem/index.html` exists)
- Named vhost via gateway: `http://multi.localhost:8080/`
- **Civilizational map:** http://localhost:5180/civilizational/ — static `apps/multi-ecosystem/civilizational/` (icons + `index.html`; no separate API)
- **Ecosystem map:** http://localhost:5180/ecosystem-map.html

## Namecheap / VPS path

- **Shared hosting (cPanel PHP-only):** static pages only — **/v1 APIs will not work**.
- **VPS / Node:** run `node apps/serve_product_apps.mjs` (or PM2/systemd samples) + nginx/Caddy reverse_proxy to `127.0.0.1:5180`.

## Sample edge paths (copy-paste)

### cPanel / Apache document root
```text
cPanel static upload = brochure ONLY. /v1/* will 404.
Prefer Namecheap VPS + Node (below). Optional: cPanel “Setup Node.js App” for ONE product.
```

### nginx (VPS)
```nginx
# From docs/ops/deploy/samples/nginx.product.sample.conf
# PRODUCT_HOST=multi.odeiafrica.com  PRODUCT_PORT=5180
upstream odei_multi_ecosystem { server 127.0.0.1:5180; }
# server_name multi.odeiafrica.com; proxy_pass http://odei_multi_ecosystem;
```

### Caddy (VPS)
```caddy
multi.odeiafrica.com {
  reverse_proxy 127.0.0.1:5180
}
```

### Process manager
- **PM2:** `pm2 start docs/ops/deploy/samples/ecosystem.config.cjs`
- **systemd:** `docs/ops/deploy/samples/systemd/odei-product-apps.service`

## Missing pieces

Needs Node for /v1/* (file-backed local_sim). cPanel PHP-only will break APIs. Use PM2/systemd + durable storage before production claims.

## Env

`apps/multi-ecosystem/.env.example`  
Shared template: `docs/ops/deploy/samples/.env.product.example`.

## TLS

Human steps: own domain → point DNS → AutoSSL (cPanel) or Let's Encrypt (VPS Caddy/certbot).  
Checklist: `docs/ops/deploy/TLS_CHECKLIST.md`.

## Health check

```bash
npm run health:deployed -- https://multi.odeiafrica.com
# require API: npm run health:deployed -- --require-api https://multi.odeiafrica.com
```
Probes `/` and `/v1/health`.

## Notes

Static shell + apps/<id>/api/handler.mjs via serve_product_apps.mjs.

## See also

- [../../docs/ops/deploy/ODEI_NAMECHEAP_AND_INDEPENDENT_HOSTING_STATUS.md](../../docs/ops/deploy/ODEI_NAMECHEAP_AND_INDEPENDENT_HOSTING_STATUS.md)
- [NAMECHEAP_PATH.md](../../docs/ops/deploy/NAMECHEAP_PATH.md)
- [NAMECHEAP_E2E_CHECKLIST.md](../../docs/ops/deploy/NAMECHEAP_E2E_CHECKLIST.md)
