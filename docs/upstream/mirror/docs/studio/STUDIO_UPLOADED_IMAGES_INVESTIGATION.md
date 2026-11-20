> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_UPLOADED_IMAGES_INVESTIGATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_UPLOADED_IMAGES_INVESTIGATION.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Studio (`:3002`) — uploaded-images investigation

**Audited:** 2026-07-30  
**Question:** What do the uploaded screenshots show, and how do they relate to
image upload on `http://localhost:3002`?

## One-line verdict

The four uploaded images are **Cursor IDE screenshots**, not ODEI Studio.
Studio on `:3002` has **no user image-upload path** (UI control, paste handler,
multipart API, storage, validation, or vision context). A live probe found
`input[type=file] = 0`, `<img> = 0`, paste of a PNG into the goal textarea
produced **no thumbnail / staged media**, and API `:4000` was down.

## Source assets examined

| # | Saved asset | What it actually is | Studio `:3002`? |
|---|-------------|---------------------|-----------------|
| 1 | `…images_Cursor1-….png` | Cursor Welcome / Recent projects | **No** |
| 2 | `…images_Cursor2-….png` | Cursor Agents Window — Home / Local composer | **No** |
| 3 | `…images_Cursor3-….png` | Cursor Editor Window — Explorer + Simple Browser + Terminal + Agents | **No** |
| 4 | `…images_Cursor4-….png` | Cursor Agents Window — Home / Local (second account) | **No** |

None of the four frames render `http://localhost:3002/`. They document the
**development IDE** used to work on the ecosystem, not Studio’s product UI.

## Image-by-image findings

### Image 1 — Cursor Welcome

- Window title: **Cursor [Administrator]**
- Actions: Open project · Clone repo · Connect via SSH
- Recent projects include **ODEI Multi Ecosystem**, **OPMS**, **ODEILHUB-Pay**,
  **GoldCity_Empire**, **ODEI Studio** on Desktop / Telegram Projects paths
- **No** Studio page, **no** uploaded media gallery, **no** file picker for
  Studio goals

### Image 2 — Cursor Agents (account `info.atlantisacc2@…`)

- Agents sidebar: New Agent, Automations, Customize
- Repositories: OPMS + **ODEI Multi Ecosystem** (“Holistic autonomous scan”)
- Composer: `+` · Auto · microphone · placeholder
  “Plan, Build, / for commands, @ for context”
- Footer: MCP configuration tip
- This `+` is **Cursor’s** attach/context control, **not** OMSG’s in-pill
  attach menu and **not** a Studio image uploader

### Image 3 — Cursor Editor on Desktop copy of the repo

- Explorer shows product folders including **ODEI Communications**
- Simple Browser: `http://localhost:5180/login.html?next=%2Fcomma` →
  **ERR_CONNECTION_REFUSED** (master shell not listening in that session)
- Terminal cwd: `C:\Users\Software Innovations\Desktop\ODEI Multi Ecosystem`
  (Desktop copy; this workspace is also present under `E:\ODEI Multi Ecosystem`)
- Agents chat shows paperclip + mic; payment-failed banner; Canvas widget
- **No** `:3002` tab; **no** Studio upload UI

### Image 4 — Cursor Agents (account `jasserroad902@…`)

- Same Agents Home / Local composer pattern as Image 2
- Two **ODEI Multi Ecosystem** repository rows
- Composer again: `+` · Auto · microphone — **no emoji**, **no Studio**

## What the screenshots imply for Studio media

| Affordance visible in Cursor images | Present in Studio `:3002`? |
| ----------------------------------- | -------------------------- |
| Composer `+` / paperclip attach | **No** — Studio has only title + description + send arrow |
| Microphone / voice | **No** |
| Paste image into composer → stage/preview | **No** — paste PNG left textarea text unchanged and created no thumb |
| Multipart upload to an API | **No** — Studio API uses `express.json()` only |
| Image gallery / `<img>` previews of user media | **No** — probe found zero `<img>` nodes |
| Auth gate before media | **N/A** — Studio has no auth at all |

Cursor’s attach controls are therefore a **reference UX**, not evidence that
Studio already implements uploads.

## Live Studio probe (same audit day; rechecked 2026-07-30)

```
GET http://127.0.0.1:3002/     → 200  ODEI Studio — AI-Native Development OS
GET http://127.0.0.1:4000/health → connection refused
input[type=file] count         → 0
document.querySelectorAll('img') → 0
paste PNG into goal textarea   → no staged image, no file input created
POST body shape                → JSON { goal: { title, description, … } }
```

Artifacts saved for operators:

- `ODEI Studio/studio-upload-probe.png`
- `ODEI Studio/studio-upload-probe.json`
- Earlier visual capture: `ODEI Studio/studio-current-audit.png`

## Code path (no omission)

1. `ODEI Studio/apps/web/src/components/chat-input.tsx`  
   Text-only form: description textarea + project-name input + submit.
2. `ODEI Studio/apps/web/src/app/page.tsx`  
   `fetch(API_URL + '/api/v1/build')` with JSON; default API
   `http://localhost:4000`.
3. `ODEI Studio/packages/api/src/index.ts`  
   `cors()` + `express.json()`; routes for health/agents/plan/build; **no**
   multipart / `/upload` / `/media`.
4. `ODEI Studio/packages/build`  
   In-memory `Map` of builds; template text artifacts under logical
   `generated/{slug}/{phase}/…` paths — not object storage.
5. Spec honesty: `ODEI Studio/docs/TECHNICAL_SPEC.md` §10 — no authentication;
   Phase 1 local-only; user-uploaded images documented as absent.

## Workspace path note from Image 3

The screenshot’s Desktop path and this Cursor workspace (`E:\…`) are **two
copies / locations** of Multi-Ecosystem work. Port probes and code edits in
this session target **`E:\ODEI Multi Ecosystem`**. If Desktop `:3002` / `:5180`
are started separately, they can diverge. Always confirm which folder owns the
process before diagnosing “uploaded images” or refused connections.

## Required Studio media architecture (not implemented)

Trusted claim → signed upload URL → MIME + magic-byte + size/dimension limits →
quarantine/scan → EXIF strip / safe re-encode → private object storage →
immutable metadata → approved media ID attached to goal/build → signed reads →
retention / delete / orphan cleanup → optional vision context. Until that
exists, do **not** claim Studio can accept uploaded images.

## Cross-links

- Canonical environment/audience/media audit:
  [`ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md`](ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md)
- Studio README / TECHNICAL_SPEC / ODEI_HOLISTIC_DOCUMENTATION (updated same day)
- Canvas:
  `canvases/studio-uploaded-images-investigation.canvas.tsx`
