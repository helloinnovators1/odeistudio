> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/PRODUCT_WEBSITE_AUDIT.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/PRODUCT_WEBSITE_AUDIT.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Product Website Audit — Full-Fledged Unique Sites

**Updated:** 2026-07-24  
**Scope:** 21 products (Academy → ODEL Hub)

## Verdict (after implementation)

**Yes — all 21 now have full unique multi-page websites** generated from each product’s Website IA.

| Check | Result |
|-------|--------|
| Website IA present | **21 / 21** |
| Full multi-page site (`apps/<id>/`) | **21 / 21** |
| Required IA pages present | **21 / 21** (verify: `hosting/verify_product_websites.py`) |
| Unique accent / brand CSS | **21 / 21** distinct accents |
| Live HTTP 200 on product port | **21 / 21** (when product apps server running) |
| Marked `.custom` + `.full-website` | **21 / 21** |

## Pages per product (no IA omission)

Home (hero + About + Product + Architecture + Token/Gov + chrome grid) · About · Product index · **each Product IA feature page** · Architecture · Token · Governance · Roadmap · Developer Hub · Partners · News · Community · Careers · Status · Security · unique `styles.css` + motion `site.js`.

Typically **17–19 HTML pages** per product (Chain has 5 product features → 19).

## How to regenerate / verify

```powershell
python _build_full_product_websites.py
python hosting\verify_product_websites.py
.\START_PRODUCT_APPS.bat
```

Docs: `docs/PRODUCT_WEBSITES_IMPLEMENTED.md` · Manifest: `apps/full-websites-manifest.json`

## Open examples

| Product | URL |
|---------|-----|
| Academy | http://localhost:5201/ |
| Pay | http://localhost:5215/ |
| Core | http://localhost:5206/ |
| Wallet | http://localhost:5220/ |
| via gateway | http://pay.localhost:8080/ |
