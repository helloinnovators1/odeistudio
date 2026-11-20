> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_HOLISTIC_SCAN_REMEDIATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_HOLISTIC_SCAN_REMEDIATION.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio — Holistic scan remediation

**Audited / remediated:** 2026-07-30  
**Surfaces:** Website `:5226` · MAC `/admin` · App `:3002/app` · Editor `:3002/editor` · API `:4000` · Extension · Registry / Command Center / Hosting / Auth / Docs

## Scan method

Grep + file reads across `apps/studio/`, `ODEI Studio/apps/web/`, `packages/api/`, `extensions/odei-studio/`, registry, `dev_all.mjs`, `serve_product_apps.mjs`, hosting Caddy/nginx/DNS, shared auth, status/honesty docs. Fixed every actionable Phase 1.5 defect found; documented Phase 2+ without fake readiness claims.

## Findings summary

| # | Area | Finding | Disposition |
|---|------|---------|-------------|
| 1 | API CORS | `:5226` missing from allowlist | **Fixed** |
| 2 | MAC health | Fake always-OK pill | **Fixed** — live probes |
| 3 | MAC data | Static config / `alert(connect API)` | **Fixed** — `mac-studio.js` |
| 4 | Uploads list | No `GET /api/v1/uploads` | **Fixed** |
| 5 | Ops aggregate | MAC needed counts | **Fixed** — `GET /api/v1/ops/summary` |
| 6 | Auth seed | `studio` absent from `ECOSYSTEM_PRODUCT_IDS` | **Fixed** (shared + 25+ product copies) |
| 7 | Command Center | App row labeled Open MAC | **Fixed** — `isMac:false` / healthProbe |
| 8 | `dev_all.mjs` | `--only=studio` remapped to nonexistent `studio-app` id | **Fixed** |
| 9 | Developers page | No extension install anchor | **Fixed** — `#desktop-extension` |
| 10 | Agents shell | “Soon” stub wording | **Fixed** → “Planned” |
| 11 | DNS registrars | Missing `app.studio.odeiafrica.com` | **Fixed** (CF / GoDaddy / IONOS) |
| 12 | Manifest | Studio missing from `mac-consoles-manifest.json` | **Fixed** |
| 13 | Status / honesty | Claimed shell-only MAC | **Fixed** — API-hydrated Phase 1.5 |
| 14 | Placeholder modules | REC-1001 CoinCore-style leftovers in Studio MAC | **Fixed** — Build OS modules |
| 15 | Caddy / nginx | studio vs app.studio already split | **OK** — no change needed |
| 16 | `serve_product_apps` skip | Correctly skips `studio-app` (Next on :3002) | **OK** |
| 17 | Registry interconnect | `studio` → site, `studioApp` → app | **OK** |
| 18 | Editor bridge | Phase 2a behavior present | **Preserved** |
| 19 | ODID / LLMs / Code-OSS | Not local Phase 1.5 | **Out of scope** (documented) |
| 20 | Running API process | Hot code not loaded until restart | **Operator action** — restart API to pick up routes |

**Approximate scan findings addressed:** ~20 (14 fixed, 3 OK, 2 out-of-scope, 1 operator restart).

## Files changed (primary)

- `ODEI Studio/packages/api/src/index.ts`, `media-store.ts`
- `apps/studio/admin/*` (`config.json`, `mac.js`, `mac-studio.js`, `mac.css`, `index.html`)
- `apps/studio/{status,developers,honesty}.*`
- `apps/_shared/auth/odei-auth.js` + all product `auth/odei-auth.js` copies
- `apps/multi-ecosystem/command/{macs.json,command.js}`
- `apps/dev_all.mjs`, `apps/mac-consoles-manifest.json`
- `ODEI Studio/apps/web/.../agents-shell.tsx`, `ODEI Studio/status.json`
- `hosting/registrars/{cloudflare,godaddy,ionos}-records.json`
- `docs/STUDIO_MAC_REMEDIATION.md`, this file, PRODUCT_MAC / COMMAND_CENTER updates

## MAC status (Phase 1.5)

**Operational for local Phase 1.5:** staff gate, live surface health, API-hydrated agents/builds/uploads, compose build/upload, API key session field, honest planned panels, correct Command Center labeling.

**Not** production-complete / not OPMS-depth.

## Remaining honest gaps (Phase 2+)

- ODID JWT on App + API + MAC  
- Live LLM agent pipeline  
- Signed object storage + malware scan  
- Persistent builds / workspace CRUD  
- Full Code-OSS / ODEI IDE fork (Phase 2b+)  
- Claiming MAC equals OPMS depth

## Verify

See [`STUDIO_MAC_REMEDIATION.md`](STUDIO_MAC_REMEDIATION.md). Also:

```powershell
cd "e:\ODEI Multi Ecosystem\ODEI Studio"
npm run typecheck -w @odei/api
npm run typecheck -w @odei/web
# Extension (optional):
npm run typecheck -w odei-studio

curl http://localhost:4000/health
curl http://localhost:4000/api/v1/ops/summary
# MAC assets:
curl http://localhost:5226/admin/config.json
curl http://localhost:5226/admin/mac-studio.js
```
