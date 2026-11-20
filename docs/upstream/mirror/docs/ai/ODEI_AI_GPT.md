> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/ODEI_AI_GPT.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ai/ODEI_AI_GPT.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI GPT — Agent & App

Last updated: 2026-08-27

## Where the prior ChatGPT-like UI lived

The matching shell (sidebar New chat / Library / Projects / Recents, “Ready when you are.”, pill “Ask anything” composer, quick actions) was already implemented as **OPMS AI Copilot**:

| Item | Path / URL |
|------|------------|
| Source | `ODEI Pre-Sale Management System (OPMS)/frontend/src/pages/CopilotChatWorkspace.tsx` |
| Docs | `ODEI Pre-Sale Management System (OPMS)/docs/COPILOT.md` · library page `docs/pages/odei-pre-sale-management-system-opms-docs-copilot.html` |
| MAC route | `/admin/copilot` on OPMS Vite (`http://localhost:5173` when that product is running) |
| API | `/api/v1/copilot/*` |

ODEI GPT on AI (:5203) adapts that UX to ODEI AI design tokens and wires chat to the AI gateway.

## Surfaces (ODEI AI :5203)

| Surface | URL |
|---------|-----|
| GPT app | http://localhost:5203/gpt.html |
| Alias | http://localhost:5203/gpt/ · http://localhost:5203/app/gpt/ |
| Home CTA | http://localhost:5203/ → primary **Open ODEI GPT** |

## API

| Method | Path | Role |
|--------|------|------|
| GET | `/v1/gpt/sessions` | Recents |
| POST | `/v1/gpt/sessions` | Create empty session |
| DELETE | `/v1/gpt/sessions/{id}` | Delete session + messages |
| GET | `/v1/gpt/messages?session_id=` | Thread |
| POST | `/v1/gpt/ask` | `{ content, session_id? }` → user + assistant via `/v1/complete` path |
| GET | `/v1/gpt/projects` | local_sim project bookmarks (tools / OS / NOC / tenants) |

Durable store: `apps/ai/data/gpt-chats.json`.

## Honesty

- **Not ChatGPT** the OpenAI product; not OpenAI-owned branding or models-as-ODEI-live without keys.
- Default replies are **local_sim** through the ODEI AI ModelRouter with **conversational answers** (identity, help, ports, GoldCity, doc RAG excerpts) — not a routing-metadata stub. OpenAI/Anthropic only when `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (etc.) are configured.
- Module: `apps/ai/api/local-sim-completion.mjs` · smoke: `npm run smoke:local-sim-gpt`
- Voice / mic controls are stubs; file attach notes a filename into the prompt (not a live blob store).
- Adapted from OPMS Copilot UX patterns — independent product surface on ODEI AI.
