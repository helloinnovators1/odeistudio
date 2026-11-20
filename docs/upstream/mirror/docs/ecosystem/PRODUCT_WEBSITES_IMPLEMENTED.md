> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/PRODUCT_WEBSITES_IMPLEMENTED.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/PRODUCT_WEBSITES_IMPLEMENTED.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Full product websites — implemented

**Updated:** 2026-07-24  
**Count:** 21 / 21

Each listed product now has a **unique multi-page website** under `apps/<id>/`, generated from its Documentation Suite Website IA, with distinct brand (type, palette, atmosphere). Marked `.custom` + `.full-website` so shell regenerators do not overwrite.

## Products

| Product | Port | Pages | IA source |
|---------|-----:|------:|-----------|
| ODEI Academy | 5201 | 23 | `ODEI Academy/ODEI Academy Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Cloud | 5202 | 23 | `ODEI Cloud/ODEI Cloud Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI AI | 5203 | 23 | `ODEI AI/ODEI AI Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Chain OS | 5204 | 24 | `ODEI Chain OS is an AI-native Digital Operating System for Africa and beyond/ODEI Chain OS Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Communications | 5205 | 23 | `ODEI Communications/ODEI Communications Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Core | 5206 | 23 | `ODEI Core/ODEI Core Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI DeFi | 5207 | 23 | `ODEI DeFi/ODEI DeFi Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI DEX | 5208 | 23 | `ODEI DEX/ODEI DEX Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Earn | 5209 | 23 | `ODEI Earn/ODEI Earn Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Exchange | 5210 | 23 | `ODEI Exchange/ODEI Exchange Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Foundation | 5211 | 23 | `ODEI Foundation/ODEI Foundation Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Launchpad | 5212 | 23 | `ODEI Launchpad/ODEI Launchpad Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Marketplace | 5213 | 23 | `ODEI Marketplace/ODEI Marketplace Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Merchant Platform | 5214 | 23 | `ODEI Merchant Platform/ODEI Merchant Platform Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Pay | 5215 | 23 | `ODEI Pay/ODEI Pay Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Store | 5216 | 23 | `ODEI Store/ODEI Store Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Switch | 5217 | 23 | `ODEI Switch/ODEI Switch Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Tokens | 5218 | 23 | `ODEI Tokens/ODEI Tokens Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Treasury | 5219 | 23 | `ODEI Treasury/ODEI Treasury Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEI Wallet | 5220 | 23 | `ODEI Wallet/ODEI Wallet Documentation Suite/md/03_Ecosystem_Website_IA.md` |
| ODEL Hub | 5221 | 22 | `ODEL Hub/ODEL Hub Documentation Suite/md/03_Ecosystem_Website_IA.md` |

## Verify

```powershell
python hosting\verify_product_websites.py
.\START_PRODUCT_APPS.bat
```

Open e.g. http://localhost:5215/ (Pay), http://localhost:5201/ (Academy).
