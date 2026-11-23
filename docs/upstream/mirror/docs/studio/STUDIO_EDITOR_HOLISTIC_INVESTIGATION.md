> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Studio Editor Window — Holistic Investigation

**Date:** 2026-07-31  
**Route:** `http://localhost:3002/editor`  
**Scope:** Live stack probe + on-disk architecture + open modes + chrome matrix + bug history + extension/bridge + docs honesty + security  
**Code root:** `ODEI Studio/apps/web` · companion `ODEI Studio/packages/path-bridge` · extension `ODEI Studio/extensions/odei-studio`

---

## 1. Executive verdict

**What `/editor` is**

- A **Next.js (App Router) browser workbench** that mirrors Cursor-style chrome after **Open folder**: Explorer, multi-tabs, Agents side panel, bottom panel, menu strip, status bar, command palette, Simple Browser preview tabs, and an installable PWA shell.
- A **mode-honest local editor**: open chain is **path-bridge → FSA → webkitdirectory**; Save / New file / New folder / rename / delete behave differently per mode and never claim Cursor-desktop capabilities.
- The **welcome (Phase 2a)** surface when no folder is open: Open / Clone / SSH handoffs, recents, Install PWA, Attach path for desktop URI.

**What `/editor` is not**

- Not full Cursor.com / Electron / Code-OSS.
- Not a shell, PTY, Git SCM, Remote-SSH filesystem, or LSP host.
- Not a path oracle: **installing the PWA does not unlock OS absolute paths**; only `@odei/path-bridge` on `127.0.0.1:4010` (or user-typed/attached path) does.
- Not a silent disk writer on Firefox/Safari without the companion.

**Live stack (2026-07-31 probe)**

| Surface | URL | Status | Notes |
|---------|-----|--------|-------|
| Editor | `GET http://localhost:3002/editor` | **200** | SSR welcome chrome; amber honesty banner; menu inactive until folder open |
| Agents | `GET http://localhost:3002/app` | **200** | Agents home markers present |
| Web root | `GET http://localhost:3002/` | **200** | `RegisterServiceWorker` in SSR tree; `manifest` linked |
| Studio API | `GET http://localhost:4000/health` | **200** | `ODEI Studio API` v0.1.5, auth none, in-memory builds + local uploads |
| Path bridge | `GET http://127.0.0.1:4010/health` | **200** | `odei-path-bridge`, host `127.0.0.1`, `roots:0`, `tokenRequired:false` |
| SW | `GET http://localhost:3002/sw.js` | **200** | Cache `odei-studio-shell-v2`; **never caches `/_next/*`** |
| Manifest | `GET http://localhost:3002/manifest.webmanifest` | **200** | `start_url: /editor`, honesty in description |

SSR banner snippet (matches `EDITOR_WELCOME_STATUS_BANNER`):  
*“Open a folder to load a Cursor-like workspace here (Explorer, tabs, Agents, palette, Simple Browser). Prefer the Absolute Path Companion on :4010…”*

---

## 2. Surface map

```
http://localhost:3002/editor
├── EditorPage (app/editor/page.tsx) ── client
│   ├── [no root] EditorWelcome
│   │   ├── Honesty banner (editor-copy.ts — SSR-stable)
│   │   ├── Open folder (path-bridge → FSA → webkitdirectory)
│   │   ├── Drag-drop folder → webkitdirectory virtual tree
│   │   ├── Attach / desktop path + Cursor/VS Code URI
│   │   ├── Clone / SSH (Phase 2a bridge — not in-browser FS)
│   │   ├── Recents (localStorage + IndexedDB FSA handles)
│   │   └── InstallStudioPwa (no preventDefault)
│   └── [root open] EditorWindow
│       ├── Menu strip (File…Help — real + disabled-with-hint)
│       ├── Activity rail (Explorer / Agents live; Run/Extensions disabled)
│       ├── Explorer (lazy tree, filter, context menu)
│       ├── Editor tabs + FileViewer (Monaco text engine, preview iframe)
│       ├── Agents panel (useStudioBuild → :4000)
│       ├── Bottom panel (Problems / Output / Terminal·no shell / Ports)
│       ├── Status bar (path, accessMode, dirty, write state)
│       ├── Command palette (Ctrl+K / Ctrl+Shift+P) + Go to file (Ctrl+P)
│       └── Dialogs (attach path, about access mode, …)
├── layout.tsx → RegisterServiceWorker + manifest.webmanifest
├── public/sw.js (shell-v2, network-first navigate, no /_next)
└── companions
    ├── API :4000  (builds, uploads, health)
    └── path-bridge :4010 (pick / resolve / list / read / write)
```

### Code map (absolute under workspace)

| Path | Role |
|------|------|
| `ODEI Studio/apps/web/src/app/editor/page.tsx` | Welcome ↔ workspace; open chain; recents; path map |
| `ODEI Studio/apps/web/src/components/editor/*` | 17 UI modules (window, welcome, explorer, tabs, …) |
| `ODEI Studio/apps/web/src/lib/use-workspace.ts` | Tree, tabs, save/export, create, mutate, preview |
| `ODEI Studio/apps/web/src/lib/fs-access.ts` | FSA + `FolderAccessMode` + limits |
| `ODEI Studio/apps/web/src/lib/virtual-directory.ts` | webkitdirectory virtual handles |
| `ODEI Studio/apps/web/src/lib/path-bridge-client.ts` | Companion HTTP client |
| `ODEI Studio/apps/web/src/lib/path-bridge-fs.ts` | Bridge-backed FsHandles |
| `ODEI Studio/apps/web/src/lib/use-browser-capabilities.ts` | Hydration-safe capability hooks |
| `ODEI Studio/apps/web/src/lib/use-studio-build.ts` | Agents builds/uploads + output log |
| `ODEI Studio/apps/web/src/lib/editor-copy.ts` | SSR-stable welcome banner string |
| `ODEI Studio/apps/web/public/sw.js` | Offline shell SW |
| `ODEI Studio/packages/path-bridge/` | Absolute Path Companion server |
| `ODEI Studio/extensions/odei-studio/` | Desktop commands + bridge helpers |

---

## 3. Open folder modes

### Open order (`pickFolder` in `page.tsx`)

1. **`path-bridge`** — if `GET /health` ok → native pick via `POST /v1/pick-folder` → `createPathBridgeRoot` → `openWorkspace(..., 'path-bridge')` → absolute path remembered.
2. **`fsa-read`** (then may upgrade) — `showDirectoryPicker` → `openWorkspace(..., 'fsa-read')` → `probeWriteAccess` may set **`fsa-readwrite`** when granted.
3. **`webkitdirectory`** — `<input webkitdirectory>` / drag-drop → virtual tree; Save = download / zip.
4. Else — message to start companion or use desktop bridge.

**Path attach** (separate): user types/stores absolute path for status bar, Terminal `cd`, Agents context, and Cursor/VS Code URI — does **not** by itself grant browser disk write.

### Capability by mode

| Mode | Edit in tabs | Disk write | Absolute path | Persist after reload | Rename/Delete |
|------|--------------|------------|---------------|----------------------|---------------|
| `path-bridge` | Yes | Yes (`PUT /v1/write`) | **Real OS path** | Needs companion + recent path / resolve | **Yes** (`/v1/rename`, `/v1/delete`) |
| `fsa-readwrite` | Yes | Yes (`createWritable`) | Hidden unless attach/bridge | IndexedDB handle + permission | Yes |
| `fsa-read` | Yes | Download / request write | Hidden unless attach/bridge | Handle may restore read | No until write granted |
| `webkitdirectory` | Yes | Download / zip only | Attach / companion | **No** (file list ephemeral) | No |

`modeAllowsDiskWrite` = `fsa-readwrite` \| `path-bridge`.  
`canCreateOnDisk` = that ∧ `writeGranted`.  
`canMutateTree` = (FSA ∧ write) ∨ (path-bridge ∧ write) — companion rename/delete live in Phase 2b.

### Absolute paths — honesty

- Browser FSA / webkitdirectory **never** expose OS path strings.
- Companion pick/resolve is the autonomous path source.
- PWA install = standalone shell only (`STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md`, manifest description, Install button copy).

---

## 4. Workspace chrome — live vs stub

| Surface | Status | Detail |
|---------|--------|--------|
| Explorer | **Live** | Lazy list, expand, icons, filter, refresh, New file/folder when writable; rename/delete FSA + path-bridge |
| Tabs | **Live** | Multi-tab, dirty ●, drag reorder, Ctrl+W, truncated files view-only |
| Text engine | **Live (Phase 2b Monaco)** | `@monaco-editor/react` dynamic SSR-off — not full Code-OSS / LSP |
| Save / Save All / Ctrl+S | **Live** | Mode-honest (bridge / FSA / download) |
| Agents panel | **Live** | `useStudioBuild` → `:4000`; folder name + optional path only — **no file contents** |
| Menu strip | **Live + stubs** | Working: Open/Close/Save/Export/panels/palette. Disabled w/ hint: multi-cursor, Zen, Go to line, Run/Debug, New Terminal, dark theme |
| Activity rail | **Partial** | Explorer + Agents; Run/Debug + Extensions disabled |
| Bottom · Problems | **Honest empty** | No LSP — explains and offers Open in Cursor |
| Bottom · Output | **Live** | Studio API request log from Agents panel |
| Bottom · Terminal | **Honest non-shell** | Copy `cd` + Open in Cursor — **no exec** |
| Bottom · Ports | **Configured links** | Not a scan; Simple Browser open |
| Status bar | **Live** | Path, mode, dirty, write label; EOL/encoding cosmetic |
| Command palette | **Live** | Ctrl+K / Ctrl+Shift+P |
| Go to file | **Live (partial)** | Ctrl+P over **loaded** entries — not full recursive index |
| Simple Browser | **Live** | Iframe preview tabs for http(s)/localhost |
| Find in file | **Browser Ctrl+F** | No in-editor find UI |
| Git / SSH / shell / LSP | **Out of scope** | Documented; Clone/SSH welcome = desktop bridge |

Welcome menu (pre-folder) is **inactive** by design (SSR: “Active once a folder is open”).

---

## 5. Capability matrix (browser × mode × features)

| Browser / setup | Open | Edit | Disk write | Absolute path | Notes |
|-----------------|------|------|------------|---------------|-------|
| Any + path-bridge `:4010` | Native dialog | Yes | Companion write | **Yes** | Preferred path |
| Chrome/Edge, no bridge | FSA | Yes | If write granted | Attach only | Recents via IndexedDB |
| Firefox/Safari, no bridge | webkitdirectory / drop | Yes | Download/zip | Attach only | Re-pick after reload |
| Installed PWA | Same as host browser | Same | Same | **Still needs bridge** | `shell-v2` offline |
| Desktop IDE + extension | Full IDE | Full | Full | Real | `odeiStudio.*` commands |

---

## 6. Known bugs history — current on-disk status

| Bug (history) | Was | Status 2026-07-31 |
|---------------|-----|-------------------|
| Hydration: capability string SSR vs client | `describeBrowserSupport()` / branching banner | **Fixed** — `useSyncExternalStore` + `useIsClientHydrated`; banner locked to `EDITOR_WELCOME_STATUS_BANNER` |
| Hydration: “real, read-only…” vs Cursor-like banner | Duplicate/divergent copy | **Fixed on disk** — single constant; live SSR shows Cursor-like string. If a tab still shows old text → hard refresh / clear old SW cache |
| `explorer.tsx` `accessMode is not defined` | Missing prop | **Fixed** — typed prop, destructured, passed from `EditorWindow` |
| SW cache-first `/_next/static` → stale bundles / phantom bugs | Old SW | **Fixed** — `sw.js` skips `/_next/`; cache name `odei-studio-shell-v2`; **dev unregisters all SWs** |
| `beforeinstallprompt.preventDefault()` console spam | Install handler deferred event | **Fixed** — InstallStudioPwa intentionally does **not** call `preventDefault` |

**No critical one-line regressions found in this pass** — no code change applied.

**Residual risk:** users with a **production-registered old SW** or a long-lived tab may still see stale hydration diffs until unregister / hard refresh. Dev mode actively clears registrations.

---

## 7. Extension / bridge commands

From `ODEI Studio/extensions/odei-studio/package.json` + `extension.ts`:

| Command | Role |
|---------|------|
| `odeiStudio.openStudioEditor` | Opens Studio web `/editor` |
| `odeiStudio.openAgents` | Opens `/app` |
| `odeiStudio.startPathBridge` | Runs `npm run path-bridge` in terminal |
| `odeiStudio.allowlistPathBridge` | Allowlists folder on companion |
| `odeiStudio.openProject` / `cloneRepo` / `connectSsh` | Desktop IDE open / clone / Remote-SSH |
| Config `odei.pathBridgeUrl` | Default `http://127.0.0.1:4010` |
| Config `odei.pathBridgeToken` | Matches `ODEI_PATH_BRIDGE_TOKEN` when companion requires auth |
| Config `odei.studioUrl` | Default `http://localhost:3002` |

---

## 8. Docs & status.json honesty

| Doc / artifact | Honesty check |
|----------------|---------------|
| `docs/STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md` | Accurate gap matrix; audited 2026-07-30 |
| `docs/STUDIO_EDITOR_WORKSPACE_VIEW.md` | Matches modes + chrome; not Code-OSS |
| `docs/STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md` | PWA ≠ paths; companion required |
| `docs/STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md` | Clone/SSH bridge phase |
| `docs/STUDIO_EDITOR_WINDOW_OPEN_CLONE_SSH_INVESTIGATION.md` | Notes prior “Soon stubs” claims as stale |
| `ODEI Studio/status.json` | Editor + path_bridge + PWA `unlocks_absolute_paths: false` — **honest** |
| `apps/studio/status.json` | Editor local_live; companion loopback; not full Cursor — **honest** |

No evidence that status files claim browser shell/Git/LSP or PWA-only absolute paths.

---

## 9. Security

| Control | Implementation |
|---------|----------------|
| Loopback-only bind | `listenBridge` refuses non-`127.0.0.1` / localhost; always binds `127.0.0.1` |
| Allowlist | In-memory roots after pick/resolve; `assertAllowed` on list/read/write |
| Traversal | `..` rejected; null bytes rejected; `path.resolve` absolute |
| Size limits | ~1.5 MB read/write |
| CORS | Studio `:3002` / `:5226` (+ `ODEI_PATH_BRIDGE_ORIGINS`) |
| Optional token | `ODEI_PATH_BRIDGE_TOKEN` / Bearer / `X-ODEI-Path-Bridge-Token` / sessionStorage / `NEXT_PUBLIC_ODEI_PATH_BRIDGE_TOKEN` / extension `odei.pathBridgeToken` — health reports `tokenRequired` honestly |
| Health unauthenticated | By design (PWA probe) — danger string + `tokenRequired` returned |
| Rename / delete | Phase 2b: `POST /v1/rename`, `DELETE /v1/entry` / `POST /v1/delete` under allowlist + realpath checks |
| Rate limit | Optional in-memory (~180/min); disable `ODEI_PATH_BRIDGE_RATE_LIMIT=0` |
| SW | Does not cache `/_next/*`; does not intercept `:4000` / `:4010` |
| Agents context | Folder name + optional path only — no file body to API |

**Remaining danger (documented):** any local process that can call `:4010` can use allowlisted roots until process exit — set a token in non-dev use.

---

## 10. Gap vs Cursor.com (summary)

**Closer than a marketing shell:** Explorer, tabs, dirty/save, Agents API panel, palette, Simple Browser, mode-honest banners, absolute paths via companion.

**Still far from Cursor.com:** no Code-OSS desktop fork, no Tab/AI billing features, no in-tab Git/SSH/shell/LSP, no multi-root, no recursive workspace index, Ports not a live scanner, Terminal never executes. Phase 2b shipped Monaco + companion rename/delete/token deepen — still not Cursor.com.

Chrome parity source of truth: `docs/STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`.  
**Full product capability** (desktop/PTY/Git/LSP/AI/marketplace/auth): `docs/STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`.

---

## 11. Risks / bugs remaining

1. **Token optional by default** on companion — set `ODEI_PATH_BRIDGE_TOKEN` (or `AUTO_TOKEN`) for shared machines; production-like auto-generates.
2. **webkitdirectory non-restorable** after reload — expected; easy to confuse with “broken recents.”
3. **Terminal copy still partially worded as “user-typed path”** in places — slightly behind path-bridge reality when companion supplied the path.
4. **Go to file = loaded entries only** — large trees incomplete until expanded.
5. **Stale client tabs / old SW** — residual hydration reports possible without hard refresh.
6. **Monaco without LSP** — Phase 2b text engine only; no IntelliSense / diagnostics host.
7. **Agents = template/orchestrator builds** — not Cursor Tab / vision LLM on pixels (`status.json` already says vision_in_build false).

---

## 12. Recommended next fixes (prioritized)

| P | Fix | Why |
|---|-----|-----|
| **P1** | Align Terminal / status copy so path-bridge-sourced paths aren’t described as “typed only” | Honesty polish |
| **P2** | Recursive (capped) go-to-file index for open workspace | Cursor Ctrl+P feel |
| **P2** | Optional production SW update banner (“New Studio version — refresh”) | Prevent stale-shell confusion |
| **P3** | Code-OSS / ODEI desktop IDE | Beyond Monaco-in-browser |
| **P3** | Opt-in companion command runner | High risk — defer; keep Terminal non-shell |

---

## 13. Verify checklist (manual)

1. Live: `:3002/editor` + `:4000/health` + `:4010/health` all 200; health shows `tokenRequired` + rename/delete in `apis`.  
2. `npm run path-bridge` → Open folder → absolute path + `path-bridge` → Ctrl+S writes (Monaco).  
3. Path-bridge Rename… / Delete… from Explorer → tree refreshes.  
4. Chrome without companion → FSA open → Save when write granted; path hidden until Attach.  
5. Firefox → webkitdirectory → Save downloads.  
6. Hard refresh welcome → no hydration mismatch; banner = `editor-copy` constant.  
7. DevTools → Application → confirm no SW caching `/_next` (or SW unregistered in dev).  
8. Extension: **ODEI: Open Studio Editor** / **Start Absolute Path Bridge** (+ `odei.pathBridgeToken` if required).

---

## Related

- [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) — **full Cursor.com / IDE product capability** (desktop, PTY, Git, LSP, AI, marketplace, auth) vs Studio today; architecture A–D; Phase 2c→3 roadmap  
- [`STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`](./STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md)  
- [`STUDIO_EDITOR_WORKSPACE_VIEW.md`](./STUDIO_EDITOR_WORKSPACE_VIEW.md)  
- [`STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md`](./STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md)  
- [`STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md`](./STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md)  
- [`STUDIO_EDITOR_PHASE_2B.md`](./STUDIO_EDITOR_PHASE_2B.md)  
- Canvases: `studio-editor-holistic-investigation.canvas.tsx` · `studio-cursor-full-parity-investigation.canvas.tsx`
