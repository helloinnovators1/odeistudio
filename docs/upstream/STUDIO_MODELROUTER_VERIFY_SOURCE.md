> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_MODELROUTER_VERIFY.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/studio/STUDIO_MODELROUTER_VERIFY.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio — ModelRouter verify & UI (2026-08-30)

**Status:** **Verified end-to-end** — API + Agents UI artifact viewer  
**Products:** ODEI AI `:5203` (gateway) · ODEI Studio App `:3002/app` · Studio API `:4000`

Peers: [`HOW_TO_RUN_LOCAL.md`](../ops/HOW_TO_RUN_LOCAL.md) · [`STUDIO_LOCAL_DESK_COMMANDS.md`](STUDIO_LOCAL_DESK_COMMANDS.md) · [`STUDIO_API_KEY_GATE.md`](STUDIO_API_KEY_GATE.md)

---

## 1. What “verified” means

| Layer | Pass criteria |
|-------|----------------|
| **ODEI AI** | `POST /v1/complete` returns 200 with gateway token when `ODEI_AI_GATEWAY_TOKEN` is set |
| **Studio API** | `POST /api/v1/build` with `options.useAi: true` → `ai.honesty.label = ai_routed` |
| **Artifacts** | `REQUIREMENTS.md` content includes `## AI ModelRouter analysis` (and `ARCHITECTURE.md` may include a matching section) |
| **Agents UI** | After build, **REQUIREMENTS.md** opens in the artifact viewer with the AI section highlighted in green |

Template agents still generate base artifacts. AI enriches them — it does **not** replace the pipeline. Not Cursor Tab AI · not production multi-tenant LLM.

---

## 2. One-command CLI verify

From repo root (requires `:5203` + `:4000` listening):

```bash
npm run verify:studio-ai-build
```

Script: `tools/verify-studio-ai-build.mjs`

- Materializes `ODEI Studio/.env.local` via `npm run setup:studio-env`
- **Restarts Studio API `:4000`** so `ODEI_AI_GATEWAY_TOKEN` is loaded from `.env.local`
- Waits up to 90s for AI + Studio API health
- Probes `/v1/complete` with `ODEI_AI_GATEWAY_TOKEN`
- Runs build with `useAi: true`
- Asserts `ai_routed`, `honesty.aiInArtifacts`, and `## AI ModelRouter analysis` in `REQUIREMENTS.md`

**Stack probe (no build):**

```bash
npm run verify:studio-stack
```

---

## 3. Manual UI check

1. Start stack: `npm run dev:studio-all` (or `npm run dev:all` + ensure `:4000` is up).
2. Open **http://localhost:3002/app**
3. Ensure **Use AI ModelRouter on build** is checked (default **on** unless **Offline sim** local preference disables it).
4. Submit any goal in the composer.
5. After **Build Complete**:
   - Honesty banner shows **AI-routed**
   - **Generated Artifacts** lists files — click `REQUIREMENTS.md` (auto-selected)
   - Content viewer shows full markdown; **`## AI ModelRouter analysis`** appears at the bottom in a green highlight box
6. Footer shows: `npm run verify:studio-ai-build`

**Editor Agents panel** (`http://localhost:3002/editor` → Agents) uses the same `BuildResults` viewer.

---

## 4. Environment (local desk)

| Variable | Where | Purpose |
|----------|-------|---------|
| `ODEI_STUDIO_API_KEY` | `ODEI Studio/.env.local` | Studio API auth (`X-ODEI-Studio-Key`) |
| `ODEI_AI_GATEWAY_TOKEN` | `apps/ai/.env.local` **and** `ODEI Studio/.env.local` | **Must match** — AI mutating routes + Studio → AI forwarding |
| `ODEI_AI_URL` | `ODEI Studio/.env.local` | Default `http://localhost:5203` |
| `ODEI_AI_DEFAULT` | `ODEI Studio/.env.local` | `true` = builds default to AI unless `useAi: false` |
| `NEXT_PUBLIC_ODEI_STUDIO_API_KEY` | `ODEI Studio/.env.local` | Browser sends key on `:3002` |

Setup:

```bash
npm run setup:ai-env       # apps/ai/.env.local + gateway token in secrets store
npm run setup:studio-env   # ODEI Studio/.env.local from secrets store
npm run dev:studio-all     # App :3002 + API :4000 + path-bridge :4010
```

Restart Studio API after changing `.env.local` so `load-env.ts` picks up tokens.

Local dev keys (Phase 1.5 localhost only):

```
ODEI_STUDIO_API_KEY=odei-studio-local-desk-erms-suite-9
ODEI_AI_GATEWAY_TOKEN=odei-ai-local-desk-erms-suite-9   # or Command Center–generated token in both files
```

---

## 5. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Many `EADDRINUSE` on second `npm run dev` | Dev already running — use one terminal; [`STUDIO_LOCAL_DESK_COMMANDS.md`](STUDIO_LOCAL_DESK_COMMANDS.md) |
| `missing_token` / 401 on `/v1/complete` | Run `setup:ai-env` + `setup:studio-env`; restart `:4000` and `:5203` |
| `template_fallback` / no AI section | Enable ModelRouter toggle; disable **Offline sim** on `:5226/offline.html` |
| Verify timeout on AI probe | Ensure `:5203` is up; increase `ODEI_VERIFY_AI_TIMEOUT_MS=60000` |
| UI shows filenames only (old build) | Hard refresh `:3002/app` (Ctrl+Shift+R) — artifact **content viewer** shipped 2026-08-30 |
| `:4000` not reachable | `npm run dev:studio-api` or `npm run dev:studio-all` |

---

## 6. Code map

| Area | Path |
|------|------|
| Build AI injection | `ODEI Studio/packages/build/src/index.ts` → `appendAiSection()` |
| API route + AI client | `ODEI Studio/packages/api/src/index.ts`, `model-router.ts` |
| Shared build hook | `ODEI Studio/packages/shared` → `BuildOptions.aiCompletion` |
| Agents UI | `ODEI Studio/apps/web/src/lib/use-studio-build.ts` |
| Artifact viewer | `ODEI Studio/apps/web/src/components/build-results.tsx` |
| AI controls | `ODEI Studio/apps/web/src/components/ai-controls.tsx` |
| Verify script | `tools/verify-studio-ai-build.mjs` |
| Env materialize | `tools/setup-studio-env.mjs`, `apps/multi-ecosystem/api/secrets-store.mjs` |

---

## 7. Honesty

- `local_sim` completions are always available without provider keys.
- Frontier models appear as **planned** or **configured** in `/v1/models` — never claim production LLM hosting.
- ODEI AI and ODEI Studio remain **separate products**; Studio consumes AI via HTTP only.
