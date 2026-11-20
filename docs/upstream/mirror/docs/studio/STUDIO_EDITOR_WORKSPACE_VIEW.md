> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_WORKSPACE_VIEW.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_EDITOR_WORKSPACE_VIEW.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Studio Editor — browser workspace view

**Audited:** 2026-07-30 (PWA + Absolute Path Companion)  
**Route:** `http://localhost:3002/editor`  
**Entry:** Open project → **Open folder…** (path-bridge preferred) or FSA / directory file input / drag-drop

This is the in-browser surface after a directory is granted to the page. It is
**not** Cursor’s full Editor Window and **not** a Code-OSS fork.

## Capability matrix

| Browser / mode | Open folder | Edit | Write to disk | Absolute path |
|----------------|-------------|------|---------------|---------------|
| Path companion (:4010) | Native dialog via bridge | Yes | Yes (`PUT /v1/write`) | **Real OS path** |
| Chrome / Edge FSA | FSA fallback | Yes | Yes (`createWritable`) | Hidden unless attached / companion |
| Firefox / Safari | `webkitdirectory` + drag-drop | Yes in tabs | Export / download only | User-attached / companion |
| Installable PWA | Same as browser | Same | Same | **Does not unlock paths alone** |
| Desktop IDE | Extension / URI | Full | Full | Real OS path |

## Access modes (`FolderAccessMode`)

| Mode | Meaning |
|------|---------|
| `path-bridge` | Absolute Path Companion — real OS path + allowlisted read/write |
| `fsa-read` | Chromium DirectoryHandle; write not granted |
| `fsa-readwrite` | Same + Save / New file / New folder write to disk |
| `webkitdirectory` | Virtual tree from file list; Save = download; Save All = zip |

## What is real

| Feature | Behavior |
|---------|----------|
| Folder pick | path-bridge → FSA `showDirectoryPicker` → `<input webkitdirectory>` / drop |
| Absolute path | Autonomous when companion healthy; else Attach path / Cursor URI |
| Explorer | Lazy listing; expand; icons; context menu (new/rename/delete where mode allows); refresh |
| Tabs | Multi-tab text edit; dirty `●`; drag reorder; truncated files stay view-only |
| Save | path-bridge write, else FSA `createWritable`, else download; Ctrl+S / Save All |
| Shortcuts | Ctrl+S, Ctrl+W, Ctrl+P (go to file), Ctrl+K / Ctrl+Shift+P (command palette) |
| Simple Browser | Iframe preview tabs for http(s) / localhost URLs (Ports panel or View menu) |
| PWA | Manifest + SW offline shell; Install ODEI Studio on welcome |
| Agents panel | Studio API template builds; New Agent + history; folder name + optional path — no file contents |
| Terminal | Honest non-shell (copy `cd` + Open in Cursor) — no PTY / no companion exec |

## What is not real

- PWA-only absolute path discovery  
- Silent disk writes on Firefox / Safari without path-bridge  
- Shell / PTY command execution in-tab  
- Git, SSH, language server  
- Full Cursor.com / Code-OSS binary  

Parity matrix: [`STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`](./STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md).

## Code map

| Module | Role |
|--------|------|
| `apps/web/src/app/editor/page.tsx` | Welcome ↔ `EditorWindow`; open chain |
| `apps/web/src/lib/path-bridge-client.ts` | Companion HTTP client |
| `apps/web/src/lib/path-bridge-fs.ts` | Bridge-backed FsHandles |
| `packages/path-bridge/` | Local companion server |
| `apps/web/src/lib/fs-access.ts` | FSA helpers + mode labels |
| `apps/web/src/lib/use-workspace.ts` | Tree, tabs, edit/save/export/preview |
| `apps/web/src/components/editor/command-palette.tsx` | Ctrl+K / Ctrl+P |
| `apps/web/src/components/editor/simple-browser.tsx` | Preview iframe tabs |

Related: [`STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md`](./STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md),
[`STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md`](./STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md),
[`STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`](./STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md).

## Verify

1. Companion: `npm run path-bridge` → Open folder → absolute path in status bar without typing.  
2. Chrome without companion: Open folder → FSA edit/Save; path hidden until attached.  
3. Firefox: Open folder → edit → Save downloads.  
4. Install PWA from welcome; confirm it does not claim path unlock.  
5. Studio MAC is **`http://localhost:5226/admin/`**.
