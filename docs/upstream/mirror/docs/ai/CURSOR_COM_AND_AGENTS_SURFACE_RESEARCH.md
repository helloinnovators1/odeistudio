> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/CURSOR_COM_AND_AGENTS_SURFACE_RESEARCH.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ai/CURSOR_COM_AND_AGENTS_SURFACE_RESEARCH.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# Cursor.com + cursor.com/agents — Holistic Surface Research

**Date:** 2026-07-31  
**Status:** Research (no ODEI cloud-agent implementation in this pass)  
**Primary URLs:** [cursor.com](https://cursor.com/) · [cursor.com/agents](https://cursor.com/agents)  
**Peers:** [`ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md`](./ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md) · [`ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`](./ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md) · [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) · [`HONESTY_POLICY.md`](./HONESTY_POLICY.md)

**Canvas:** open beside chat → [`cursor-com-and-agents-surface-research.canvas.tsx`](/Users/Software%20Innovations/.cursor/projects/e-ODEI-Multi-Ecosystem/canvases/cursor-com-and-agents-surface-research.canvas.tsx)

---

## 0. Executive verdict

| Question | Answer |
|----------|--------|
| What is [cursor.com](https://cursor.com/)? | Marketing + product hub for Cursor as an **AI coding agent** platform: Desktop, CLI, Cloud Agents, Automations, models, enterprise — not “just an IDE download page.” |
| What is [cursor.com/agents](https://cursor.com/agents)? | The **web control plane for Cloud Agents** (isolated VMs, parallel fleets, review/artifacts). Login/bot-gated in anonymous fetches; documented in [Cloud Agents docs](https://cursor.com/docs/cloud-agent). |
| Same as Studio `/app` Agents? | **No.** Studio Agents = local template Build OS UX. Cursor `/agents` = **cloud VM agents** with own computers, PRs, remote desktop. |
| ODEI implication | Keep **ODEI AI** (intelligence/gateway) and **ODEI Studio** (creator/IDE) **independent**. Cloud-class agents are a future **ODEI AI + infra** capability that Studio would *launch*, not own alone. |

**One line:** Cursor’s homepage sells an **AI operating workspace**; `/agents` is the **cloud agent fleet console** — far above ODEI’s current local Agents + AI gateway.

---

## 1. Method & source honesty

| Source | Access 2026-07-31 | Role |
|--------|-------------------|------|
| [cursor.com](https://cursor.com/) | Fetched (markdown) | **Verified** homepage thesis, nav, model picker labels, product pillars |
| [cursor.com/agents](https://cursor.com/agents) | Cloudflare authenticator interstitial | **Partial** — URL is the documented web entry; HTML body not scrapeable without auth |
| [cursor.com/docs/cloud-agent](https://cursor.com/docs/cloud-agent) | Fetched | **Verified** — what `/agents` *is* for (Cloud Agents) |
| [cursor.com/help/ai-features/cloud-agents](https://cursor.com/help/ai-features/cloud-agents) | Search/docs | **Verified** — access points, MCP, billing notes |
| [cursor.com/blog/agent-computer-use](https://cursor.com/blog/agent-computer-use) | Search | **Verified** — computer use, artifacts, remote desktop |
| Prior ODEI research / P0 gateway | Repo | Studio + AI current state |

Never invent private Cursor internals (scheduler, exact VM image, billing meters). Prefer docs-dated claims.

---

## 2. What [cursor.com](https://cursor.com/) markets

### 2.1 Positioning

Headline: **“Cursor is your coding agent for building ambitious software.”**  
Product is framed as an **agent**, not merely an editor with autocomplete.

### 2.2 Product surfaces (nav / sections)

From the public homepage (and linked product areas):

| Surface | What homepage emphasizes |
|---------|---------------------------|
| **Desktop** | IDE + Agents Window demos (plan/build, file edits, local preview) |
| **Agents / Cloud** | Parallel autonomous agents with **their own computers**; review walkthroughs/artifacts |
| **CLI** | `curl https://cursor.com/install -fsS \| bash` — agent in terminal / CI |
| **Mobile / iPad** | Changelog: Cursor on iPad; build from anywhere |
| **Automations** | Always-on agents on schedules/triggers (CI fix bots, etc.) |
| **Slack / GitHub** | Agents in chat and PR comments (`@cursor`) |
| **Models** | Multi-provider picker; Auto + frontier roster |
| **Enterprise** | Fortune 500 / scale / security narrative |
| **Marketplace** | Linked as product area (rules/skills/plugins ecosystem) |
| **Review** | Code review product lane |

### 2.3 Model selector (homepage marketing labels)

Public picker on homepage (marketing UI — treat as **presented**, confirm against [models & pricing](https://cursor.com/docs/models-and-pricing) for billing IDs):

- **Auto** (suggested)
- **Grok 4.5**
- **GPT-5.6 Sol**
- **Fable 5 Max**
- **Opus 5**
- **Gemini 3.1 Pro**
- **Composer 2.5**

Homepage copy: choose models from OpenAI, Anthropic, Gemini, SpaceXAI, and Cursor.

### 2.4 Homepage thesis (architectural)

Cursor presents a **unified AI software factory**:

1. Local agentic IDE (plan → build → review)  
2. Cloud agents that run **offline from your laptop**  
3. CLI + Slack + GitHub as **same agent, many doors**  
4. Model router / Auto as first-class UX  
5. Team/enterprise administration around that factory  

That is an **AI Operating Workspace**, not a single SPA.

---

## 3. What [cursor.com/agents](https://cursor.com/agents) is

### 3.1 Access note

Anonymous fetch of `/agents` hit **Cloudflare bot/auth verification** (`authenticator.cursor.sh`). That matches a **logged-in web app** for team agent runs, not a public marketing brochure.

Official docs still define the URL’s purpose clearly:

> Start and manage agents from [cursor.com/agents](https://cursor.com/agents) on any device.  
> — [Cloud Agents docs](https://cursor.com/docs/cloud-agent)

### 3.2 Cloud Agents (the product behind `/agents`)

From [docs/cloud-agent](https://cursor.com/docs/cloud-agent) and related help/blog:

| Capability | Meaning |
|------------|---------|
| **Isolated cloud VMs** | Full Linux/dev environment: clone, deps, secrets, network — not browser JS sandbox |
| **Parallel fleets** | Many agents at once; laptop need not stay online |
| **Build / test / demo** | Agents can run the software; produce screenshots, videos, logs |
| **Computer use + remote desktop** | Agent controls desktop/browser; human can take over remote desktop |
| **Merge-ready PRs** | Branch + push + PR handoff into GitHub/GitLab/Bitbucket/Azure DevOps |
| **Multi-repo** | One task spanning frontend/backend/infra workspaces |
| **Environments** | Snapshots, Dockerfiles, `.cursor/environment.json`, secrets dashboard |
| **MCP** | Team MCP servers managed from agents UI dropdown |
| **Hooks** | Repo `.cursor/hooks.json` (+ Enterprise team/enterprise hooks); **not** `~/.cursor` user hooks |
| **Triggers** | Desktop Cloud mode, iOS, Slack, GitHub `@cursor`, Linear, API, Automations |
| **Team share** | Agent URLs; repo ACL + team membership; optional team follow-ups |
| **Billing** | API pricing for selected model + spend limits (paid plans) |
| **SCM prerequisite** | Admin connects GitHub / GitLab / Bitbucket / Azure DevOps before repo agents start |
| **Environments** | Agent-led setup, snapshots, Dockerfile / `.cursor/environment.json`; secrets dashboard |
| **Network** | Outbound domain allowlists; Tailscale / private connectivity options |
| **Android** | Use `/agents` in Chrome → Install App (PWA); native app is iOS |

**Naming:** formerly “Background Agents.”

### 3.3 Desktop Agents Window ≠ `/agents`

| Surface | Runs where | ODEI analogue today |
|---------|------------|---------------------|
| Desktop **Agents Window** | Local IDE session | Studio `:3002/app` + Editor Agents panel (template / ModelRouter client) |
| **cursor.com/agents** | Cloud VM fleet console | **None** — planned class of work under ODEI AI + hosting, not Studio alone |

Do not conflate “Agents” marketing with a single UI.

---

## 4. Mapping Cursor → ODEI (products stay independent)

| Cursor surface | ODEI owner | Today (honest) | Future |
|----------------|------------|----------------|--------|
| Desktop IDE chrome | **ODEI Studio** | Next `/editor` + `/app`, extension 0.3.0, Desktop scaffold | Code-OSS Desktop (XL) |
| Local Agents UX | **ODEI Studio** (client) | Template builds + AI-routed builds when gateway up | Richer agent UX consuming AI |
| Model router / Auto / keys | **ODEI AI** | Gateway `:5203` (`local_sim` / configured with keys) | Full multi-provider pools + org policy |
| Cloud Agents / `/agents` | **ODEI AI** + infra (Studio launches) | **Not built** | Sandboxed runners, PR artifacts |
| CLI agent | **ODEI AI** CLI or Studio CLI thin client | Not Cursor CLI | ODEI agent CLI calling AI gateway |
| Automations / Slack / GH bots | **ODEI AI** + Communications / Core | OMSG local; no Cursor-like bots | Event-triggered AI jobs |
| Team admin / billing / model ACL | **ODEI AI** + Membership / Identity | Local keys / honesty | ODID + Pay + org AI policy |
| Marketplace (rules/skills) | **ODEI AI** marketplace | Planned IA | Catalog of agents/prompts/models |
| MCP policy | **ODEI AI** | Planned | Gateway-enforced MCP allowlists |

**Hard rules**

- Studio must **not** host org model billing or claim Cursor Tab / Cursor Cloud Agents.  
- AI must **not** own full IDE/PTY/SCM/path-bridge.  
- Never advertise GPT/Claude/Grok as ODEI-live unless gateway `configured` + routed.

---

## 5. Gap matrix (ODEI vs Cursor.com + /agents)

| Capability | Cursor | ODEI now | Gap size |
|------------|--------|----------|----------|
| Marketing site as agent OS | Strong | Studio + AI separate product sites | OK (modular) |
| Local Agents UI | Desktop + web demos | Studio `/app` + Editor | Medium (UX depth) |
| Multi-model Auto | Live product | AI gateway Auto heuristic + `local_sim` | Medium–Large |
| Cloud VM agents | Live (paid) | Absent | **XL** |
| Parallel fleets + artifacts | Live | Absent | **XL** |
| Remote desktop control | Live | Absent | **XL** |
| Slack/GH `@agent` | Live | Absent | Large |
| Automations | Live | Absent | Large |
| MCP team console | Live on `/agents` | Absent | Large |
| CLI install one-liner | Live | Absent | Medium |
| Enterprise SSO / spend | Live | Planned ODID/Pay | Large |

---

## 6. Recommended ODEI phases (honest)

| Phase | Scope | Owner |
|-------|--------|-------|
| **Done (P0)** | AI gateway `:5203` + Studio ModelRouter consumer; template fallback | AI + Studio |
| **P1** | Model catalog UX in Studio; rules UI; consented snippets; provider keys ops runbook | AI + Studio |
| **P2** | MCP allowlist on AI gateway; basic agent job queue (same-machine worker, not full VM) | AI |
| **P3** | True cloud sandboxes (VM/container), PR artifacts, web “Agents” console — **ODEI AI Agents** surface, Studio deep-link only | AI + hosting |
| **Never** | Claim parity with Cursor Cloud Agents or Cursor Tab without shipping equivalents; merge AI+Studio into one product |

---

## 7. Relation to existing ODEI docs

- [`ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md`](./ODEI_AI_AND_STUDIO_VS_CURSOR_RESEARCH.md) — CLI models + ownership split (broader).  
- This doc — **homepage + `/agents` surface deep-dive** and Cloud Agents gap.  
- [`ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md`](./ODEI_AI_GATEWAY_AND_STUDIO_MODELROUTER.md) — P0 implementation how-to.  
- [`STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md`](./STUDIO_CURSOR_FULL_PARITY_INVESTIGATION.md) — desktop IDE pillars (Code-OSS, PTY, Git, …).

---

## 8. Official references

- [cursor.com](https://cursor.com/)  
- [cursor.com/agents](https://cursor.com/agents)  
- [Cloud Agents docs](https://cursor.com/docs/cloud-agent)  
- [Cloud agent capabilities](https://cursor.com/docs/cloud-agent/capabilities.md)  
- [Models & pricing](https://cursor.com/docs/models-and-pricing)  
- [Agent computer use blog](https://cursor.com/blog/agent-computer-use)  
- CLI install: `curl https://cursor.com/install -fsS | bash` (homepage)
