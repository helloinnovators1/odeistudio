> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Studio Editor Phase 2a — desktop bridge

**Implemented:** 2026-07-30  
**Web surface:** `http://localhost:3002/editor`  
**Desktop host:** Cursor or VS Code with `extensions/odei-studio`

## What Phase 2a is

The Editor welcome is an honest launcher for capabilities that need a desktop
host, plus a **Chromium read-only workspace viewer** when the user picks a
folder via File System Access. It does not turn the browser into Electron or a
Code-OSS workbench. Workspace-view details:
[`STUDIO_EDITOR_WORKSPACE_VIEW.md`](./STUDIO_EDITOR_WORKSPACE_VIEW.md).

| Action | Web `/editor` | ODEI extension | Boundary |
|---|---|---|---|
| Open project | **Primary:** Chromium FSA `Open folder…` → editable `EditorWindow` (`fsa-read` / `fsa-readwrite`). **Fallback:** Firefox/Safari `webkitdirectory` + drag-drop (same chrome; Save = download / zip). **Also:** typed absolute path → `cursor://file/…` / `vscode://file/…`; recents in `localStorage` + IndexedDB FSA handles | Native `showOpenDialog`, then `vscode.openFolder` (normal IDE recents) | FSA write needs permission; webkitdirectory cannot silently write original paths; Terminal tab is non-executing |
| Clone repo | Validates common HTTPS/SSH Git URLs; copies a quoted `git clone` command; requests the IDE Git clone URI | Prompts for URL and parent folder, runs local `git clone`, then offers to open the clone | No browser-native Git; IDE URI support varies, so extension command is the reliable route |
| Connect via SSH | Builds/copies `ssh user@host`; requests a Cursor/VS Code Remote-SSH URI | Opens a `vscode-remote://ssh-remote+…` folder; offers Remote - SSH install/copy fallback | Browser is not an SSH client; remote filesystem editing needs Remote - SSH, local SSH and credentials |

The extension also adds **ODEI: Open Studio Editor** and **ODEI: Open Agents**.
Existing build-from-goal and agent-registry integration is unchanged.

## Install the extension on Windows

From the ecosystem root:

```powershell
cd ".\ODEI Studio"
npm install
npm run build -w odei-studio
cd ".\extensions\odei-studio"
npx @vscode/vsce package
cursor --install-extension .\odei-studio-0.2.0.vsix
```

Use `code --install-extension` for VS Code. If the CLI is unavailable, run
**Extensions: Install from VSIX…**. Development-host and junction instructions
are in [`../ODEI Studio/extensions/odei-studio/README.md`](../ODEI%20Studio/extensions/odei-studio/README.md).

Start the web surface:

```powershell
cd "E:\ODEI Multi Ecosystem"
npm run dev:studio
```

Open `http://localhost:3002/editor`.

## Windows end-to-end tests

### Open project

1. Install/reload the ODEI extension.
2. In Cursor, run **ODEI: Open Project**, choose a folder, and confirm it opens
   and appears in desktop recents.
3. On `/editor`, click **Open project**, enter an absolute path such as
   `E:\ODEI Multi Ecosystem`, then click **Open in Cursor**.
4. Accept the browser's external-protocol prompt. If no prompt appears, copy the
   path and use the extension command.
5. In Chromium, click **Open folder…**. Confirm the workspace view loads
   (Explorer + tabs). Recents should label the entry `browser` / `handle`.
   Absolute path remains hidden unless typed for desktop handoff.

### Clone repo

1. Ensure `git --version` succeeds.
2. On `/editor`, enter a disposable repository URL. Confirm invalid URLs are
   rejected and **Copy git clone** copies the displayed command.
3. Try **Clone with Cursor** and accept the external-protocol prompt. This
   depends on the installed IDE's bundled Git URI handler.
4. Reliable path: run **ODEI: Clone Repository** in Cursor, select a parent
   directory, wait for the ODEI output, and choose **Open**. Confirm the target
   folder exists and opens.

### Connect via SSH

1. Install Microsoft's **Remote - SSH** extension and verify the host works with
   `ssh user@host` independently.
2. On `/editor`, enter user and host. Copy the command and try **Open Remote in
   Cursor**.
3. Reliable path: run **ODEI: Connect via SSH**. Confirm a new
   `vscode-remote://` window opens. Without Remote - SSH, confirm the extension
   offers install instructions or copies the SSH command.

Use a test host and repository you are authorized to access. Credentials and
host-key decisions remain owned by Git, SSH, and the desktop IDE.

## Storage and security

- Browser recents are local to the current origin and browser profile. Seeded
  examples are visibly labeled and remain examples.
- No workspace path, Git URL, SSH target, key, or credential is sent to Studio
  API by this bridge.
- Custom protocols may be blocked by browser policy or unregistered if the IDE
  was installed without its protocol handler.
- The extension passes clone arguments directly to `git` without a shell.
- Studio API auth remains the optional `ODEI_STUDIO_API_KEY`; Phase 2a does not
  add ODID JWT.

## Explicitly not implemented

- A native Electron picker that returns an absolute path inside the browser
- Browser-writable FS, host shell/PTY, Git, SSH transport, or remote filesystem
- Language server / real Problems diagnostics in the browser workspace view
- A full Code-OSS/ODEI desktop binary (Phase 2b+)
- Cloud workspace sync, cloud cloning, or SSH relay
- Vision LLM or ODID JWT changes
