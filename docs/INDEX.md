# ODEI Studio Documentation Index

Welcome to the engineering and product documentation for ODEI Studio, an African-built AI-native Development Operating System (AI-DOS).

## Start here
- [Ecosystem handbook](ECOSYSTEM.md) — product vision, ecosystem map, principles and end-to-end workflows.
- [Architecture foundation](ARCHITECTURE.md) — system planes, boundaries and core architecture.
- [Implementation status](IMPLEMENTATION_STATUS.md) — verified work, unverified items and next steps.
- [Implementation roadmap](ROADMAP.md) — phased delivery, dependencies and acceptance gates.
- [Engineering standards](ENGINEERING_STANDARDS.md) — code quality, API, testing and contribution rules.
- [Security and privacy](SECURITY.md) — threat model, secrets, isolation, identity and incident handling.
- [Identity integration contract](IDENTITY_INTEGRATION.md) — verified upstream ODID maturity, RFC 9068 access-token profile, required issuer contract and RBAC gates.
- [ODID browser authentication](ODID_BROWSER_AUTH.md) — provider-neutral Authorization Code + PKCE client, token-handling boundaries and production integration prerequisites.
- [Global technical research and decisions](RESEARCH_DECISIONS.md) — official sources and implementation choices.

## Product and platform
- [NEXUS agent specification](NEXUS.md) — AI software engineering agent, tools, loop and runtime.
- [IDE workspace implementation](IDE_WORKSPACE.md) — Monaco shell, NEXUS chat-panel side preference, shortcuts and explicit capability boundaries.
- [NEXUS chat operationalisation](NEXUS_CHAT_OPERATIONALIZATION.md) — complete chat lifecycle, UX contract, identity/consent/security boundaries, event and persistence contracts, and phased acceptance gates.
- [NEXUS project discovery transport](NEXUS_PROJECT_DISCOVERY.md) — secure typed browser client for tenant-scoped project listing and creation.
- [NEXUS chat API](NEXUS_CHAT_API.md) — authenticated project-scoped chat contract, consent, redaction, audit and read-only limits.
- [NEXUS patch proposals](PATCH_PROPOSALS.md) — bounded multi-file patch validation, content hashes, diff output and safe-application requirements.
- [Master Admin Console requirements](MAC_REQUIREMENTS.md) — central configuration and governance plane.
- [Master Admin Dashboard](MAD.md) — operational and executive visibility.
- [Data model](DATA_MODEL.md) — canonical entities, tenancy and persistence rules.
- [API and event contracts](API_AND_EVENTS.md) — API conventions and asynchronous event model.

## Integrations and operations
- [Hosting integrations](HOSTING_INTEGRATIONS.md) — hosting, cloud, registrar and DNS adapters.
- [Provider capability research](PROVIDER_CAPABILITY_RESEARCH.md) — verified initial provider surfaces and limits.
- [Deployment and environments](DEPLOYMENT.md) — local, preview, staging and production deployment.
- [Quality and testing](TESTING.md) — test pyramid, security checks and release gates.
- [Desktop project ingestion](DESKTOP_INGESTION.md) — safe, user-authorized local project indexing without ZIP packaging.
- [Web workspace client](../apps/web/README.md) — Monaco read-only workspace, local pairing and configurable NEXUS panel.
- [Project lifecycle and membership API](API_AND_EVENTS.md#project-lifecycle-and-membership-routes) — tenant-scoped projects and owner-managed members.

## Upstream ecosystem source material
- [Upstream ecosystem alignment](UPSTREAM_ECOSYSTEM_ALIGNMENT.md) — audited source-repository capabilities, migration boundaries, desktop access, AI gateway, MAC/MAD and implementation work order.
- [Imported upstream ecosystem documentation](upstream/INDEX.md) — preserved source snapshots of Studio specifications, desktop/editor phases, MAC audits, AI gateway and ecosystem operating documents.
- [68-document mirror index](upstream/MIRROR_INDEX.md) — source paths, provenance and mirror mapping.

## Documentation rules
1. Treat this index as the canonical documentation entry point.
2. Mark unimplemented capabilities as planned or experimental; never imply that a design document proves implementation.
3. Record provider capabilities against official documentation and the exact account/product scope tested.
4. Update relevant docs in the same change as behavior or API changes.
5. Never place credentials, tokens, connection strings or private customer data in documentation.
