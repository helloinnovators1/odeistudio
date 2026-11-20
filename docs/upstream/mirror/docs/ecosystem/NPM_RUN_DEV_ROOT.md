> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/NPM_RUN_DEV_ROOT.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/NPM_RUN_DEV_ROOT.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Fix: `npm error Missing script: "dev"` at ecosystem root

**Updated:** 2026-07-24  
**Symptom:** From `ODEI Multi Ecosystem`, `npm run dev` failed with `Missing script: "dev"`.

## Cause

1. The workspace root is a **multi-product ecosystem**, not a single app. Historically there was **no root `package.json` `dev` script**.
2. Terminal typos also appeared in the session: `npn run dev` (invalid) and a broken line `n` / `pm run dev`.

## Fix (applied)

Root [`package.json`](../package.json) now provides:

```powershell
npm run dev          # product sites :5180 + :5201–5223
npm run dev:gateway  # Host gateway :8080
npm run dev:docs     # docs :8765
npm run dev:opms     # OPMS UI :5173
npm run help
```

## Correct commands

```powershell
cd "C:\Users\Software Innovations\Desktop\ODEI Multi Ecosystem"
npm run dev
```

Then open http://localhost:5180/

For OPMS only:

```powershell
cd ".\ODEI Pre-Sale Management System (OPMS)"
npm run dev
```

See [`HOW_TO_RUN_LOCAL.md`](HOW_TO_RUN_LOCAL.md).  
Wallet Universal Account: http://localhost:5220/app/ · [`ODEI_WALLET_UNIVERSAL_ACCOUNT.md`](ODEI_WALLET_UNIVERSAL_ACCOUNT.md)
