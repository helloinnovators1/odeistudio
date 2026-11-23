> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_MEMBERSHIP_PLATFORM_SHELL.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_MEMBERSHIP_PLATFORM_SHELL.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Multi-Ecosystem Membership — Platform Shell

**Updated:** 2026-07-28  
**Product:** ODEI Multi-Ecosystem Membership System (independent)  
**Port:** 5225  
**Hosts:** `membership.localhost` · `membership.odeiafrica.com`

## URLs

| Surface | URL |
|---------|-----|
| Home | http://localhost:5225/ |
| App · Plans | http://localhost:5225/app/ |
| Entitlements | http://localhost:5225/app/entitlements.html |
| Billing | http://localhost:5225/app/billing.html |
| Organizations | http://localhost:5225/app/orgs.html |
| Plan catalog | http://localhost:5225/app/plans.json |
| Member dashboard | http://localhost:5225/dashboard/ |
| MAC | http://localhost:5225/admin/ |
| Login | http://localhost:5225/login.html |
| Gateway | http://membership.localhost:8080/ |
| Production | https://membership.odeiafrica.com/ |

## Plans (catalog)

Free · ODEI+ · ODEI Pro · Business · Enterprise

## Honesty (mandatory)

**Membership billing/entitlements = local simulation until Pay rails.**

| Surface | Label |
|---------|--------|
| Sticky banner | Every HTML page via `/honesty/honesty.js` |
| Plans / billing | `NOT CHARGED` · `LOCAL SIM` badges |
| `plans.json` | `honesty` object + per-plan `billing_honesty` |
| Entitlement claim JSON | `honesty.local_sim` field |
| Status | http://localhost:5225/status.html · `/status.json` |
| MAC | Honesty matrix module |
| Full doc | [`HONESTY.md`](../../ODEI%20Multi-Ecosystem%20Membership%20System/docs/HONESTY.md) |

No real charges on this port until ODEI Pay recurring billing ships.

## Architecture

```
ODEI ID → Membership (catalog · billing · entitlements) → feature flags across products
```
