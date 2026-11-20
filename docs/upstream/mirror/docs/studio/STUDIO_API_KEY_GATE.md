> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_API_KEY_GATE.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_API_KEY_GATE.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Studio API key gate (`ODEI_STUDIO_API_KEY`)

Phase 1.5 interim auth — **not** production ODID JWT. When set on the Studio API process, all `/api/v1/*` routes require the same key via header.

## Local dev keys (placed)

```bash
ODEI_STUDIO_API_KEY=[REDACTED]
ODEI_AI_GATEWAY_TOKEN=[REDACTED]   # must match apps/ai/.env.local for ModelRouter
ODEI_AI_URL=http://localhost:5203
ODEI_AI_DEFAULT=true
```

Files:

| File | Purpose |
|------|---------|
| `ODEI Studio/.env.local` | Active local env (gitignored) |
| `ODEI Studio/.env.local.example` | Template — Studio + AI client keys |
| `ODEI Studio/.env.example` | Documented defaults |
| `apps/studio/studio-local-dev.json` | MAC localhost bootstrap |
| `apps/ai/.env.local` | AI gateway token (mutating routes) |

## One-command setup

```bash
npm run setup:ai-env          # apps/ai/.env.local + gateway token in secrets store
npm run setup:studio-env      # materializes ODEI Studio/.env.local
npm run dev:studio-api        # runs setup, then Studio API :4000
npm run dev:studio-all        # App :3002 + API :4000 + path-bridge :4010
npm run verify:studio-stack   # probes surfaces + 401/200 key gate
npm run verify:studio-ai-build # ModelRouter build + REQUIREMENTS.md AI section
```

## Enable on the API

The API loads `ODEI Studio/.env.local` automatically via `packages/api/src/load-env.ts`.

`GET /health` and `GET /` stay open so surfaces can probe auth mode (`auth: "api_key"` vs `"none"`).

## Clients must send the key

| Header | Value |
|--------|--------|
| `X-ODEI-Studio-Key` | Same value as `ODEI_STUDIO_API_KEY` |
| `Authorization` | `Bearer <same value>` |

## Where the key is supplied automatically

| Surface | How |
|---------|-----|
| **Studio App** `:3002/app` | `NEXT_PUBLIC_ODEI_STUDIO_API_KEY` from `.env.local` + session bootstrap |
| **Studio MAC** `:5226/admin/` | Auto from `studio-local-dev.json` when API reports `auth: api_key` |
| **curl** | `-H "X-ODEI-Studio-Key: [REDACTED LOCAL STUDIO API KEY]"` |

Manual override: Studio App header **API key** button (session-only).

## Honesty

- Unset key → localhost demo stays open (template builds, local uploads).
- Set key → 401 without header; not a claim of multi-tenant RBAC or ODID.
- The local key above is for **localhost Phase 1.5 only** — rotate before any non-local exposure.

## Related

- `docs/ai/ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md` (AI gateway consumer)
- `docs/studio/STUDIO_MODELROUTER_VERIFY.md` (CLI + UI verify, troubleshooting)
- `apps/studio/developers.html`
