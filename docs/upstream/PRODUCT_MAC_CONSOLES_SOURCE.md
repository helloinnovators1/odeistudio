> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/PRODUCT_MAC_CONSOLES.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ecosystem/PRODUCT_MAC_CONSOLES.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Product Master Admin Consoles (MAC)

**Updated:** 2026-08-18  
**Count:** 24+ (shared-kit products) · plus Studio website MAC · plus OPMS React MAC

Each product below has an **independent Master Admin Console & Dashboard** at `/admin/`, modeled on OPMS MAC (sidebar groups, workspace tabs, KPI deck, module Card deck / Composer / Manage, global search Ctrl+K).

**Studio note:** ODEI Studio website MAC is at `:5226/admin/` — Phase 1.5 **API-hydrated** (agents/builds/uploads/health from `:4000`). Do **not** treat `:3002/app` (Agents App) or `:3002/editor` as the MAC. See [`STUDIO_MAC_REMEDIATION.md`](STUDIO_MAC_REMEDIATION.md) · [`STUDIO_HOLISTIC_SCAN_REMEDIATION.md`](STUDIO_HOLISTIC_SCAN_REMEDIATION.md).

## Open

| Product | MAC URL |
|---------|---------|
| **ODEI Command Center** (all MACs) | http://localhost:5180/command/ |
| **ODEI Studio** (website MAC) | http://localhost:5226/admin/ |
| ODEI Academy | http://localhost:5201/admin/ |
| ODEI Cloud | http://localhost:5202/admin/ |
| ODEI AI | http://localhost:5203/admin/ |
| ODEI Chain OS | http://localhost:5204/admin/ |
| ODEI Communications | http://localhost:5205/admin/ |
| ODEI Core | http://localhost:5206/admin/ |
| ODEI DeFi | http://localhost:5207/admin/ |
| ODEI DEX | http://localhost:5208/admin/ |
| ODEI Earn | http://localhost:5209/admin/ |
| ODEI Exchange | http://localhost:5210/admin/ |
| ODEI Foundation | http://localhost:5211/admin/ |
| ODEI Launchpad | http://localhost:5212/admin/ |
| ODEI Marketplace | http://localhost:5213/admin/ |
| ODEI Merchant Platform | http://localhost:5214/admin/ |
| ODEI Pay | http://localhost:5215/admin/ |
| ODEI Store | http://localhost:5216/admin/ |
| ODEI Switch | http://localhost:5217/admin/ |
| ODEI Tokens | http://localhost:5218/admin/ |
| ODEI Treasury | http://localhost:5219/admin/ |
| ODEI Wallet | http://localhost:5220/admin/ |
| ODEL Hub | http://localhost:5221/admin/ |
| ODEI Identity | http://localhost:5222/admin/ |
| DiCEI Africa | http://localhost:5223/admin/ |
| ODEI Multi-Ecosystem | http://localhost:5180/admin/ |

Multi-Ecosystem MAC **Env vars** (`http://localhost:5180/admin/#/env`) configures Atlas + Vercel slots and materializes gitignored `.env.local`. See [GITHUB_MONGODB_VERCEL.md](GITHUB_MONGODB_VERCEL.md). Sidebar hide: ☰ + **Show menu** FAB ([apps/_shared/mac/README.md](../apps/_shared/mac/README.md)).

## Regenerate
```powershell
python _build_product_mac_consoles.py
```

## Shared kit
`apps/_shared/mac/mac.css` · `mac.js` · [README.md](../apps/_shared/mac/README.md)

OPMS reference (full React MAC): http://localhost:5173/admin
