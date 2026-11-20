> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/studio/STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/studio/STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Studio ↔ Cursor Full Product Parity — Holistic Investigation

**Date:** 2026-07-31 (revalidated same day against Phase 2b/2c + Desktop scaffold)  
**Status:** Research revalidated — **Phase 2b + 2c shipped**; **Desktop Code-OSS = scaffold only** (`ODEI Studio/desktop/`) — **no** shipped IDE binary, **no** claim of full Cursor parity  
**Scope:** What ODEI would need to match **full Cursor.com / Cursor IDE product capability** (not UI chrome alone)  
**Workspace:** `e:\ODEI Multi Ecosystem`  
**Authority peers:** [`STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md`](./STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md) · [`STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`](./STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md) · [`STUDIO_EDITOR_PHASE_2B.md`](./STUDIO_EDITOR_PHASE_2B.md) · [`STUDIO_EDITOR_PHASE_2C.md`](./STUDIO_EDITOR_PHASE_2C.md) · [`STUDIO_DESKTOP_CODE_OSS_ROADMAP.md`](./STUDIO_DESKTOP_CODE_OSS_ROADMAP.md) · [`ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md`](./ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md) · [`ODEI_ECOSYSTEM_STACK_STRATEGY.md`](./ODEI_ECOSYSTEM_STACK_STRATEGY.md) · [`ODEI Studio/status.json`](../ODEI%20Studio/status.json) · [`apps/studio/status.json`](../apps/studio/status.json) · [`BUILD_ORDER_ROADMAP.md`](./BUILD_ORDER_ROADMAP.md) · Studio [`TECHNICAL_SPEC.md`](../ODEI%20Studio/docs/TECHNICAL_SPEC.md)

**Canvas (visual summary):** open beside chat → [`studio-cursor-full-parity-investigation.canvas.tsx`](/Users/Software%20Innovations/.cursor/projects/e-ODEI-Multi-Ecosystem/canvases/studio-cursor-full-parity-investigation.canvas.tsx).

---

## 0. Executive verdict (read this first)

### Does current architecture fully equal Cursor?

**No.** Still no — and Phase 2b/2c / Desktop scaffold do **not** change that verdict.

ODEI Studio today is a **hybrid of surfaces**:

| Surface | What it is | Port / host |
|---------|------------|-------------|
| Next App `/editor` + `/app` | Cursor-**like** browser chrome + Monaco (2b) + Agents templates | `:3002` |
| Absolute Path Companion | Loopback FS: pick/list/read/write/**rename/delete** + optional token (2b) | `127.0.0.1:4010` |
| Express Studio API | Template builds + ODEI AI ModelRouter consumer (`ODEI_AI_URL` → `:5203`) | `:4000` |
| `odei-studio` **0.3.0** | Phase **2c**: surfaces, status bar, path-bridge lifecycle, **host** Terminal/Git/Reveal; Open/Clone/SSH | Cursor / VS Code host |
| PWA | Installable shell only | Does **not** unlock OS paths |
| Desktop track | `ODEI Studio/desktop/` README + fetch stubs + `vscode/` branding / shallow `upstream` | **Scaffold only — no `.exe`** |

Cursor IDE is a **desktop Code-OSS-derived product** with first-class PTY, Git SCM, LSP/debug, native FS, Remote-SSH, extension host, proprietary AI (Tab, chat, rules, model routing), auth/billing/sync/updates. Studio’s browser workbench **intentionally does not** implement those layers; Phase 2a–2c document honesty, not parity. Extension 0.3.0 **reuses the host** for PTY/Git/LSP — that is **D progress**, not ODEI-owned IDE parity.

### Shipped vs still XL (revalidation 2026-07-31)

| Shipped (real) | Still XL / not owned by ODEI |
|----------------|------------------------------|
| Web `/editor` Monaco + path-bridge rename/delete/token (2b) | Shipped Code-OSS / Electron binary |
| Extension **0.3.0** host handoffs (Terminal/Git/SCM view/SSH URI) | In-browser PTY, Git SCM UI, LSP/DAP |
| Template Agents builds on `:4000` + optional AI route | Tab-quality FIM, indexing, org AI billing |
| Desktop **docs + script stubs** (`desktop/`, roadmap) | Compile → package → signed updater; Open VSX wiring |
| Honesty flags (`full_cursor_com: false`) | ODID + Pay seats + settings sync |

### Best path for ODEI (architecture letter)

**Recommended: C via D→C** — evidence unchanged. Official **Code-OSS / VSCodium-class fork** branded **ODEI Studio Desktop**, as a **separate product** from the Next web App (aligns with stack ADR “no all-Next”; desktop ≠ rewrite Studio to Electron-wrap-Next as the whole ecosystem).

**Near-term bridge (do not skip): keep A + deepen D AI; prepare C**

| Phase | Letter | Role |
|-------|--------|------|
| **2b / 2c DONE** | **A + D** | Honest browser Studio; `odei-studio` 0.3.0 on Cursor/VS Code for Git/SSH/PTY/LSP **via host** |
| **Next build slice** | **A + D** | **P0 done:** ModelRouter + rules + consented context via ODEI AI `:5203` — see [`ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`](./ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md); next = MCP (P1) |
| **Desktop (Phase 3)** | **C** | Own the binary when fork build/CI is reliable (`BUILD_ORDER`: “Extension-first until Code-OSS clone reliable”; `TECHNICAL_SPEC`: “Fork Code-OSS, not wrap it”) — scaffold exists, binary does not |
| **Reject as primary** | **B** | Electron shell around Studio web + ad-hoc `node-pty`/`git` — recreates a weak IDE without extension host / DAP / marketplace; high cost, low ceiling |
| **Never** | Clone Cursor proprietary | Tab model weights, Cursor billing, Cursor settings sync, Marketplace-ToS-violating redistribution of Microsoft-only bits |

### One-line product truth

> **Studio Web approximates Cursor chrome with mode-honest local edit; full Cursor-class capability requires an ODEI-owned Code-OSS desktop (C), approached via extension-first (D) while Web (A) stays the Agents + light editor surface.**

---

## 1. Method & sources

### 1.1 Checklist researched (user list)

1. Desktop IDE core — Code-OSS / Electron (or real VS Code fork), not only a website  
2. Real terminal — PTY process tied to the workspace  
3. Git SCM — status, diff, commit, branch UI  
4. LSP / IntelliSense / debug — language servers + debugger adapters  
5. Native FS — always real absolute paths (no FSA/webkitdirectory limits)  
6. Remote-SSH / multi-root — first-class remote workspaces  
7. AI parity — Tab completion, repo chat, rules, model routing (not template builds only)  
8. Extensions marketplace (or curated ODEI extension host)  
9. Auth, billing, sync, updates — matching Cursor **the product**, not just UI  

### 1.2 Documents & artifacts read

- `docs/STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md` (2026-07-31 live probe)  
- `docs/STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md` (chrome gap matrix)  
- `docs/STUDIO_EDITOR_PHASE_2B.md` (Monaco + companion rename/delete/token) — **shipped**  
- `docs/STUDIO_EDITOR_PHASE_2C.md` (extension deepen 0.3.0) — **shipped**  
- `docs/STUDIO_EDITOR_PHASE_2A_DESKTOP_BRIDGE.md`  
- `docs/STUDIO_DESKTOP_CODE_OSS_ROADMAP.md` + `ODEI Studio/desktop/` — **scaffold only**  
- `docs/ODEI_ECOSYSTEM_STACK_STRATEGY.md` (ADR: hybrid; Studio Next; desktop track parallel)  
- `ODEI Studio/status.json` + `apps/studio/status.json` (`full_cursor_com: false`; phase `1.5_with_editor_2c_extension` / `phase1_5_mac_wired_extension_2c_desktop_scaffold`; Desktop = `scaffold_only`, `shipped_binary: false`)  
- Path-bridge `server.ts` health `apis` (rename/delete); extension `package.json` 0.3.0 commands  
- Studio `TECHNICAL_SPEC.md`, `MVP_SCOPE.md`, `vscode/README.md`, `product.overrides.json`  
- `docs/BUILD_ORDER_ROADMAP.md` (Studio fork: extension-first)  
- Public license notes: Code-OSS **MIT** vs VS Code product license; Visual Studio Marketplace ToS **blocks non-Microsoft distributions**; Open VSX as fork-friendly registry  

### 1.3 Current Studio state (revalidated 2026-07-31)

```
Browser
  ├─ :3002/editor   Next workbench + Monaco (2b); honesty banners; no shell/Git/LSP
  ├─ :3002/app      Agents home (useStudioBuild → :4000 templates ± AI)
  ├─ PWA shell-v2   Offline chrome; paths still need :4010
  ├─ :4000          Express API — template builds + optional ODEI AI ModelRouter consumer
  ├─ :4010          path-bridge — absolute FS + token/rename/delete (2b); no PTY/git/LSP
  └─ :5203          ODEI AI gateway /v1/* (independent product)

Desktop host path (D — live)
  └─ Cursor / VS Code + odei-studio 0.3.0
        Surfaces / status bar / path-bridge start / ODEI AI health
        Host Terminal / Show Git / Reveal / Clone / SSH URI

Desktop product path (C — not shipped)
  └─ ODEI Studio/desktop/ + vscode/ branding + shallow upstream
        Docs + fetch stubs only — no odei-studio.exe
```

**Honesty already encoded in product:** both `status.json` files → `full_cursor_com: false`; `claims_cursor_tab_ai: false`; Desktop `shipped_binary: false`.

---

## 2. How Cursor / VS Code actually works (baseline)

Cursor ships a **desktop IDE** derived from the VS Code / Code-OSS architecture (Electron + Node + Chromium workbench), then layers **proprietary** AI, account, and product services. The open stack underneath (shared with VS Code / VSCodium-class forks) is what makes “real IDE” features possible:

| Layer | Mechanism |
|-------|-----------|
| **Shell** | Electron main + renderer; workbench UI in `src/vs/workbench` |
| **FS** | Node `fs` + file watcher; workspace folders are real OS paths |
| **Terminal** | `node-pty` (or equivalent) → OS PTY; cwd = workspace folder |
| **Git** | Built-in SCM + `git` CLI; diff/commit/branch/merge UI |
| **Languages** | Extension Host process; LSP clients talk to language servers |
| **Debug** | Debug Adapter Protocol (DAP) + UI |
| **Remote** | Remote-SSH / containers / WSL via **extension + local agent** (Microsoft Remote extensions are Marketplace-restricted) |
| **Extensions** | Extension host + gallery (VS Marketplace for official VS Code/Cursor family; forks typically **Open VSX** or private gallery) |
| **AI (Cursor-specific)** | Proprietary Tab / chat / Composer / rules / indexing / model routing / billing — **not** in Code-OSS |
| **Product ops** | Auth, subscription, settings sync, auto-update channels |

**Legal split (critical):**

| Asset | License / constraint |
|-------|----------------------|
| **Code-OSS** (`microsoft/vscode` repo source) | **MIT** — forkable (VSCodium, Cursor-class products, ODEI Studio Desktop) |
| **“Visual Studio Code” branded product** | Microsoft product license + telemetry/icons/marketplace wiring |
| **Visual Studio Marketplace** | ToS: **not** for alternative products / Code-OSS forks |
| **Many Microsoft extensions** (Remote-SSH, Pylance, C/C++, Live Share, …) | Licensed for Visual Studio family — **not** freely redistributable into a fork |
| **Cursor proprietary AI + billing** | Closed; **must not** be cloned or redistributed |
| **Open VSX** | Eclipse-hosted gallery suitable for forks |

---

## 3. Pillar-by-pillar analysis

Effort scale: **S** weeks · **M** ~1–2 months · **L** quarter+ · **XL** multi-quarter product (team + CI + ongoing rebase).

---

### Pillar 1 — Desktop IDE core (Code-OSS / Electron fork)

| | |
|--|--|
| **Cursor / VS Code** | Full Electron desktop workbench; native menus, windowing, multi-window, protocol handlers (`cursor://`, `vscode://`). |
| **ODEI today** | Next.js website/App (`:3002`); PWA chrome; **0.3.0** extension opens Studio URLs + host IDE; `ODEI Studio/desktop/` scaffold + `vscode/` branding + shallow `upstream` — **still not** a distributed `odei-studio.exe`. |
| **Gap** | No shipped desktop workbench; no Electron main process owned by ODEI; scaffold ≠ binary; web cannot become Code-OSS by adding CSS. |
| **Options** | **Extend A** — polish web only (never closes gap). **B** — Electron BrowserWindow wrapping `:3002` (shell only). **C** — Code-OSS/VSCodium fork (`product.overrides.json` + desktop roadmap). **D** — users run Cursor/VS Code; ODEI is extension + web (**0.3.0 live**). |
| **Effort** | A: — · B: **L** · C: **XL** (unchanged) · D: **S–M** (**2c done**; further AI deepen remains). |
| **License** | C: MIT Code-OSS OK; do **not** ship as “VS Code” or wire official Marketplace URLs. Preserve MIT notices. Cursor binary/IP: off-limits. |
| **Recommend** | **C for product ownership**; **D until C ships**. Do not treat B as the IDE. |

---

### Pillar 2 — Real terminal (PTY ↔ workspace)

| | |
|--|--|
| **Cursor / VS Code** | Integrated terminal: PTY, shells, cwd, split terminals, environment, tasks. |
| **ODEI today** | Web **Terminal** tab remains **honest non-shell**. Path-bridge still has **no** exec/PTY. Extension **0.3.0** `odeiStudio.openTerminalHere` opens the **host** integrated terminal (D reuse — not ODEI PTY). |
| **Gap** | No ODEI-owned process spawn / PTY / stdout in `/editor` or companion. |
| **Options** | Companion `node-pty` over WS (A deepen — **dangerous** on loopback). Electron/`node-pty` (B). Code-OSS terminal contrib (C — free with fork). Host terminal via D (**shipped handoff**). |
| **Effort** | Companion PTY: **M** + ongoing security. C/D: **included** in desktop host (D usable now). |
| **License** | `node-pty` / winpty OK; sandboxing is the hard part, not license. |
| **Recommend** | **Do not** add unconstrained command runner to `:4010`. Use **D now / C later** for real terminals. Optional later: allowlisted task runner with explicit user consent (still **L** security review). |

---

### Pillar 3 — Git SCM

| | |
|--|--|
| **Cursor / VS Code** | Source Control view: status, staged/unstaged diff, commit, branches, merge conflict UI, timeline. |
| **ODEI today** | No in-browser Git. Clone via URI / extension `odeiStudio.cloneRepo`. Extension **0.3.0** `odeiStudio.showGit` focuses **host** SCM view — status/diff/commit remain **host-owned**, not Studio Web UI. |
| **Gap** | Full SCM provider surface missing in web; ODEI does not own an SCM implementation. |
| **Options** | `isomorphic-git` in browser (partial, weak). Companion wrapping `git` CLI (A — **M**, fragile). Simple-git in Electron (B). Built-in SCM in Code-OSS (C). Host SCM (D). |
| **Effort** | Honest web Git UI: **L** and still incomplete. C/D: **included**. |
| **License** | Git CLI GPL is separate process OK; do not vendor GPL into ODEI license casually without review. |
| **Recommend** | **D/C**. Browser: keep clone bridge only; never fake a full SCM. |

---

### Pillar 4 — LSP / IntelliSense / debug

| | |
|--|--|
| **Cursor / VS Code** | Extension Host + LSP + DAP; Problems panel from real diagnostics; debug breakpoints/launch.json. |
| **ODEI today** | Monaco **syntax** highlighting only (Phase 2b). Problems = honest empty. Run/Debug activity = disabled. No language servers / DAP in web. On **D**, host Cursor/VS Code supplies LSP/DAP when the user installs language extensions — ODEI does not ship them. |
| **Gap** | Entire language intelligence + debugger stack **owned by ODEI** (web and future Desktop fork gallery). |
| **Options** | Monaco + LSP over WebSocket via companion (A — **XL**, reinvent extension host). Embed TS language service only (A — **M**, one language). Full extension host (C). Host provides LSP/DAP (D). |
| **Effort** | Multi-language LSP+DAP without Code-OSS: **XL**. C/D: leverage existing. |
| **License** | Language servers vary (Apache/MIT/proprietary). Microsoft Pylance etc. **not** for arbitrary forks via Marketplace. Prefer Pyright / community LS on Open VSX. |
| **Recommend** | **C or D**. Do not claim IntelliSense from Monaco alone. |

---

### Pillar 5 — Native FS (always absolute paths)

| | |
|--|--|
| **Cursor / VS Code** | Workspace = real paths; drag-drop; watchers; no FSA opacity. |
| **ODEI today** | **Best path (2b):** path-bridge → absolute paths + write/**rename/delete** + optional `ODEI_PATH_BRIDGE_TOKEN` / rate limit. Else FSA (hidden path) or webkitdirectory (ephemeral). PWA ≠ paths. Size caps; no recursive watcher. Host FS via D when using Cursor/VS Code. |
| **Gap** | Browser without companion cannot equal native FS. Companion is allowlist-based, not multi-root workspace service; no chokidar-class watch API in product UI. |
| **Options** | Deepen bridge (watch, larger files, multi-root allowlist) — **M**. Electron `fs` (B). Code-OSS FS (C). Host FS (D). |
| **Effort** | Bridge deepen: **M**. Full native always-on: **C** (or D host). |
| **License** | Companion is ODEI MIT-style code; keep loopback + token. |
| **Recommend** | Keep path-bridge for **Web honesty**. For “always native paths,” ship **C** (or use D). |

---

### Pillar 6 — Remote-SSH / multi-root

| | |
|--|--|
| **Cursor / VS Code** | Multi-root `.code-workspace`; Remote-SSH / WSL / containers as first-class window modes. |
| **ODEI today** | Single folder root in browser. SSH = copy command + `vscode-remote://` / extension `odeiStudio.connectSsh`. Depends on **Microsoft Remote - SSH** (or Cursor’s remote stack) on host — **not** reimplemented in Studio. |
| **Gap** | No remote FS relay in browser; no ODEI-owned remote agent; no multi-root editor model. |
| **Options** | SSHFS-ish companion (A — **XL**, insecure by default). Reimplement remote agent (C — **XL**, and **cannot** ship ms-vscode-remote from Marketplace into fork). D: rely on host Remote-SSH. |
| **Effort** | True remote: **XL**. Multi-root local in web: **M**. |
| **License** | **Critical:** Microsoft Remote Development extensions are **not** licensed for arbitrary Code-OSS forks via Marketplace. Forks need OpenSSH + community remote, Cursor-host (D), or a **from-scratch** remote agent. |
| **Recommend** | **Near-term: D** (extension SSH URI already live). **C** later with Open VSX / own remote story — budget legal review. Never promise “Remote-SSH identical to VS Code Marketplace” inside a fork. |

---

### Pillar 7 — AI parity (Tab, repo chat, rules, model routing)

| | |
|--|--|
| **Cursor** | Tab completions, repo-aware chat/Composer, project rules, model picker/routing, indexing, privacy modes, usage metering — **product cloud**. |
| **ODEI today** | Agents panel / `/app`: `useStudioBuild` → **template** orchestrator on `:4000`; workspace context = **folder name + optional path only** (no file bodies). Uploads local; `vision_in_build: false`. Extension 0.3.0: build-from-goal + **Copy Goal for Host Chat** + `odei.modelRouterUrl` **stub** (probe only). No Tab, no rules engine, no live ModelRouter, no billing meters. |
| **Gap** | Almost entire AI product layer. Differentiator opportunity: **ODEI Build / agents / African fintech goals** — not cloning Cursor Tab UX pixel-for-pixel. |
| **Options** | ModelRouter + context engine on Studio API (A/D shared backend) — **L**. Embed in fork workbench (C) — **L–XL**. Wrap Cursor AI — **illegal / ToS**. |
| **Effort** | Honest LLM chat + rules + routing: **L**. Tab-quality FIM + index: **XL**. |
| **License** | Use licensed model APIs (OpenAI/Anthropic/etc.) or future ODEI Models; never scrape Cursor. Rules files can be ODEI-defined (e.g. `.odei/rules`) — original IP. |
| **Recommend** | **Build ODEI AI on `:4000` + extension/webview** (D then C). **Never** claim Cursor Tab parity. Priority: real LLM plan/build + optional repo context with user consent — not template-only forever. |

---

### Pillar 8 — Extensions marketplace / extension host

| | |
|--|--|
| **Cursor / VS Code** | Full extension host; gallery install; activation events; proposed APIs allowlist. |
| **ODEI today** | One extension (`odei-studio` **0.3.0** VSIX) sideloaded into Cursor/VS Code — deepened surfaces/status/host commands. Browser Extensions rail disabled. Desktop scaffold docs mention bundling into upstream — **no** public gallery, **no** shipped fork host. |
| **Gap** | No ODEI gallery; no extension host in web; fork would need Open VSX or private registry + `product.json` gallery URLs. |
| **Options** | Curated VSIX bundle (C — **M**). Open VSX pointer (C — **M**). Private ODEI gallery (C — **L**). Stay on D and use host marketplace (**S**, but Cursor/VS Code ToS/product rules apply to that host). |
| **Effort** | Host reuse: **S** (done for ODEI bridge). Own gallery: **L**. |
| **License** | **Do not** point a fork at `marketplace.visualstudio.com`. Use Open VSX or self-hosted. Sideload MIT extensions OK. |
| **Recommend** | **D now (0.3.0)**; **C + Open VSX / curated bundle** when Desktop ships. |

---

### Pillar 9 — Auth, billing, sync, updates

| | |
|--|--|
| **Cursor** | Accounts, plans, usage limits, settings sync, auto-update, device trust. |
| **ODEI today** | Optional `ODEI_STUDIO_API_KEY` / path-bridge token; no ODID JWT on Studio App; uploads local; no subscription billing; no settings sync; Next/PWA update = refresh/SW (shell-v2); no IDE auto-updater. Ecosystem Identity (ODID) is **build-order P0–P1** but not wired to Studio editor. |
| **Gap** | Full product ops plane. |
| **Options** | Wire ODID + Pay for Studio seats (ecosystem rails) — **L**. Electron auto-updater / Code-OSS update channel (C — **L**). Settings sync service — **L**. |
| **Effort** | MVP auth: **M**. Billing+sync+updates: **L–XL**. |
| **License** | Use ODEI Identity/Pay; do not impersonate Cursor accounts. |
| **Recommend** | Align Studio product auth with **ODID** when Identity ships; Desktop updates via signed releases (C). Web stays cookie/JWT to API. **Never** fake sync. |

---

## 4. Pillar summary matrix

| # | Pillar | Have (ODEI) — revalidated | Need for Cursor-class | Effort | Best vehicle |
|---|--------|----------------------------|------------------------|--------|--------------|
| 1 | Desktop IDE core | Next + PWA + **desktop/ scaffold** + vscode scripts — **no binary** | Shipped Code-OSS binary | **XL** | **C** |
| 2 | Real terminal / PTY | Web: honest non-shell; **D:** host Terminal via 0.3.0 | ODEI-owned PTY ↔ cwd (or keep D) | **L**\* | **C/D** |
| 3 | Git SCM | Clone + **D:** Show Git (host SCM) | In-product status/diff/commit (owned) | **L**\* | **C/D** |
| 4 | LSP / debug | Monaco syntax; **D:** host LSP if installed | ODEI LS + DAP + Problems | **XL**\* | **C/D** |
| 5 | Native FS | path-bridge **token/rename/delete** (2b) / FSA / webkit | Always absolute + watchers | **M–L** | Bridge→**C** |
| 6 | Remote-SSH / multi-root | URI + extension SSH handoff (2c) | First-class remote + multi-root | **XL** | **D** then **C**\* |
| 7 | AI parity | Template Agents + ModelRouter **stub** | Chat/rules/routing (+ Tab optional) | **L–XL** | API + **D/C** |
| 8 | Extensions | **0.3.0** sideload VSIX (deepened) | Host + Open VSX/curated gallery | **M–L** | **D** / Open VSX on **C** |
| 9 | Auth / billing / sync / updates | Optional API keys + bridge token | ODID + Pay + updater + sync | **L–XL** | Ecosystem + **C** |

\*Effort collapses if adopting C/D (reuse host), vs reinventing on A/B. **D host reuse is live for 2–4/6/8; ODEI still does not own those layers.**

---

## 5. Architecture options comparison

### A — Stay browser + companion + extension (current)

```
Next :3002  ←→  path-bridge :4010
     ↓
API :4000 (Agents)
     ↓
odei-studio 0.3.0 → Cursor/VS Code (host Terminal/Git/LSP + surfaces)
```

| Pros | Cons |
|------|------|
| Already shipped (2b/2c); honesty model strong | **Cannot** reach full Cursor capability alone |
| Fits stack ADR (Studio stays Next) | FSA/webkit limits forever without companion |
| Low legal risk | PTY/Git/LSP in-browser = security/complexity trap |

**Fit:** Permanent **Web Agents + light editor** lane — not the path to IDE parity.

### B — Electron shell wrapping Studio web + node-pty + git

| Pros | Cons |
|------|------|
| Absolute paths + PTY + simple git without full fork | No real extension host / DAP / marketplace |
| Reuses Next UI | Dual maintenance (Electron + Next) |
| Feels “desktop” quickly | **Reinvents** VS Code poorly; dead-end vs C |

**Fit:** **Reject as primary.** Optional thin installer that only starts path-bridge + opens browser is OK — that is **not** B-as-IDE.

### C — Official Code-OSS / VSCodium-class fork (ODEI Studio Desktop)

| Pros | Cons |
|------|------|
| Only path to true IDE-layer parity | **XL** build (8–16GB RAM, hours compile, rebase forever) |
| Matches `TECHNICAL_SPEC` + existing `vscode/` branding | Marketplace ToS → Open VSX / curated only |
| Separate product — **does not** force ecosystem onto Next | Remote-SSH parity hard without MS extensions |
| Can bundle `odei-studio` + ODEI theme | Team must own security updates |

**Fit:** **Recommended end-state** for “match Cursor **editor** capability.” AI/billing remain ODEI-built (not Cursor clones).

### D — Cursor / VS Code as host + deep `odei-studio` extension (no fork)

| Pros | Cons |
|------|------|
| Instant PTY/Git/LSP/Remote via host | ODEI does **not** own the IDE binary |
| Extension-first matches build-order | Cursor product changes can break UX |
| Best ROI for AI features on `:4000` | Two brands in user’s face (Cursor + ODEI) |
| **0.3.0 Phase 2c shipped** | Cannot ship “ODEI Studio IDE” as `.exe` |

**Fit:** **Recommended near-term path (2c done)** and permanent option for users who already live in Cursor; next D deepen = ODEI AI on `:4000`, not more host chrome.

### Scorecard (Cursor-class capability / team fit / legal safety / ADR fit)

Scores 1–5; weights: capability 4, team 4, legal 3, ADR 3 (max 70).

| Criterion | A | B | C | D |
|-----------|:-:|:-:|:-:|:-:|
| Cursor-class editor capability (4) | 1 | 2 | **5** | 4 |
| ODEI AI product leverage (3) | 3 | 3 | **4** | **5** |
| Team / time cost (4) | **5** | 2 | 1 | **4** |
| Legal / marketplace safety (3) | **5** | 4 | 3 | **4** |
| Stack ADR alignment (3) | **5** | 2 | **5** | **5** |
| **Weighted (~70)** | **~52** | **~35** | **~52** | **~61** |

**Interpretation (revalidated post-2c):**

- **D wins near-term ROI** (weighted) — and **0.3.0 is now live** for host Terminal/Git/SSH/surfaces.  
- **C** remains the **only** option that owns a Cursor-class **editor binary**; Desktop folder is scaffold, not progress past XL compile.  
- **Recommendation letter unchanged: C via D→C**, with **A retained** for web. Next product slice on D = **ModelRouter**, not more IDE chrome.  
- **B loses.** Phase 2b/2c evidence does **not** flip “equals Cursor” to yes.

---

## 6. Phased roadmap (aligned with stack ADR)

Does **not** contradict [`ODEI_ECOSYSTEM_STACK_STRATEGY.md`](./ODEI_ECOSYSTEM_STACK_STRATEGY.md): Studio App stays **Next**; desktop is **parallel Studio-owned product**; no ecosystem-wide Next; no “PWA unlocks paths.”

```
Phase 2b (DONE)     Companion deepen + Monaco
        ↓
Phase 2c (DONE)     Web honesty polish + extension/AI deepen (A+D) — odei-studio 0.3.0
        ↓
Phase 3 Desktop     Code-OSS ODEI Studio Desktop MVP (C) — scaffold started; no binary
        ↓
Phase 3+            ODID/Pay/updater + Open VSX + ODEI AI in workbench
```

### Phase 2b — Done (do not re-claim as Cursor)

- Path-bridge token, rename/delete, rate limit, Monaco text engine.  
- Still not shell/Git/LSP/SSH/Tab.  
- Doc: [`STUDIO_EDITOR_PHASE_2B.md`](./STUDIO_EDITOR_PHASE_2B.md).

### Phase 2c — Browser + extension deepen (A + D) — **implemented 2026-07-31**

| Track | Work | Status |
|-------|------|--------|
| Web honesty | Terminal/status copy distinguishes path-bridge vs attached paths; About matrix notes Desktop scaffold | **Done** |
| Extension deepen | Status bar health; surfaces tree/webview; host Terminal/Git/Reveal; path-bridge lifecycle; VSIX 0.3.0 | **Done** — [`STUDIO_EDITOR_PHASE_2C.md`](./STUDIO_EDITOR_PHASE_2C.md) |
| AI (ODEI-owned) | ModelRouter on `:4000` | **Stub only** (`odei.modelRouterUrl`); template `/api/v1/build` + host-chat paste |
| Explicit non-goals | No companion PTY; no fake LSP; no Cursor Tab clone | **Honored** |

### Phase 3 — ODEI Studio Desktop (C) — **scaffold started**

Docs + script stubs under `ODEI Studio/desktop/` and [`STUDIO_DESKTOP_CODE_OSS_ROADMAP.md`](./STUDIO_DESKTOP_CODE_OSS_ROADMAP.md). **No shipped binary.**

| Milestone | Deliverable | Status |
|-----------|-------------|--------|
| 3.0 | Reliable `vscode:setup` → compile → launch on Windows CI (16GB) | **Not done** (XL) |
| 3.1 | Branding + bundled extension/theme | Overrides exist; binary not shipped |
| 3.2 | Open VSX / curated VSIX | Documented only |
| 3.3 | Wire Desktop to Studio API | Planned |
| 3.4 | Auto-update + ODID | Planned |

**Web `/editor` remains** the lightweight / PWA / remote-browser surface — not deleted, not required to equal Desktop.

### What to build next vs never clone

| Build next (ODEI) | Never clone from Cursor proprietary |
|-------------------|-------------------------------------|
| **Next slice:** MCP under ODEI AI (P1); deepen Desktop when CI ready | Cursor Tab weights / completion service |
| Desktop 3.0 only when Windows compile/CI reliable (scaffold ready) | Cursor billing/subscription backend |
| Open VSX / curated extensions (with C) | Cursor settings sync protocol |
| ODID + Pay seats when Identity/Pay ready | VS Marketplace URLs inside a fork |
| Honesty banners forever | Microsoft Remote-SSH binaries into fork without license |
| Keep A web lane; do not implement Code-OSS binary in this investigation | Marketing claims of “full Cursor.com” on `:3002` |

---

## 7. Stack ADR cross-check

| ADR statement | This investigation |
|---------------|-------------------|
| Do not standardize ecosystem on Next | Desktop = separate Code-OSS product; shells stay static/Vite |
| Studio App stays Next | `/app` + `/editor` + PWA remain |
| PWA / path-bridge Studio-scoped | Unchanged; still required for web absolute paths |
| Phase 4 desktop track parallel | = this doc’s Phase 3 **C** |
| Extension-first until fork reliable | = Phase 2c **D** before 3.0 |

---

## 8. Risks & honesty obligations

1. **Capability theater** — Cursor-like chrome ≠ Cursor product. Keep `full_cursor_com: false` until Desktop+AI criteria met (define a gate checklist before flipping).  
2. **Companion RCE** — any future exec API on `:4010` is a local privilege footgun; default deny.  
3. **Fork treadmill** — monthly Code-OSS rebase; security patches; Windows build agents.  
4. **Marketplace trap** — configuring MS Marketplace in `product.json` for a fork violates ToS expectations.  
5. **Remote gap** — users expecting Pylance/Remote-SSH identical to VS Code will be disappointed on a clean fork; document alternatives.  
6. **AI expectations** — template builds must stay labeled until LLM routing ships (`HONESTY_POLICY` / status.json).  

---

## 9. Suggested “full parity” gate (future — not claimed today)

Flip marketing / `status.json` only when **all** are true:

- [ ] ODEI Studio Desktop installable on Windows (signed) from Code-OSS  
- [ ] Integrated terminal executes in workspace cwd  
- [ ] Git SCM status/diff/commit works in-product  
- [ ] ≥1 language LSP + Problems populated; debug adapter for ≥1 stack  
- [ ] Native multi-root; documented remote story (host or ODEI agent)  
- [ ] ODEI AI: chat + rules + model routing (Tab optional/labeled)  
- [ ] Extension install path (Open VSX or curated) documented legally  
- [ ] ODID auth for cloud AI; update channel live  
- [ ] Public docs still distinguish Web vs Desktop  

**None of the above are true as of 2026-07-31.**

---

## 10. Related docs

- [`STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md`](./STUDIO_EDITOR_HOLISTIC_INVESTIGATION.md) — live `/editor` audit  
- [`STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md`](./STUDIO_EDITOR_CURSOR_WORKSPACE_PARITY.md) — chrome gap matrix  
- [`STUDIO_EDITOR_PHASE_2C.md`](./STUDIO_EDITOR_PHASE_2C.md) — extension deepen 0.3.0  
- [`STUDIO_DESKTOP_CODE_OSS_ROADMAP.md`](./STUDIO_DESKTOP_CODE_OSS_ROADMAP.md) — Desktop scaffold (C)  
- `ODEI Studio/desktop/README.md` — honest non-binary Desktop folder  
- `ODEI Studio/vscode/README.md` — fork build pipeline (aspirational)  
- `ODEI Studio/status.json` — machine-readable honesty  

---

*Investigation revalidated 2026-07-31. Phase 2b + 2c shipped; recommendation remains **C via D→C**; architecture still does **not** equal Cursor; Code-OSS Desktop remains scaffold — no binary claimed or implemented in this pass.*
