> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_MAC_REMEDIATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_MAC_REMEDIATION.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Studio MAC remediation

**Date:** 2026-07-30  
**Scope:** Close Phase 1.5 gaps from [`STUDIO_MAC_FULLY_OPERATIONAL_INVESTIGATION.md`](STUDIO_MAC_FULLY_OPERATIONAL_INVESTIGATION.md).  
**Related:** [`STUDIO_HOLISTIC_SCAN_REMEDIATION.md`](STUDIO_HOLISTIC_SCAN_REMEDIATION.md)

## What was fixed

| Gap | Fix |
|-----|-----|
| CORS `:5226` → `:4000` | `DEV_ORIGINS` includes `localhost:5226`, `127.0.0.1:5226`, `studio.localhost:5226`, App vhosts |
| Fake health pill | `mac-studio.js` probes website / app / editor / API; pill `ok` / `warn` / `down` |
| Static sample rows | Live `GET /api/v1/agents`, `/builds`, `/uploads`; `GET /api/v1/ops/summary` |
| Composer stubs | Builds POST `/api/v1/build`; Uploads file → POST `/api/v1/uploads`; API settings key field |
| Placeholder REC-1001 modules | Replaced with Build OS modules + honest `planned-ops` panel |
| `studio` missing from auth seed | Added to `ECOSYSTEM_PRODUCT_IDS` in `_shared` + all product `odei-auth.js` copies |
| Command Center App mislabeled as MAC | `studio-app` uses `healthProbe`, `mac: null`, `isMac: false`; Command Center UI says Open App |
| Docs / status | `status.json`, honesty, PRODUCT_MAC_CONSOLES, COMMAND_CENTER, macs.json, manifest |

## How to verify (Windows)

1. Ensure shells + Studio are up (`npm run dev` / `node apps/dev_all.mjs` — do not kill unrelated services).
2. **Restart Studio API** so new CORS + `/uploads` list + `/ops/summary` load:
   ```powershell
   # From ODEI Studio workspace, if API is already running restart its terminal, then:
   curl http://localhost:4000/health
   curl http://localhost:4000/api/v1/ops/summary
   curl http://localhost:4000/api/v1/agents
   ```
3. Open staff MAC: `http://localhost:5226/admin/` (staff invite `ODEI-ADMIN` / `ODEI-OPERATOR` on localhost if needed).  
   **Note:** `http://localhost:35226/admin` is **not** a Studio port — that is a typo for **5226**.
4. Confirm `#mac-health` shows `N/4 surfaces` (not a static “OK” string).
5. Open **Agents / Builds / Uploads** — Manage tables hydrate from API (empty is honest if no builds yet).
6. Builds → Composer → **Run template build**; Uploads → **Upload image**.
7. Optional: API settings → set key if `ODEI_STUDIO_API_KEY` is set on the API process.
8. Cross-links: Open App `:3002/app`, Editor `:3002/editor`, API health, Extension docs on Developers.

## Remaining (honest — do not fake)

- Production ODID JWT on MAC + API  
- Live LLM agents (still template / `local_sim`)  
- Signed cloud uploads + malware scan  
- Workspace CRUD API (implicit `ws_default` only)  
- OPMS-depth React MAC (shared kit is Phase 1.5 ceiling)  
- Persistent builds across API restarts
