> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/ODEI Studio/docs/PLANNED_DESKTOP_OFFLINE_AND_DOMAIN_PACKS.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/ODEI%20Studio/docs/PLANNED_DESKTOP_OFFLINE_AND_DOMAIN_PACKS.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI Studio — Planned Desktop, Offline AI, and Domain Packs

**Status:** Planned. This document does not announce a shipped Electron app, local model, or AetherIDE replacement.

## Desktop and offline path

ODEI Studio may extend its existing Code-OSS scaffold with a desktop distribution and an offline-first model path. The intended architecture is: local model/cache fallback where a device supports it, governed routing through ODEI AI for cloud use, sandboxed workspace access, and ODID-aware policy before sensitive actions.

No binary, Electron shell, local model runtime, offline autocomplete, or production desktop IPC is currently delivered. The existing `desktop/` directory remains a Code-OSS scaffold only.

## Planned domain packs

Candidate extension packs are:

- **Solidity:** contract authoring, test fixtures, static review, and human-approved security workflows.
- **TON / Chain:** TON and ODEI Chain tooling, transaction simulation, and explicit signing boundaries.
- **LMS / Academy:** course and learning-content structures, assessment schemas, and accessibility checks.

Each pack needs an accountable owner, test corpus, license review, security model, and release criteria. They are not enabled extensions or automated auditors.
