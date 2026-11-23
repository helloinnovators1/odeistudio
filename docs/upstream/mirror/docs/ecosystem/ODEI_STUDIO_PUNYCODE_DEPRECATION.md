> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_STUDIO_PUNYCODE_DEPRECATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_STUDIO_PUNYCODE_DEPRECATION.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Studio — Node `punycode` deprecation warning

**Date:** 2026-07-31  
**Context:** `cursor --install-extension .\odei-studio-0.3.0.vsix` printed a Node.js `punycode` deprecation warning.

---

## Verdict

**Not from ODEI Studio / odei-studio / path-bridge code.**  
Harmless. **Not fixable in-repo.** No code or dependency change is warranted.

---

## Investigation

| Area | Result |
| --- | --- |
| `ODEI Studio/extensions/odei-studio` (src, dist, scripts) | **Zero** `punycode` references |
| `ODEI Studio/packages/path-bridge` | **Zero** `punycode` references |
| Extension `package.json` runtime deps | **None** — only `@types/node`, `@types/vscode`, `typescript` (dev) |
| Package script | `npx @vscode/vsce package --no-dependencies` — packaging only; install is Cursor CLI |

Node has deprecated the built-in `punycode` module (DEP0040). Cursor’s CLI (and much of the Node ecosystem) still hit it indirectly via the legacy `url` parser when handling paths/URLs during extension install. That stack lives in **Cursor / Node**, not in the VSIX payload we ship.

---

## What we did **not** do

- No fake silence flags in our scripts
- No unused `punycode` / `tr46` dependency upgrades (nothing of ours pulls them)
- No change to extension runtime

---

## If the warning reappears

1. Confirm the stack mentions Cursor install / Node internals, not `odei-studio` or path-bridge.
2. Re-grep `ODEI Studio/extensions/odei-studio` and `packages/path-bridge` for `punycode`.
3. Only act if a **new** runtime dependency we add imports `punycode` directly — then upgrade or replace that dep.
