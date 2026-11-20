> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_PARTNER_PROJECTS_MMD360.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_PARTNER_PROJECTS_MMD360.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Partner Projects implementation note

**Updated:** 2026-08-04

## Architecture (as implemented)

```
OIPTECH
 └── ODEI Multi-Ecosystem
      ├── Shared rails (Identity, AI, Pay, Wallet, Marketplace, Comms, OCS, Cloud, …)
      └── Partner Projects (:5229)
           └── Tenants
                └── MMD360 — Masaka Muslim District 360 (:5228)  [first tenant]
                └── UMYS / SACCO / Schools / NGO / Hospital / Coop templates (planned)
```

## URLs

| Surface | URL |
|---------|-----|
| Partner hub | http://localhost:5229/ |
| Partner admin | http://localhost:5229/admin/ |
| MMD360 | http://localhost:5228/ |
| Multi-Ecosystem Partners map | http://localhost:5180/partners.html |

## Honesty

local_sim. File-backed tenancy + district fixtures. Shared rails are linked by URL, not forked. Not UMSC360 production. Not live Mobile Money. Not constitutional authority.

Vision corpus remains under `Masaka Muslim District Digital Platform (MMDDP)/`.
