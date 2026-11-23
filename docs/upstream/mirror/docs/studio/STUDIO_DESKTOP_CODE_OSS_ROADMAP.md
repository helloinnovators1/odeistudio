> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_DESKTOP_CODE_OSS_ROADMAP.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_DESKTOP_CODE_OSS_ROADMAP.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Studio Desktop — Code-OSS / VSCodium Roadmap

**Status:** Scaffold roadmap — **no binary claimed**  
**Aligned with:** [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) · [`ODEI_ECOSYSTEM_STACK_STRATEGY.md`](./ODEI_ECOSYSTEM_STACK_STRATEGY.md) · `ODEI Studio/desktop/` · `ODEI Studio/vscode/`  
**Strategy:** **C via D→C** — deepen extension first; Desktop is a **separate** product from Next Studio App.

---

## 1. Goal

Ship an installable **ODEI Studio Desktop** based on **Code-OSS (MIT)** (or VSCodium-class build), branded with existing `product.overrides.json`, bundling `odei-studio` + theme, talking to Studio API `:4000`.

**Non-goals for this roadmap doc:**

- Electron-wrapping Next `:3002` as the IDE (option **B** — rejected)
- Claiming Cursor Tab AI / Cursor billing / Cursor sync
- Wiring `marketplace.visualstudio.com` into a fork (ToS)

---

## 2. Prerequisites (build machine)

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM | 8 GB | **16 GB+** |
| Disk | 10 GB free | 20 GB+ |
| Node.js | 20.x | 22.x |
| Python | 3.11 | 3.12 |
| Windows | VS 2022 C++ Build Tools | — |
| Network | GitHub clone of `microsoft/vscode` | Mirror OK |

**CI policy:** do **not** download multi-GB upstream in default PR CI. Use a dedicated nightly/manual workflow with a large runner when ready.

---

## 3. Build steps (MVP 3.0)

### 3.0 Reliable clone → compile → launch

Existing Studio scripts (PowerShell):

```text
ODEI Studio/
  npm run vscode:setup      # fork:vscode + brand + integrate
  npm run vscode:install
  npm run vscode:compile
  npm run vscode:launch
  npm run build:ide         # orchestrated pipeline
```

Manual / documented stubs (no auto-download):

```text
ODEI Studio/desktop/scripts/fetch-code-oss.ps1
ODEI Studio/desktop/scripts/fetch-code-oss.sh
```

Target tree (after opt-in clone):

```text
ODEI Studio/vscode/
  product.overrides.json
  defaults.settings.json
  contrib/
  upstream/                 # gitignored Code-OSS
```

### 3.1 Branding

- Apply `product.overrides.json` (name, data folder `.odei-studio`, `urlProtocol: odei-studio`)
- Do **not** ship Microsoft product icons/trademarks as “VS Code”
- Preserve MIT notices from Code-OSS

### 3.2 Extensions gallery — legal path

| Do | Do not |
|----|--------|
| Point gallery at **Open VSX** or a **private/curated** VSIX list | Point `product.json` at `marketplace.visualstudio.com` for a non-Microsoft product |
| Bundle MIT extensions (`odei-studio`, ODEI theme) | Redistribute Microsoft Marketplace-only extensions (e.g. many Remote-* bits) without license |

### 3.3 Wire Desktop ↔ Studio

- Default `odei.apiUrl` → Studio API
- Optional path-bridge only for hybrid web workflows (Desktop has native FS)
- Honesty: Web `/editor` remains the light/PWA surface

### 3.4 Updates + auth (later)

- Signed update channel
- ODID login for cloud AI when Identity ships
- Never fake settings sync

---

## 4. CI sketch (future)

```yaml
# Conceptual — not enabled by default
# workflow_dispatch / nightly on windows-latest-16core (or self-hosted 16GB)
# steps: checkout → setup node/python/msbuild → cache upstream → compile → artifact
# PR CI: docs + extension typecheck only (current)
```

---

## 5. Remote / LSP on Desktop

- Prefer community / Open VSX language servers (e.g. Pyright) over Marketplace-locked Microsoft extensions
- Remote-SSH parity with stock VS Code is **XL** and legally constrained — document host-Cursor (D) as interim; own agent later

---

## 6. Exit criteria (flip marketing carefully)

See investigation §9 “full parity” gate. Until then:

- `full_cursor_com: false` in `status.json`
- Desktop folder labeled **scaffold**
- Extension Phase 2c is the real near-term IDE host path

---

## 7. Remaining XL work (honest)

1. Stable Windows (and later macOS/Linux) compile + packaging  
2. Monthly Code-OSS rebase + security patches  
3. Open VSX / curated gallery product.json  
4. Signed installers + auto-update  
5. Remote story without illegal Marketplace reuse  
6. ODEI AI (ModelRouter, rules, consented context) inside the workbench — not Cursor clones  
7. ODID + Pay seats  

**Until those land, install `odei-studio` 0.3.x into Cursor/VS Code.**

