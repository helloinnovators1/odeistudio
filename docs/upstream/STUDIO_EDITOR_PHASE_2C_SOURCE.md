> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_PHASE_2C.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_EDITOR_PHASE_2C.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Studio Editor / Extension — Phase 2c (Extension deepen)

**Date:** 2026-07-31  
**Status:** Implemented (extension `odei-studio` **0.3.0**)  
**Path:** Architecture **D** (host Cursor/VS Code) per [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md)  
**Code:** `ODEI Studio/extensions/odei-studio/`  
**Desktop scaffold (C, not binary):** `ODEI Studio/desktop/` · [`STUDIO_DESKTOP_CODE_OSS_ROADMAP.md`](./STUDIO_DESKTOP_CODE_OSS_ROADMAP.md)

## Delivered

| Area | What shipped |
|------|----------------|
| Surfaces | Commands open `/editor`, `/app`, website `:5226`, API health, path-bridge start/allowlist |
| Status bar | API + path-bridge health pills |
| Webview | Recent builds, agents chips, quick actions, actionable down errors |
| Tree | “Surfaces & host” quick actions |
| Host Git/Terminal/FS | Open Terminal Here, Show Git (SCM), Reveal Active File — **honest host reuse** |
| AI | Build-from-goal panel; Copy Goal for Host Chat; ModelRouter stub via `odei.modelRouterUrl` — **not Cursor Tab AI** |
| Packaging | `npm run package` (`vsce`); README install for Cursor + VS Code; version **0.3.0** |
| Config | `apiUrl`, `studioUrl`, `websiteUrl`, `pathBridgeUrl`, `pathBridgeToken`, `modelRouterUrl`, `statusBarPollMs` |

## Explicit non-goals (still true)

- No companion PTY on `:4010`
- No fake LSP Problems in browser Editor
- No Cursor Tab clone
- No shipped Code-OSS `.exe` (Desktop = scaffold docs only)

## Web honesty (Phase 2c polish)

- Terminal / status-bar copy distinguishes **path-bridge** absolute paths vs user-attached paths
- About matrix notes Desktop Code-OSS scaffold + `odei-studio` 0.3.x host path
- Website / honesty / docs cross-links keep `full_cursor_com: false`

## Install VSIX

```powershell
cd ".\ODEI Studio\extensions\odei-studio"
npm run package
cursor --install-extension .\odei-studio-0.3.0.vsix
```

