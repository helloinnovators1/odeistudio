# ODEI Studio Desktop Host

This is the native Windows/macOS/Linux host for the OIPTECH Core workbench. It provides real operating-system window controls, an isolated Chromium browser surface, a local Git bridge, and interactive PTY sessions.

## Prerequisites

- Node.js 22 or newer and npm 10+
- Git installed and available on PATH
- Windows: Visual Studio C++ build tools and Windows SDK for `node-pty`
- macOS: Xcode command-line tools
- Linux: make, Python and a C/C++ build toolchain

## Run

```sh
cd apps/desktop
npm install
npm run rebuild
npm start
```

By default the desktop host loads `https://zurios.vercel.app/odeistudio?window=ide`. For local web development set `ODEI_DESKTOP_URL=http://127.0.0.1:3002/?window=ide`.

## Native capabilities

- Native window minimize, maximize/restore and close via Electron `BrowserWindow`.
- Isolated Chromium `WebContentsView` for browser tabs. It accepts HTTP(S) only; popups are opened externally.
- Folder selection through the operating-system folder picker.
- Repository status, staged/unstaged diff, stage, unstage and commit. The selected folder must be the repository root. Git commands use argument arrays (never a shell), a bounded timeout, and a bounded output buffer.
- Up to four interactive PTY sessions, rooted in the selected workspace.

## Security boundaries

The web renderer receives a narrow `contextBridge` API. Node integration is disabled, context isolation and Chromium sandboxing are enabled, and IPC accepts only the top-level ODEI app route: `https://zurios.vercel.app/odeistudio/**` or the explicit localhost development origins. The Zuri OS root and sibling paths on the shared production origin are rejected, and arbitrary `ODEI_DESKTOP_URL` origins are not trusted. Embedded browser pages have no preload and no Node integration. Browser navigation is restricted to HTTP(S). Terminal commands execute with the current desktop user's permissions; only use this local desktop app with workspaces and commands you trust. The terminal is not exposed through the public ODEI web deployment.

Git commits use the user's configured Git identity and normal Git hooks. A commit can fail until `user.name` and `user.email` are configured in Git.

The web UI must call `window.odeiDesktop` to use these native features. In a normal browser session this API is absent; the web app must retain its honest browser-only fallback.
