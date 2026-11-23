> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_EDITOR_PHASE_2B.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_EDITOR_PHASE_2B.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Studio Editor — Phase 2b (companion deepen + Monaco)

**Shipped:** 2026-07-31  
**Surfaces:** `http://localhost:3002/editor` · companion `http://127.0.0.1:4010`  
**Code:** `ODEI Studio/packages/path-bridge` · `apps/web` Editor · extension `odei-studio`

## What Phase 2b is

| Area | Status |
|------|--------|
| Path-bridge token | Prefer `ODEI_PATH_BRIDGE_TOKEN`; health reports `tokenRequired` honestly; Studio prompts → `sessionStorage`; `NEXT_PUBLIC_ODEI_PATH_BRIDGE_TOKEN`; extension `odei.pathBridgeToken` |
| Rename / delete | `POST /v1/rename`, `DELETE /v1/entry` + `POST /v1/delete` — Explorer context menu works in **path-bridge** mode |
| Safer ops | Strict allowlist + realpath/junction hardening; size limits; optional in-memory rate limit; JSON `{ error, code }`; logs without file contents |
| Monaco | Text files use `@monaco-editor/react` (dynamic `ssr: false`); syntax by extension; line numbers; Ctrl+S; light Studio theme; images/binary unchanged |
| Not claimed | Still **not** full Cursor.com / Code-OSS / shell / Git / SSH / LSP |

## Token how-to

```powershell
# Companion
$env:ODEI_PATH_BRIDGE_TOKEN = "local-dev-secret"
npm run path-bridge
# or auto-generate once:
$env:ODEI_PATH_BRIDGE_AUTO_TOKEN = "1"
npm run path-bridge
```

| Client | Setting |
|--------|---------|
| Studio web (build) | `NEXT_PUBLIC_ODEI_PATH_BRIDGE_TOKEN` (legacy: `NEXT_PUBLIC_PATH_BRIDGE_TOKEN`) |
| Studio web (runtime) | Prompt stores `sessionStorage['odei-studio.path-bridge-token']` when `tokenRequired:true` |
| Extension | Settings → `odei.pathBridgeToken` |

`GET /health` remains public and returns `tokenRequired: true|false`. Loopback bind is still required — the token only stops casual localhost abuse.

## APIs added (path-bridge)

| Method | Path | Body / query |
|--------|------|----------------|
| `POST` | `/v1/rename` | `{ from, to }` absolute, under allowlist; rejects `..` |
| `DELETE` | `/v1/entry` | `?path=` + optional `recursive=1` |
| `POST` | `/v1/delete` | `{ path, recursive? }` |

Existing: pick / resolve / list / read / write / roots. Mutating + sensitive routes require Bearer / `X-ODEI-Path-Bridge-Token` when a token is configured.

## Monaco notes

- Package: `@monaco-editor/react` + `monaco-editor`
- Entry: `monaco-text-editor-dynamic.tsx` → `dynamic(..., { ssr: false })`
- Theme: `odei-studio-light` (vs light / `#f7f7f5` gutter cues)
- Models keyed `odei://workspace/<path>`; disposed on tab close / path change
- Save paths (path-bridge / FSA / download) unchanged — Monaco only replaces the textarea buffer UI

## Windows verify (rename / delete)

1. Start companion (+ optional token) and Studio web `:3002`
2. Open `http://localhost:3002/editor` → Open folder (absolute path)
3. Confirm `/health` JSON includes `tokenRequired` and `apis` containing `rename` / `delete`
4. Right-click a file → **Rename…** → tree refreshes; file on disk renamed
5. Right-click → **Delete…** → confirm → entry gone; refresh listing
6. Edit a `.ts` / `.md` file → Monaco highlights + Ctrl+S writes via companion

## Honesty

Phase 2b is **live** for companion deepen + Monaco. Studio remains a mode-honest browser workbench, not Cursor desktop.

## Related

- [`STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md`](./STUDIO_PWA_ABSOLUTE_PATH_ACCESS.md)  
- [`STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`](./STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md)  
- [`STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md`](./STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md)  
- [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md)  
- Package README: `ODEI Studio/packages/path-bridge/README.md`
