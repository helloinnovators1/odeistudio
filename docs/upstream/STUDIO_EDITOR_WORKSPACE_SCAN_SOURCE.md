> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_WORKSPACE_SCAN.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_EDITOR_WORKSPACE_SCAN.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Studio Editor workspace — scan verdict

**Date:** 2026-07-30  
**Claim (original):** Choosing a folder renders the full workspace interface (Explorer, tabs, bottom panel, Agents, status bar) with an honest non-executing Terminal.

## Verdict

| Claimed | Actual | Evidence |
|---------|--------|----------|
| Open folder → workspace UI | **Fully implemented** | `page.tsx` switches to `EditorWindow` when `workspace.root` is set |
| Explorer from real folder | **Yes** | FSA `DirectoryHandle` or webkitdirectory virtual tree |
| File tabs + viewer | **Yes** — now **editable** | `FileViewer` textarea; dirty tabs |
| Bottom panel | **Yes** | Problems / Output / Terminal · no shell / Ports |
| Agents composer | **Yes** — Studio API | `useStudioBuild`; name + optional path context only |
| Status bar | **Yes** | Mode chip, path attach, dirty count |
| Terminal honesty | **Yes** | No PTY; copy `cd` / bridge |
| “Chromium only” | **Superseded** | Firefox/Safari use `webkitdirectory` + drag-drop |
| Disk write | **Chrome/Edge FSA only** | `fsa-readwrite` + `createWritable`; others download/zip |
| Absolute path | **User-attached** | Bridge dialog → status / Explorer / URIs |
| Studio MAC `:35226` | **Typo** | Correct URL is `http://localhost:5226/admin/` |

## Access modes

`fsa-read` | `fsa-readwrite` | `webkitdirectory` | `path-bridge`

## Fixes in this pass

- Cross-browser open (FSA + webkitdirectory + drop)  
- Editable tabs; FSA Save / New file / New folder; webkitdirectory download + zip  
- Attach real path in bridge / status / Explorer  
- Honesty matrix in About dialog + docs  
- Clarified MAC port `:5226` (not `:35226`)

## Verify

- Admin: `http://localhost:5226/admin/` → 200 + `mac-studio.js`  
- Editor: `http://localhost:3002/editor` → Open folder in Chrome and Firefox  
- `npm run typecheck -w @odei/web` inside `ODEI Studio`
