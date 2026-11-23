> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/MASTER_WEBSITE.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/MASTER_WEBSITE.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Multi-Ecosystem — Master Website

**Updated:** 2026-07-24  
**Local:** http://localhost:5180/  
**Production:** https://multi.odeiafrica.com/

The master website is the professional directory for all independent product surfaces.
The footer lists every product; each link opens that product’s own website (port / future domain).

## Run

```powershell
cd apps
node serve_product_apps.mjs
```

Then open http://localhost:5180/

## Core & Identity address contracts

| Surface | Local | Production |
|---------|-------|------------|
| ODEI Core | http://localhost:5206/ | https://core.odeiafrica.com |
| ODEI Identity | http://localhost:5222/ | https://id.odeiafrica.com |

Products must resolve peers via `apps/ecosystem-registry.json` / `apps/_shared/interconnect.js` — not hard-coded monolith routes.
