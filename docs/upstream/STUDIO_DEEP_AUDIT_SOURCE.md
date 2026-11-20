> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_DEEP_AUDIT.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_DEEP_AUDIT.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio — deep holistic audit & remediations

**Audited + remediations applied:** 2026-07-30  
**Scope:** `ODEI Studio/` end-to-end, plus ecosystem hosting/auth/env gaps that
affect Studio and audience boundaries.

## Verdict

ODEI Studio is a **Phase 1.5 local MVP**: text goal (+ optional image refs) →
template artifacts via Express `:4000`, Next.js App on `:3002/app`. Marketing
and honesty live on the **Studio website** at `:5226`. Edge DNS/Caddy now
separate website (`studio.odeiafrica.com` → `:5226`) from App
(`app.studio.odeiafrica.com` → `:3002`).

Same-day remediations harden what can be fixed without inventing Identity +
object storage: local CORS, port-pinned `next start`, honesty banner, clearer
API-down errors, sidebar “planned” labels, `status.json`, and `dev:all` now
starts Studio API.

## Studio architecture (no omission)

| Layer | Path | Reality |
|-------|------|---------|
| Web UI | `apps/web` `@odei/web` | Next 15 on **3002**, Agents home at **`/app`** |
| Website | `apps/studio/` | Static shell on **5226** |
| API | `packages/api` `@odei/api` | Express on **4000**; open routes, local CORS |
| Build | `packages/build` | Template strings → in-memory `Map` |
| Orchestrator | `packages/orchestrator` | Deterministic task queue (no LLM) |
| Shared types | `packages/shared` | Goal = title + description + workspaceId |
| VS Code ext | `extensions/odei-studio` | Text goal → same API |
| Edge | Caddy/nginx/registry | Website → `:5226`; App → `:3002`; API `:4000` not proxied by default |
| Edge deploy | `deploy_edge.sh` | Does **not** sync or run `ODEI Studio/` |

### API routes

`GET /`, `/health`, `/api/v1/agents`, `POST /api/v1/goals/plan`,
`GET /api/v1/goals/:id/tasks`, `POST /api/v1/build`, `GET /api/v1/build/:id`,
`GET /api/v1/builds`. **No** multipart / upload / media routes.

### Uploads

Absent end-to-end: no `<input type=file>`, no FormData, no multer, no disk/S3,
no previews, no MIME validation. Probe artifact:
`ODEI Studio/studio-upload-probe.json`.

### Sidebar honesty

Only **Build** is live. Agents / Memory / Deploy / Security / Monitor / Docs /
Marketplace are Phase 2+ chrome (UI now labels them Planned).

## Remediations applied (this pass)

### Studio

- CORS allowlist for local Studio/gateway origins (`packages/api/src/index.ts`)
- Honesty fields on `GET /` and `/health` (`auth`, `persistence`, `uploads`)
- `next start -p 3002` port pin
- Dev banner + API-unreachable messaging in web UI
- Planned-tab labels in sidebar / mobile nav
- `ODEI Studio/status.json` machine-readable honesty
- `MVP_SCOPE.md` / `README.md` updated (uploads + sidebar out of scope)
- Root `dev_all.mjs` now starts **studio-api :4000** alongside studio web

### Hosting / env drift

- Caddy + nginx API upstream **8000 → 8002**
- CoinCore `:5224` + Membership `:5225` added to Caddy, nginx, `dns-records.csv`
- `deploy_edge.sh` header documents Studio/OPMS exclusion honestly

### Audience / roles

- Invite codes redeemable **only on localhost / data-odei-env=dev**
- All 26 `staff-invite.html` pages no longer print working codes
- `GET /v1/master-admin` returns emails only when `X-ODEI-Email` is a master
- `/v1/status` and `/v1/health` no longer expose master emails
- Public `status.html` Master tab redacted
- Static `/auth/master-admins.json` served **redacted** (emails/history stripped)
- `honesty.js` prefers `honesty.staff.json` for staff sessions (fallback to public)
- `interconnect.js` gains `railForRegistry()` + `isProdHost()` (opt-in migration)

## Still required for real production separation

1. Trusted ODID JWT + server RBAC on every protected route/API
2. Deploy manifests for Studio web+API, OPMS, and object storage
3. Registry-driven URLs replacing remaining localhost hardcodes (chat, membership API)
4. Remove bootstrap master emails from browser bundles after server claims exist
5. Studio media upload only after Identity + signed upload + scan + retention
6. Staging environment distinct from edge “same as local” shells

## Cross-links

- [`ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md`](ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md)
- [`STUDIO_UPLOADED_IMAGES_INVESTIGATION.md`](STUDIO_UPLOADED_IMAGES_INVESTIGATION.md)
- `ODEI Studio/status.json`
- Canvas: `studio-uploaded-images-investigation.canvas.tsx`
