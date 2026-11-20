> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Studio PWA + Absolute Path Access

**Audited:** 2026-07-30  
**Surfaces:** `http://localhost:3002/editor` · companion `http://127.0.0.1:4010`

## Honesty first

| Claim | Reality |
|-------|---------|
| Installable PWA | Yes — manifest + service worker offline shell for `/editor` and `/app` |
| PWA unlocks OS absolute paths | **No** — browsers never expose path strings from `showDirectoryPicker` / `webkitdirectory` |
| Autonomous absolute paths | **Yes**, via the local **Absolute Path Companion** (`@odei/path-bridge` on **127.0.0.1:4010**) |
| Companion danger | Anything that can call localhost:4010 can use allowlisted roots — set `ODEI_PATH_BRIDGE_TOKEN` |

## Architecture

```
Studio Web / PWA (:3002)
    │  health probe
    ▼
Absolute Path Companion (:4010, 127.0.0.1 only)
    │  native folder dialog → allowlist root
    ▼
list / read / write under allowlisted roots
```

Open-folder fallback chain in the Editor:

1. **path-bridge** (if `/health` OK) → real absolute path + companion write  
2. **FSA** `showDirectoryPicker` (Chrome / Edge)  
3. **webkitdirectory** / drag-drop  
4. Manual path attach + Cursor/VS Code URI  

## Install the PWA (desktop)

1. Start Studio Web: `npm run dev:studio` (or `dev:studio-all`).  
2. Open `http://localhost:3002/editor`.  
3. Click **Install ODEI Studio**, or use the browser UI:

| Browser | How |
|---------|-----|
| Chrome / Edge | Address bar install icon, or ⋮ → **Install ODEI Studio** / **App available** |
| Firefox | ⋮ → **Install** when offered (desktop PWA support varies by version) |
| Safari (macOS) | **File → Add to Dock** or Share → **Add to Home Screen** |

PWA gives a standalone window and offline shell caching. It does **not** replace path-bridge.

## Start the Absolute Path Companion

From ecosystem root:

```powershell
npm run dev:studio-path-bridge
```

From `ODEI Studio`:

```powershell
npm run path-bridge
```

`npm run dev:studio-all` also starts the companion alongside App + API.  
`npm run dev:all` includes it as an **optional** service (`studio-path-bridge`).

Health:

```powershell
curl http://127.0.0.1:4010/health
```

Optional token:

```powershell
$env:ODEI_PATH_BRIDGE_TOKEN = "local-dev-secret"
npm run path-bridge
```

Store the same value as `NEXT_PUBLIC_ODEI_PATH_BRIDGE_TOKEN`, or let the Editor prompt and keep it in `sessionStorage['odei-studio.path-bridge-token']` when `/health` reports `tokenRequired:true`. Extension setting: `odei.pathBridgeToken`.

Phase 2b also adds companion **rename / delete** and Monaco text editing — see [`STUDIO_EDITOR_PHASE_2B.md`](./STUDIO_EDITOR_PHASE_2B.md).

## Windows verify (absolute path without typing)

1. `npm run path-bridge` in `ODEI Studio`  
2. `npm run dev:studio` (if not already)  
3. Open `http://localhost:3002/editor`  
4. Confirm the welcome panel says the companion is running  
5. Click **Open folder (absolute path)…** → native Windows folder dialog  
6. Explorer header + status bar show the **real** absolute path (e.g. `E:\…`) with access mode `path-bridge`  
7. Edit a text file → **Save** writes via `PUT /v1/write`

## Security controls

- Bind **127.0.0.1 only** (refuses non-loopback hosts)  
- In-memory allowlist after pick / `/v1/resolve`  
- Reject `..` traversal; realpath / junction escape hardening  
- ~1.5 MB read/write size limits  
- Optional token + basic in-memory rate limit  
- CORS limited to Studio origins (+ `ODEI_PATH_BRIDGE_ORIGINS`)  
- Logging without dumping file contents  

## Code map

| Path | Role |
|------|------|
| `ODEI Studio/packages/path-bridge/` | Companion HTTP server |
| `apps/web/src/lib/path-bridge-client.ts` | Browser client |
| `apps/web/src/lib/path-bridge-fs.ts` | FsHandle adapters |
| `apps/web/public/manifest.webmanifest` | PWA manifest |
| `apps/web/public/sw.js` | Offline shell SW |
| `extensions/odei-studio` | Start bridge / allowlist folder commands |

Related: [`STUDIO_EDITOR_WORKSPACE_VIEW.md`](./STUDIO_EDITOR_WORKSPACE_VIEW.md).
