> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_WINDOW_OPEN_CLONE_SSH_INVESTIGATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_EDITOR_WINDOW_OPEN_CLONE_SSH_INVESTIGATION.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Studio Editor Window — Open / Clone / SSH investigation

**Audited:** 2026-07-30 (refresh after browser workspace view landed)  
**Phase 2a desktop bridge:** implemented 2026-07-30  
**Browser workspace view (Open → Explorer/tabs):** landed in-tree as of this audit  
**Workspace:** `e:\ODEI Multi Ecosystem`  
**Studio surface under review:** `http://localhost:3002/editor`

> Prior drafts of this file still described disabled **Soon** stubs and “no Explorer on `/editor`.” Those claims are **stale**. This rewrite matches current code under `ODEI Studio/apps/web` and `extensions/odei-studio`.

---

## Executive verdict

| Button | What happens on click today | Full Cursor-like IDE in the browser? |
|--------|-----------------------------|--------------------------------------|
| **Open project** | Opens an expandable panel: primary path is Chromium **Open folder…** (File System Access) → loads a real **read-only** workspace chrome (`EditorWindow`: Explorer, tabs, bottom panel, Agents). Secondary path: typed absolute path → `cursor://file/…` / `vscode://file/…`. | **Partial in-browser** — real folder browse/view only. Full IDE (write, shell, Git, LSP) remains desktop handoff. |
| **Clone repo** | Opens panel: validate Git URL → **Clone with Cursor/VS Code** (`cursor://vscode.git/clone?url=…`) and/or **Copy git clone**. No browser `git`. | **Desktop handoff only** (or paste command into a local shell). |
| **Connect via SSH** | Opens panel: user/host → **Open Remote in Cursor/VS Code** (`…://vscode-remote/ssh-remote+…/`) and/or **Copy SSH command**. | **Desktop handoff only** (Remote - SSH). |

**One-line product truth:** `/editor` is a Phase 2a **launcher + optional Chromium read-only workspace viewer**. It is not Electron, not Code-OSS, and not Cursor’s post–Open Project workbench.

Companion docs:

- [`STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md`](./STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md) — install + Windows tests for protocol/extension paths  
- [`STUDIO_EDITOR_WORKSPACE_VIEW.md`](./STUDIO_EDITOR_WORKSPACE_VIEW.md) — what the in-browser Explorer/tabs actually do  
- [`STUDIO_CURSOR_DESIGN_PARITY.md`](./STUDIO_CURSOR_DESIGN_PARITY.md) — screenshot → surface mapping  

---

## A. What Cursor desktop does (contrast)

### A.1 Open project

| Step | Mechanism |
|------|-----------|
| Trigger | Welcome **Open project** or **File → Open Folder** |
| OS bridge | Electron `dialog.showOpenDialog` / `vscode.window.showOpenDialog` |
| Result | Folder becomes workspace root of the full workbench |
| Surfaces | Explorer, editable tabs, Problems/Output/Terminal/Ports, status bar, Agents, extensions |

Requires privileged desktop host: native FS R/W, process spawn, integrated terminal.

### A.2 Clone repo

1. Prompt for remote URL.  
2. Choose local parent directory.  
3. Run local `git clone`.  
4. Open cloned folder as workspace (same outcome as Open).

### A.3 Connect via SSH

1. Prompt for host / `~/.ssh/config` alias.  
2. Local `ssh` + Remote-SSH extension.  
3. Workbench attaches to **remote** FS and shell.

### A.4 Capability matrix

| Capability | Cursor desktop | Browser `:3002/editor` today |
|------------|----------------|------------------------------|
| Native folder picker → absolute path | Yes | No — FSA hides absolute path; typed path only for handoff |
| Read local tree + open files | Yes | Yes (Chromium FSA, **read-only**, lazy listing) |
| Write / save / create files | Yes | No |
| Spawn `git` / `ssh` / shell | Yes | No |
| Integrated PTY terminal | Yes | No (Terminal tab is honesty UI + copy `cd`) |
| Language server / diagnostics | Yes | No |
| Remote-SSH workspace | Yes (with extension) | Protocol/copy handoff only |
| Agents | In-IDE panel | `/app` full Agents home; in-window Agents = Studio API template builds |

---

## B. Actual `/editor` architecture (current code)

### B.1 Route states

Source: `ODEI Studio/apps/web/src/app/editor/page.tsx`

```
workspace.root == null  →  <EditorWelcome />   (Open / Clone / SSH panels + recents)
workspace.root != null  →  <EditorWindow />    (Explorer / tabs / bottom / Agents)
```

Opening a folder calls `pickDirectory()` → `workspace.openWorkspace(handle)` and remembers a `browser` recent with `handle: true`. Closing returns to welcome.

### B.2 Surfaces (`ODEI Studio/status.json`)

| Surface | Local | Role (current) |
|---------|-------|----------------|
| Website | `:5226/` | Marketing, honesty, login shell |
| Agents | `:3002/app` | Cursor-inspired Agents workspace |
| Editor | `:3002/editor` | Welcome + Chromium read-only workspace view + Phase 2a desktop bridge |
| API | `:4000` | Builds, agents, uploads |

### B.3 Key modules

| Path | Role |
|------|------|
| `components/editor/editor-welcome.tsx` | Three action cards + panels |
| `components/editor/editor-window.tsx` | Loaded workspace chrome |
| `components/editor/editor-dialogs.tsx` | About + desktop bridge dialogs |
| `lib/fs-access.ts` | `showDirectoryPicker`, listing, file load, IndexedDB handles |
| `lib/use-workspace.ts` | Lazy tree, tabs, restore/close |
| `lib/desktop-bridge.ts` | `cursor://` / `vscode://` URI builders, recents |
| `extensions/odei-studio` | Native Open / Clone / SSH commands |

### B.4 Honesty labels (welcome)

| Control | Badge | Detail line |
|---------|-------|-------------|
| Open project | **Live** | Load a real folder here |
| Clone repo | **Bridge** | Git command + IDE clone UI |
| Connect via SSH | **Bridge** | Remote-SSH handoff |

Amber banner: open folder for read-only FSA workspace; Git/SSH/shells stay on desktop; Agents at `/app`.

Menu strip on welcome is decorative (`title="Active once a folder is open"`). After open, `MenuStrip` is functional with many items explicitly disabled and hinted.

---

## C. Per-action deep dive

### C.1 Open project

#### 1. What the UI button does today

- Click toggles the **open** panel (`selectPanel('open')`); default panel on load is already `'open'`.
- Enabled; not disabled; badge **Live**.
- Panel primary CTA: **Open folder…** → `onPickFolder` → Chromium directory picker (`mode: 'read'`). Busy state shows “Reading folder…”. Disabled when `!supportsPicker` (non-Chromium).
- On success: switches to `EditorWindow` (Explorer, tabs, bottom panel, Agents panel). Files read-only; absolute path never revealed by the browser.
- Secondary: absolute Windows path input + **Open in Cursor** / **Open in VS Code** / **Copy path** → `desktopFileUri(scheme, path)` → `window.location.href`.
- Recents: `handle` rows restore via IndexedDB; `path` rows launch Cursor and suggest opening the same folder in-browser.

#### 2. Browser path

| Mechanism | Used? |
|-----------|-------|
| File System Access `showDirectoryPicker` | Yes — primary Open path |
| IndexedDB directory handle persistence | Yes — restore after reload (may need permission re-grant) |
| `cursor://file/<path>` / `vscode://file/<path>` | Yes — typed absolute path handoff |
| Clipboard | Copy path / later `cd` from workspace |
| In-browser workspace chrome | Yes — `EditorWindow` |

#### 3. Desktop / extension path

- Command: **ODEI: Open Project** (`odeiStudio.openProject`)
- `vscode.window.showOpenDialog` (folders) → `vscode.openFolder`
- Also: **ODEI: Open Studio Editor** opens `studioUrl/editor` in the system browser

#### 4. vs Cursor

Cursor’s Open loads a **writable, process-capable** workbench immediately. Studio Open either (a) loads a **read-only browser viewer** of a real folder, or (b) deep-links into Cursor/VS Code for the real IDE.

#### 5. Hard limits without a bridge

- No absolute path from FSA  
- No write/save/create  
- No shell, Git, debugger, LSP  
- Firefox/Safari: no directory picker → Open folder disabled; desktop path still available  

#### 6. Windows test (Cursor installed)

1. `npm run dev:studio` → `http://localhost:3002/editor` in **Edge/Chrome**.  
2. **Open project** → **Open folder…** → pick `E:\ODEI Multi Ecosystem` → confirm Explorer lists children; open a `.md`/`.ts` tab; Terminal tab shows no PTY.  
3. Enter `E:\ODEI Multi Ecosystem` → **Open in Cursor** → accept protocol prompt.  
4. In Cursor: **ODEI: Open Project** → same folder via native picker.  
5. Reload `/editor` → **Reopen workspace** if prompted.

---

### C.2 Clone repo

#### 1. What the UI button does today

- Click toggles **clone** panel. Badge **Bridge**.
- Input: repository URL; validates via `validGitUrl` (https/ssh/git:// or `git@host:path`, no spaces).
- Shows quoted PowerShell-safe `git clone '…'` preview.
- Buttons: **Clone with Cursor** / **Clone with VS Code** (disabled until valid) → `gitCloneUri` → `window.location.href`.  
- **Copy git clone** always available for the displayed command.
- Copy does not clone; protocol depends on IDE Git URI handler. Honesty text: use **ODEI: Clone Repository** for reliable local clone; then reopen folder in browser if desired.

#### 2. Browser path

| Mechanism | Used? |
|-----------|-------|
| Run `git` in page | **No** |
| `cursor://vscode.git/clone?url=` / `vscode://…` | Yes |
| Clipboard `git clone '…'` | Yes |
| Cloud clone / OAuth workspace | **Not implemented** |

#### 3. Desktop / extension path

- **ODEI: Clone Repository** (`odeiStudio.cloneRepo`)
- Input URL → parent folder dialog → `spawn('git', ['clone', '--', url, target])` (no shell) → offer **Open** / **Open in New Window**
- Requires `git` on PATH; refuses if destination exists

#### 4. vs Cursor

Cursor clones then opens the folder as a full workspace. Studio web only **requests** clone UI or copies a command; extension performs real clone.

#### 5. Hard limits

Browsers cannot spawn Git, write arbitrary disk trees, or open SSH agent sockets for `git@` auth without a host process.

#### 6. Windows test

1. `git --version`.  
2. `/editor` → Clone → disposable HTTPS URL → **Copy git clone** → paste in PowerShell.  
3. Try **Clone with Cursor** (may or may not open IDE clone UI).  
4. Reliable: Cursor **ODEI: Clone Repository** → Open → optionally return to `/editor` and **Open folder…** on the clone.

---

### C.3 Connect via SSH

#### 1. What the UI button does today

- Click toggles **ssh** panel. Badge **Bridge**.
- Optional user + required host/alias (`host` or `host:port`; user alphanumeric/`.`/`_`/`-`).
- Preview: `ssh user@host`.
- **Open Remote in Cursor/VS Code** → `remoteSshUri` → e.g. `cursor://vscode-remote/ssh-remote+user%40host/`.  
- **Copy SSH command**.
- Explicit copy: browser is not the SSH client; FSA only reaches **local** folders.

#### 2. Browser path

| Mechanism | Used? |
|-----------|-------|
| Raw SSH / WebSSH relay | **No** |
| Remote-SSH custom protocol | Yes |
| Clipboard `ssh …` | Yes |

#### 3. Desktop / extension path

- **ODEI: Connect via SSH** (`odeiStudio.connectSsh`)
- If `ms-vscode-remote.remote-ssh` missing → warn + Open Extensions / Copy SSH command  
- Else `vscode-remote://ssh-remote+<target>/` via `openFolder(..., forceNewWindow: true)`  
- Fallback: quick-open Remote-SSH connect command or copy `ssh`

#### 4. vs Cursor

Cursor’s Connect via SSH attaches the workbench to the remote FS. Studio only hands off URI/command.

#### 5. Hard limits

No arbitrary outbound SSH from a sandboxed origin; no remote FS mount; keys/agent stay on the desktop host.

#### 6. Windows test

1. Install **Remote - SSH**; verify `ssh user@host` independently.  
2. `/editor` → SSH panel → **Open Remote in Cursor**.  
3. Reliable: **ODEI: Connect via SSH** → new remote window (or install/copy fallback).

---

## D. Workspace view status (landed)

**Landed** — not a stub plan. After **Open folder…**:

- Activity rail, Explorer (lazy expand, 1200 entry cap/dir), editor tabs  
- Text (≤ ~1.5 MB decode) + image object URLs; binary stub  
- Bottom: Problems / Output / Terminal / Ports — Terminal is **non-executing** honesty UI  
- Agents panel: Studio API template builds; folder **name** only as context  
- Menus: many items disabled with reasons; File → Open in Cursor / VS Code… opens bridge dialog  

Does **not** equal Cursor3 full Editor Window (no write, PTY, Git, LSP, Remote-SSH inside the tab).

See [`STUDIO_EDITOR_WORKSPACE_VIEW.md`](./STUDIO_EDITOR_WORKSPACE_VIEW.md).

---

## E. Viable paths (research — status)

| Path | Status |
|------|--------|
| Desktop bridge / extension + protocol URIs | **Shipped (Phase 2a)** |
| Chromium FSA read-only workspace view | **Shipped** (companion to 2a) |
| Local sidecar agent | Not shipped |
| Cloud clone / WebSSH relay | Explicitly not implemented |
| ODEI Code-OSS fork (`urlProtocol: odei-studio`) | Phase 2b+ |

---

## F. Related files

| Path | Relevance |
|------|-----------|
| `ODEI Studio/apps/web/src/app/editor/page.tsx` | Welcome ↔ workspace switch |
| `ODEI Studio/apps/web/src/components/editor/*` | Welcome, window, dialogs, Explorer, tabs |
| `ODEI Studio/apps/web/src/lib/{desktop-bridge,fs-access,use-workspace}.ts` | URIs, FSA, workspace state |
| `ODEI Studio/extensions/odei-studio/{package.json,src/extension.ts}` | Commands 0.2.0 |
| `ODEI Studio/status.json` | Ports + `editor_desktop_bridge` |
| `docs/STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md` | Install + E2E tests |
| `docs/STUDIO_CURSOR_DESIGN_PARITY.md` | Screenshot mapping |

**Canvas:** `canvases/studio-editor-open-clone-ssh.canvas.tsx` — **not present** in this workspace (no canvas update this pass).

---

## G. One-line for product

**Open project can load a real Chromium read-only Explorer/tabs workspace in `/editor`, while Clone and SSH remain honest Cursor/VS Code (and `odei-studio` extension) handoffs; a full ODEI desktop IDE remains Phase 2b+.**
