> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Studio Editor ↔ Cursor workspace parity

**Audited + hardened:** 2026-07-30  
**Route:** `http://localhost:3002/editor`  
**Scope:** Loaded workspace after **Open folder** (path-bridge → FSA → webkitdirectory)

This matrix compares Cursor.com / Cursor IDE **Editor Window** surfaces to ODEI Studio’s
in-browser workbench. Studio maximizes chrome and honest local editing; it does **not**
replace Cursor desktop or ship a Code-OSS binary.

## Gap matrix

| Cursor surface | Studio status | Implement now | Bridge / companion | Phase 2+ |
|----------------|---------------|---------------|--------------------|----------|
| Welcome Open / Clone / SSH | **Live** Open; Clone/SSH **Bridge** | Yes (shipped) | Extension URI | — |
| Absolute OS path after Open | **Live** via path-bridge `:4010` | Yes | Companion required | Browser cannot invent paths |
| Explorer tree expand/collapse + icons | **Live** | Harden | — | Multi-root folders |
| Explorer context menu (new/rename/delete) | **Live** where mode allows | Yes | path-bridge: create/write/**rename/delete**; FSA mutate | — |
| Explorer refresh | **Live** | Yes | — | Watcher / chokidar |
| Editor multi-tabs + dirty + close | **Live** | Yes | — | — |
| Tab reorder | **Live** (drag) | Yes | — | — |
| Save / Save All + Ctrl+S | **Live** (mode-honest) | Yes | path-bridge / FSA write | Silent write on webkitdirectory (impossible) |
| Ctrl+W close tab | **Live** | Yes | — | — |
| Text editing engine | **Live** Monaco (Phase 2b) | Yes | dynamic `ssr: false` | Code-OSS / LSP still Phase 2b+ |
| Find in file | Browser Ctrl+F | Honest stub | — | In-editor find |
| Bottom: Problems | **Honest empty** (no LSP) | Yes | Open in Cursor | Real diagnostics |
| Bottom: Output | **Live** Studio API log | Yes | — | Process stdout |
| Bottom: Terminal | **Honest non-shell** (copy cd + Open in Cursor) | Yes — **no exec** | Desktop PTY | Companion command runner (opt-in, high risk — deferred) |
| Bottom: Ports | **Configured links** (not a scan) | Yes + Simple Browser open | — | Live port probe |
| Agents panel + New Agent + history | **Live** (`useStudioBuild`) | Yes | API `:4000` | Vision / real LLM |
| Menu strip File…Help real actions | **Live** | Yes | — | — |
| Status bar path / mode / dirty / problems | **Live** + EOL/encoding stub | Yes | — | Real encoding detect |
| Command palette (Ctrl+K / Ctrl+Shift+P) | **Live** | Yes | — | Fuzzy workspace index |
| Go to file / Ctrl+P | **Live** (loaded entries + palette) | Yes | — | Full recursive index |
| Simple Browser / Preview iframe | **Live** localhost URL tabs | Yes | — | Cookie / auth isolation polish |
| PWA installable shell | **Live** | Yes | Does **not** unlock paths | — |
| Hydration-safe capability copy | **Live** (`useSyncExternalStore`) | Yes | — | — |
| Honesty banners | **Live** (mode-accurate) | Yes | — | — |
| Git / SCM | **Not in browser** | Document | Extension / Cursor | In-tab Git |
| Remote-SSH FS in browser | **Not without companion** | Document | IDE Remote-SSH | Relay |
| Cursor Tab / billing AI | **Out of scope** | Document | — | Never fake |
| Vision LLM on uploads | **Out of scope** | Document | — | Roadmap |
| Multi-root workspaces | Chrome feel only | Partial (single root) | — | Multi-root |
| Code-OSS / ODEI desktop IDE | **Phase 2b+** | Document | — | Ship fork |

## Access modes (honesty)

| Mode | Edit in tabs | Disk write | Absolute path |
|------|--------------|------------|---------------|
| `path-bridge` | Yes | Companion `PUT /v1/write` | Real OS path |
| `fsa-readwrite` | Yes | FSA `createWritable` | Hidden unless attached / companion |
| `fsa-read` | Yes | Download / request write | Hidden unless attached |
| `webkitdirectory` | Yes | Download / zip only | User-attached / companion |

## Explicitly not faked

- Full Cursor.com / Electron workbench  
- Shell / PTY execution inside the browser tab  
- Remote-SSH filesystem without a desktop host  
- Cursor proprietary Tab / billing features  
- Vision LLM reading upload pixels  

## Related docs

- [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) — beyond chrome: full product pillars (desktop/PTY/Git/LSP/AI/marketplace/auth)  
- [`STUDIO_EDITOR_WORKSPACE_VIEW.md`](./STUDIO_EDITOR_WORKSPACE_VIEW.md)  
- [`STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md`](./STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md)  
- [`STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md`](./STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md)  
- [`STUDIO_EDITOR_PHASE_2B.md`](./STUDIO_EDITOR_PHASE_2B.md)  
- [`STUDIO_CURSOR_DESIGN_PARITY.md`](./STUDIO_CURSOR_DESIGN_PARITY.md)  

## Verify (manual)

1. `npm run path-bridge` + Studio web `:3002` → Open folder → status shows absolute path + `path-bridge`.  
2. Edit → Ctrl+S → companion write (Monaco buffer).  
3. Path-bridge: Explorer Rename… / Delete… → tree refreshes.  
4. Ctrl+Shift+P / Ctrl+K → command palette; Ctrl+P → go to file; Ctrl+W → close tab.  
5. Ports → Open in Simple Browser → iframe tab with URL bar.  
6. Firefox without companion → Open folder → Save downloads.  
7. Confirm no hydration mismatch on welcome capability line.  
