> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_CURSOR_DESIGN_PARITY.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_CURSOR_DESIGN_PARITY.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Cursor → ODEI Studio design parity (uploaded screenshots)

**Audited + UI remediations:** 2026-07-30 · **Editor Phase 2a implemented:** 2026-07-30  
**Browser workspace view:** landed 2026-07-30 — see
[`STUDIO_EDITOR_WORKSPACE_VIEW.md`](./STUDIO_EDITOR_WORKSPACE_VIEW.md)  
**Open/Clone/SSH deep dive:** 2026-07-30 (refreshed) — see
[`STUDIO_EDITOR_WINDOW_OPEN_CLONE_SSH_INVESTIGATION.md`](./STUDIO_EDITOR_WINDOW_OPEN_CLONE_SSH_INVESTIGATION.md)

## What the four screenshots are

They are **Cursor IDE / Agents Window** frames — the design reference for
ODEI Studio, not bugs in Studio itself.

| Shot | Cursor surface | Studio mapping |
|------|----------------|----------------|
| 1 | **Welcome** (Open / Clone / SSH + recent projects) — no folder loaded | **Implemented** at `/editor` — Live Open (FSA) + Bridge Clone/SSH panels, labeled recents |
| 2 / 4 | **Agents Home** — light theme, centered composer, left rail | **Implemented** at `/app` |
| 3 | **Loaded Editor Window** after **Open Project** — Explorer + tabs + Terminal + Agents + Simple Browser | **In-browser Cursor-like chrome** — path-bridge / FSA / webkitdirectory workspace with Explorer, tabs, palette, Simple Browser, Agents. Not Electron / Code-OSS. See [`STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`](./STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md) |

**Important distinction:** Screenshot 3 is Cursor’s **full** post–Open workbench. Studio after Open folder approximates the chrome (Explorer, tabs, bottom panel, Agents, palette, Simple Browser) with mode-honest edit/save — not Electron parity.

## Cursor affordances → Studio

| Cursor | Studio now |
|--------|------------|
| Left: New Agent, Automations, Customize, Repositories | Agents shell — New Agent live; Automations/Customize marked Soon |
| Home ▾ · Local | Header breadcrumbs |
| Composer: “Plan, Build, / for commands, @ for context” | Same placeholder |
| **+** attach | Uploads images via `POST /api/v1/uploads` (local validated) |
| Auto dropdown | Auto / Build / Plan |
| Microphone | Stub (planned Phase 2) |
| Plan New Idea ⇧Tab | Pill action |
| Light whitespace Agents chrome | Default Studio theme |
| Welcome Open / Clone / SSH + recent | `/editor` — Open **Live**; Clone/SSH **Bridge**; protocol/copy; labeled recents |
| Full Editor Window after Open Project | Browser: Cursor-like workspace (edit/save by mode). Desktop: Cursor/VS Code. Fork: Phase 2b+ |

## Uploads honesty

Images are **accepted and stored** under `ODEI Studio/.uploads/` after MIME +
magic-byte + 5 MB checks. Build responses list attachment metadata. Template
agents **do not yet consume image pixels** (no vision LLM). This is **not**
signed cloud object storage + malware scan — required before public production.

## Surfaces (website vs App)

| Surface | Local | Production |
|---------|-------|------------|
| Studio website | `http://localhost:5226/` | `https://studio.odeiafrica.com/` |
| Studio App (Agents) | `http://localhost:3002/app` | `https://app.studio.odeiafrica.com/app` |
| Editor Window | `http://localhost:3002/editor` | `https://app.studio.odeiafrica.com/editor` |
| Studio API | `http://localhost:4000/health` | (edge when deployed) |

## Still open (infra)

| Item | Status |
|------|--------|
| ODID JWT / server RBAC | Interim `ODEI_STUDIO_API_KEY` only |
| Studio+OPMS edge deploy | `hosting/deploy_studio_opms.sh` + compose scaffolding |
| Registry-driven URLs | `railForRegistry` + chat.js / interconnect rails expanded |
| Signed storage + scan | Local disk foundation only |
| Native ODEI desktop IDE | Phase 2b+; Phase 2a hands Clone/SSH (and optional Open path) to Cursor/VS Code. Browser Open folder is an editable workspace with honest limits (no shell/Git/LSP). |

## Files

- `apps/web/src/components/agents-shell.tsx`
- `apps/web/src/components/chat-input.tsx`
- `apps/web/src/app/app/page.tsx`
- `apps/web/src/app/editor/page.tsx`
- `apps/web/src/components/editor/*` (welcome + workspace window)
- `apps/web/src/app/page.tsx` (splash → website + `/app` + `/editor`)
- `packages/api/src/media-store.ts`
- `packages/api/src/index.ts`
- `ODEI Studio/status.json`
- `docs/STUDIO_EDITOR_WINDOW_OPEN_CLONE_SSH_INVESTIGATION.md`
- `docs/STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md`
- `docs/STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`
- `docs/STUDIO_EDITOR_WORKSPACE_VIEW.md`
