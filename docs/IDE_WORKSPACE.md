# ODEI Studio IDE Workspace

**Status:** initial Monaco workspace shell implemented; read-only companion-backed preview. Not a complete IDE or autonomous coding agent.

## Current frontend boundary

- Application: React 19 + TypeScript + Vite under `apps/web`.
- Editor: Monaco via `@monaco-editor/react`, opened with `readOnly: true`.
- Workspace source: the loopback-only `odei-companion` API. The user explicitly selects roots in the local companion and pairs with a one-time code.
- Explorer: builds a nested, collapsible directory/file tree from the already-authorized companion relative-path listing. Folders sort before files; filtering reveals matching paths and their ancestors; keyboard navigation supports Arrow Up/Down, Arrow Left/Right, Home and End. Tree construction rejects malformed relative paths and performs no additional filesystem access. Filesystem watching is not implemented.
- Tabs: multiple read-only files can be opened, activated and closed.
- Bottom panel: output/status messages, an honest no-LSP Problems surface and a disabled terminal explanation.
- Patch preview: an explicit editor action opens a proposed-content dialog and requests a live, SHA-256-checked unified diff from the local companion. It is preview-only; no local files are changed.
- NEXUS panel: UI shell only. It does not send prompts, invoke the cloud planning API, stream responses or run tools.

## NEXUS chat panel position

- Shortcut: `Command+I` on macOS and `Ctrl+I` on Windows/Linux toggles the NEXUS panel.
- Setting: Workspace Settings → NEXUS chat panel → Left side / Right side.
- Default: Right.
- Preference key: `odei.nexus.chatPanelSide` in browser local storage.
- Invalid or unavailable storage values safely fall back to Right. The selected side remains active in the current page session if browser storage is blocked.
- The chat panel can also be opened/closed using the NEXUS button in the title bar.

## Explicit capability boundaries

| Capability | Current status |
|---|---|
| Local companion connect and one-time pairing | Implemented in the existing read-only flow |
| Workspace selection and file listing | Implemented |
| Monaco source viewing | Implemented, read-only |
| Multiple open tabs | Implemented |
| NEXUS panel left/right preference | Implemented |
| Command+I / Ctrl+I toggle | Implemented |
| Authenticated chat and streaming | Not connected |
| Whole-codebase indexing / semantic retrieval | Not implemented |
| Agent orchestration / agents window | Not implemented in this shell |
| Live patch proposal and diff preview | Implemented for the active file; local companion re-reads the base and checks SHA-256; no writes |
| Proposal persistence, reviewer approval/rejection, safe apply and rollback | Not implemented |
| File writes, rename, delete, save | Disabled; companion remains read-only |
| Terminal / shell / command execution | Disabled |
| LSP diagnostics and test runner | Not connected |
| Git/SCM and preview server | Not connected |
| Cloud/background agents and CLI | Not implemented |
| Native Code-OSS/Electron desktop packaging | Not implemented |

The UI must not imply that a disabled capability is operational. The NEXUS composer is disabled until authenticated chat and authorization are integrated. The terminal does not execute browser commands. The Monaco editor cannot save to disk.

## Security and data handling

- Companion calls are loopback-only and initiated by a user gesture.
- Pairing credentials are held in React memory, not local storage.
- Disconnect clears the in-memory session and requests server-side revocation.
- The browser UI lists and reads files and may send a proposed replacement to the paired local companion for a bounded diff preview. The preview remains on the loopback companion; it is not sent to a cloud model.
- Do not enable editor writes by adding a browser-side fetch to an arbitrary path. A future patch service must use the server's handle-relative Windows and descriptor-relative POSIX path controls, validate content hashes/concurrent edits, require explicit review/approval and audit mutations atomically.
- A future terminal must be an isolated execution service with resource/network/filesystem policy, not a shell exposed from the browser.

## Next implementation dependencies

1. Connect a trusted ODID identity contract and tenant/project authorization to the browser session.
2. Implement authenticated NEXUS chat, durable streaming/reconnect and scoped read-only tools.
3. Extend preview to multi-file IDE review, persist proposals securely, require explicit approval, and implement safe atomic handle-relative apply/rollback.
4. Implement isolated command execution, diagnostics and tests.
5. Add recursive explorer, workspace persistence, file watching, Git integration and preview.
6. Build the full Agents Window, CLI, background and cloud-agent control planes.
7. Validate the complete desktop/companion flow on the user's Windows 10 build 18362 environment before claiming support.

## Hierarchical Explorer

The browser workspace builds a nested tree from the already-authorized relative-path listing. Directories render before files and are alphabetically/numerically sorted; folders can be collapsed, and a non-empty path filter expands matching ancestors automatically. The tree builder rejects malformed relative paths (absolute paths, empty segments, dot segments and backslash separators), resolves file/directory path collisions deterministically without emitting duplicate nodes, preserves the companion's file metadata, and performs no filesystem access. The UI remains read-only.

Unit coverage lives in `apps/web/src/workspace-tree.test.ts`; the Explorer integration is in `apps/web/src/App.tsx`.

## Verification

The preference and shortcut helpers have Vitest coverage. API/web CI [44803547712](https://github.com/helloinnovators1/odeistudio/actions/runs/44803547712) passed all six jobs on UI code commit `d6aa775abd516ea4aa308b43b224fac995c30b30`; the web job reported 9 Vitest tests passed and a successful TypeScript/Vite production build. Security CI on the later documentation head is still running CodeQL; dependency audits and secret scanning have passed.


Latest full API/web verification for the integrated workspace and project API is [44804291266](https://github.com/helloinnovators1/odeistudio/actions/runs/44804291266) on `5f0d390ae13a7df76fd6dc0de88ae32abf32f21b`: all six jobs passed, including 9 Vitest tests, Vite production build, four OS/Python matrix jobs and real MongoDB replica-set transaction integration. Security scan [44804305322](https://github.com/helloinnovators1/odeistudio/actions/runs/44804305322) completed successfully across all four jobs: CodeQL, Gitleaks, Python dependency audit and web dependency audit.

## Authenticated chat API integration status

The API now has an initial project-scoped, authenticated, read-only chat endpoint; see [NEXUS chat API](NEXUS_CHAT_API.md). The React composer is still disabled because this frontend has no ODID access-token acquisition/refresh integration or project identity selector. Do not enable it by asking users to paste bearer tokens into local storage. The next frontend increment must use the approved ODID browser authorization flow, keep access tokens in memory, bind selected project context through trusted membership APIs and display explicit cloud-data consent before sending file excerpts.
