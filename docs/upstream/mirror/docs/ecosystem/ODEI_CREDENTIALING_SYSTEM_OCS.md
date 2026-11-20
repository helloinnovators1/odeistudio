> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_CREDENTIALING_SYSTEM_OCS.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_CREDENTIALING_SYSTEM_OCS.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Credentialing System (OCS)

**Status:** `local_sim` / design edition. This document describes a product direction and local fixture implementation, not live credential issuance, accreditation, employer trust, regulated licensing, production identity proofing, audited cryptography, or mainnet operation.

## Decision

ODEI should build the **ODEI Credentialing System (OCS)** as a foundational trust layer in the Multi-Ecosystem. OCS is credential infrastructure, not an LMS: Academy and approved partner systems may eventually submit credential proposals, while OCS owns issuer policy, template versioning, issuance authorization, status, verification, sharing, and auditability.

**OCSC decision:** defer it. OCSC is not a launched coin, ticker, exchange asset, or necessary credential representation. If a future credential economy has a demonstrated utility need, it may be evaluated as an optional utility design; until then, use **ODEI** for any future ecosystem fees or governance subject to separate policy and legal review. Credentials should be portable records / non-fungible credentials, not a fungible coin.

## Lessons adapted from credential platforms

Credential platforms demonstrate that value comes from reliable issuer controls, recipient ownership, status-aware verification, templating, branding, reporting, and integrations—not from putting certificates on a blockchain by default. OCS adopts those product lessons while retaining explicit ODEI boundaries:

- a visible issuer of record and credential type;
- recipient-facing share/verification references;
- revocation and expiry as first-class states;
- an audit trail and versioned templates;
- integration proposals instead of automatic issuance from LMS progress;
- portable W3C Verifiable Credential and Open Badges alignment as targets, not a claim that the local fixtures are signed VCs or badges.

## Architecture

`Academy / approved partner LMS → issue proposal → OCS issuer authorization → credential record + status list + audit trail → recipient Wallet reference / public verification`

- **ODID:** future consented binding for holders and authorized issuer identities. The local fixture may display an ODID-shaped identifier; it does not authenticate or prove one.
- **Wallet:** future storage or presentation of consented credential references. It is not an NFT requirement.
- **Chain:** hash canonical off-chain credential content and optionally anchor the fingerprint only after policy, privacy, key-management, and chain readiness. No credential content should be placed on-chain merely to create an anchor.
- **Foundation:** planned issuer registry, template policy, key/authorization governance, dispute and revocation policy, and verification continuity stewardship.

## Local implementation

`apps/ocs/` serves an OCS product shell with fixture issuers, nine template categories, a **Template Designer** (`/designer/`) with layout canvas and design JSON (`schema_version`), governed template states (draft → in_review → approved → retired), file-backed durable store under `apps/ocs/api/data/` when Node mounts `api/handler.mjs`, immutable `template_version` + content hash pins on issue, active and revoked sample credentials, SHA-256 local payload fingerprints, verification (shows pinned version), QR-ready verification URL payloads, revocation/expiry status, audit events, recipient-facing credential list, employer-facing verification warning, skills-passport grouping, fixture analytics, local email-notification logs, issuer-record creation, hash-anchor concept, bounded fixture verification/recommendation API and JavaScript SDK stubs, and an AI-OS recommendation attempt with a deterministic OCS fallback.

**Durability:** Prefer `POST/GET /v1/templates*` and `POST /v1/credentials/issue` (file-backed). If the product is served static-only without the API handler, the UI falls back to seed JSON + `localStorage` and labels that mode. Smoke: `npm run verify:ocs-templates`.

**Honesty:** Designer + governance are **operational (local durable)**. Signed W3C VCs, accreditation, live RBAC, ODID authentication, and chain anchors remain **gated**. OCSC is deferred.

Template and issuer browser-fallback records, notification events, and non-durable fixture credentials are clearly labelled local. The email log does not contact recipients or configure SMTP. The QR panel produces a URL payload for a future hosted QR resolver; it does not claim to render a production QR or prove authenticity.

## Academy and partner integration boundary

Academy’s current curriculum and partner fixtures are planned/local simulation records. They must not directly grant OCS credentials just because a learner progressed through a page or course. A production path needs approved assessment evidence, issuer authorization, ODID/consent, data retention controls, signing keys, a status registry, rate/abuse controls, and applicable academic, legal, accessibility, privacy, and jurisdictional reviews.

The three issuer lanes remain distinct: ODEI-issued professional credentials, partner-issued awards, and formally governed co-branded delivery where one issuer of record is explicit. “Co-branded” must not silently mean “co-issued.”

## Capability boundaries

- **Issuer and Foundation framing:** local issuer entries are proposed records for future Foundation policy review. They do not establish accreditation, licensing, award authority, or a verified issuer registry.
- **Templates and designers:** Template Designer + governance are operational as local durable fixtures. They are not production brand verification, accredited award instruments, or signed VC templates.
- **Analytics and email:** all metrics and notification events are local fixtures, not operational reporting or email delivery.
- **Integrations:** Academy is a wired local-simulation proposal path. Moodle, Canvas, other LMS providers, Wallet, and ODID are planned integrations; none currently sends data, signs credentials, or authenticates holders.
- **Marketplace:** the product includes a planned-only panel. It does not sell, transfer, trade, price, or tokenize credentials.
- **API, SDK, and AI-OS:** `GET /v1/credentials/{id}/verification`, `POST /v1/recommendations`, `apps/ocs/sdk/odei-ocs.js`, and AI-OS `ocs.verify` / `ocs.recommend` are local-simulation interfaces. They cannot authorize issuance, attest to a credential, or substitute for production access control and signing.

## Related research

The public-source and industry-typical category research, OCS comparison, and
explicit OCSC decision are available in
[`ODEI_ACCREDIBLE_OCS_RESEARCH.md`](ODEI_ACCREDIBLE_OCS_RESEARCH.md).

## Production gates

Before real issuance: issuer due diligence and authority, versioned credential policy, key custody/rotation, signed VC implementation, status-list and revocation operations, privacy/consent and data-minimization review, verification abuse controls, accessibility and localization, audit retention, incident response, and credential continuity/export plans. Any credit-bearing, degree, diploma, government, or regulated claim also needs jurisdiction-specific approval.
