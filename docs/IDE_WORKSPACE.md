# ODEI Studio IDE Workspace

**Status:** initial Monaco workspace shell implemented; read-only companion-backed preview. Not a complete IDE or autonomous coding agent.

## Current frontend boundary

- Application: React 19 + TypeScript + Vite under `apps/web`.
- Editor: Monaco via `@monaco-editor/react`, opened with `readOnly: true`.
- Workspace source: the loopback-only `odei-companion` API. The user explicitly selects roots in the local companion and pairs with a one-time code.
- Explorer: lists files in the selected workspace. The current companion response is rendered as a flat list; recursive tree navigation and filesystem watching are not implemented in this shell.
- Tabs: multiple read-only files can be opened, activated and closed.
- Bottom panel: output/status messages, an honest no-LSP Problems surface and a disabled terminal explanation.
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
| Patch proposal, diff review, accept/reject, rollback | Not implemented |
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
- The browser UI lists and reads files only. It does not upload workspace content to a cloud model.
- Do not enable editor writes by adding a browser-side fetch to an arbitrary path. A future patch service must use the server's handle-relative Windows and descriptor-relative POSIX path controls, validate content hashes/concurrent edits, require explicit review/approval and audit mutations atomically.
- A future terminal must be an isolated execution service with resource/network/filesystem policy, not a shell exposed from the browser.

## Next implementation dependencies

1. Connect a trusted ODID identity contract and tenant/project authorization to the browser session.
2. Implement authenticated NEXUS chat, durable streaming/reconnect and scoped read-only tools.
3. Implement patch proposals, diff review and safe atomic apply/rollback on the companion/backend.
4. Implement isolated command execution, diagnostics and tests.
5. Add recursive explorer, workspace persistence, file watching, Git integration and preview.
6. Build the full Agents Window, CLI, background and cloud-agent control planes.
7. Validate the complete desktop/companion flow on the user's Windows 10 build 18362 environment before claiming support.

## Verification

The preference and shortcut helpers have Vitest coverage. The web CI workflow runs tests and a production TypeScript/Vite build. Current-head verification must be read from the linked GitHub Actions run, not inferred from the presence of this document.
