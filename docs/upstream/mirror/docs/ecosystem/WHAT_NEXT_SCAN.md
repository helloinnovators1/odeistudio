> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/WHAT_NEXT_SCAN.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/WHAT_NEXT_SCAN.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# What Next — Deep Holistic Scan

**Updated:** 2026-07-24  
**Canvas:** `next-scan-2026-07-24.canvas.tsx`  
**Authorities:** live ports · `tests/test_p0_authz.py` · `BUILD_ORDER_ROADMAP.md` · folder maturity

---

## Verdict

**Docs + P0 backend authz are done enough.**  
**Next = engineering:** close frontend auth UX (P0b) → **ODEI Core** SDK → **Identity (ODID) extract** → Wallet/Switch/Pay/ODUSD.  
Do **not** expand prose or launch DiCEI Verses next.

---

## Live runtime (this machine)

| Port | Service | Probe |
|-----:|---------|-------|
| 5173 | OPMS Vite (MAC UI) | 200 on `[::1]` |
| 8000 | OPMS API | 200 `/health` |
| 8765 | Docs library | 200 `/docs/` |
| 3002 | ODEI Studio web | LISTEN |

## P0 authz

| Control | State |
|---------|--------|
| `tests/test_p0_authz.py` | **8/8 passed** |
| Admin routers with `require_user` | **19** (website.py intentionally public) |
| `/auth/demo` | Disabled unless `ALLOW_AUTH_DEMO=true` |
| `/env*` + MAC component download | JWT required |
| Frontend `demoAuth` in `PlatformPages.tsx` | **Still calls `/auth/demo` — gap** |

## Folder reality

| Area | Reality |
|------|---------|
| OPMS | Live FastAPI + React (only full product runtime) |
| ODEI Studio | Live seed; `dev:web` on 3002; API workspace build fragile |
| ODEI Core / Identity / Wallet / Pay / … | **Documentation suites + prose; no standalone runtime packages** |
| DiCEI Africa | Brand + suite docs; no Verse runtime |

---

## Priority queue

1. **P0b — Close OPMS authz UX** (0.5–1 day)  
   Login must not depend on `/auth/demo`; MAC env calls must send JWT.

2. **P0-CORE — Scaffold ODEI Core** (1–2 weeks)  
   Shared authz/tenancy/audit SDK; ≥1 OPMS consumer.

3. **P0-ODID — Extract Identity API** (2–4 weeks)  
   Versioned ODID from OPMS identity patterns.

4. **P1 — Wallet → Switch → Pay → ODUSD** (1–2 quarters)  
   Money spine before DiCEI.

5. **OPS — Git / LICENSE / secrets** (days)

## Explicit non-next

- More institutional prose as a substitute for Core/Identity code  
- Building all 25 products in parallel  
- DiCEI Verse token launches before Pay/ID  
- Merging OCRE into DiCEI Verses (or vice versa)

---

## Architecture prerequisite (accepted 2026-07-24)

**Independent product addresses** before deeper Core work:

- Registry: `apps/ecosystem-registry.json`
- Map: `docs/PRODUCT_PORTS_AND_DOMAINS.md`
- Launcher: `START_PRODUCT_APPS.bat`

Each listed product has its own `localhost:PORT` (and future `*.odeiafrica.com` host) while interconnecting via shared API/docs/SSO rails.
