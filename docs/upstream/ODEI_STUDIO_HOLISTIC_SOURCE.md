> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/ODEI Studio/docs/ODEI_HOLISTIC_DOCUMENTATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/docs/ODEI_HOLISTIC_DOCUMENTATION.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio

> AI-Native Development Operating System of ODEIAfrica — Human → Goal → Product.

| Field | Value |
|-------|-------|
| **Organization** | ODEIAfrica |
| **Document** | Holistic product documentation (exhaustive operational index) |
| **Last updated** | 2026-07-24 |
| **Maturity status** | Live Phase 1 MVP v0.1.0 (MIT) — template agents, no LLM; Code-OSS fork incomplete |
| **Build-order phase** | Parallel enabler all phases; LLM/persistence Phase 2 |
| **Workspace** | ODEI Multi Ecosystem |
| **Master index** | [`../README.md`](../README.md) |

---
## 1. Product identity

**Version:** 0.1.0 · **License:** MIT · **Author:** ODEIAfrica  
**Stack:** TypeScript · npm workspaces · Express 5 (:4000) · Next.js 15 (:3002) · VS Code Extension API  
**Claim vs reality:** Marketed multi-agent AI-DOS; Phase 1 is deterministic template scaffolding with named agent roles.

---

## 2. Folder inventory

### Path

`ODEI Studio/`

### Contained artifacts

- `README.md, LICENSE (MIT), package.json (workspaces), tsconfig.base.json`
- `apps/web, packages/{shared,orchestrator,build,api}, extensions/{odei-studio,odei-theme}`
- `vscode/ (fork scripts; upstream often broken partial clone), scripts/*.ps1, docs/`
- `ODEI Studio … ODEIAfrica.docx, Cursor Deep Autonomous Research Report.rtf, _odei.zip, _odei_extracted.txt`

---

## 3. Role in the ODEI Multi Ecosystem

Accelerates greenfield stubs via goal→plan→artifacts. Does **not** block money rails. Future Agent Marketplace ≠ commerce Marketplace.

---

## 4. Dependencies

Optional: Cloud deploy, AI Model Router (Phase 2+). Provides scaffolds to any stub product team.

---

## 5. Overlap with live code (OPMS / Studio)

Own codebase. Competitive research on Cursor is inspiration only — not a Cursor fork.

---

## 6. Architecture & capabilities

Packages: `@odei/shared` · `@odei/orchestrator` · `@odei/build` · `@odei/api` · `@odei/web` · extensions.  
9 DEFAULT_AGENTS · SACCO demo path · template artifacts (REQUIREMENTS, prisma, FastAPI, page.tsx, tests).  
Fork pipeline: `fork:vscode` → brand → integrate — currently fragile (SSL/EOF clone failures logged).

---

## 7. Build-order placement & exit criteria

### Now
Keep Phase 1 demo reliable; fix test build order; do not overclaim AI.

### Next
LLM Model Router · persistence · auth · finish or drop Code-OSS fork · first git commit + remote.

---

## 8. Gaps, risks & honesty

No LLM calls. Open CORS / no auth on API. Web `:3002` can be reachable while
required API `:4000` is down. No user image/file upload path exists (no control,
multipart endpoint, validation, storage, tenancy, cleanup, or vision context).
Zero commits on master. `_odei.zip` is duplicate of DOCX. Upstream clone broken.
Production/environment and media audit:
[`../../docs/ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md`](../../docs/ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md).

---

## 9. Recommended next actions

1. First commit. 2. LLM Phase 2. 3. Use to scaffold Core/Wallet/Pay stubs after interfaces exist. 4. Repair or document extension-only path.

---

## 10. Cross-references

- Master index: [`../README.md`](../README.md)
- Sibling products: see master catalog table
- Canonical sequencing: Africa Infrastructure Roadmap + stub build-order roadmap canvas
- This file: `ODEI_HOLISTIC_DOCUMENTATION.md` generated/updated 2026-07-24

---
