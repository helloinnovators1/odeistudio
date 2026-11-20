> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_CORE_HOLISTIC.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_CORE_HOLISTIC.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Core (Shared Platform)

> Foundational shared infrastructure upon which every ODEI product is built.

| Field | Value |
|-------|-------|
| **Organization** | ODEIAfrica |
| **Document** | Holistic product documentation (exhaustive operational index) |
| **Last updated** | 2026-07-24 |
| **Maturity status** | Blueprint Word currently misplaced under CoinCore folder — no Core code repo yet |
| **Build-order phase** | P0 foundation — critical |
| **Workspace** | ODEI Multi Ecosystem |
| **Master index** | [`../README.md`](../README.md) |

---
## 1. Identity

ODEI Core is **not another application**. It is the shared platform: Identity Core, AI Core, Payment Core (wallet engine, MoMo, escrow, treasury, settlement), Blockchain Core, Communication Core, storage, APIs.

---

## 2. Inventory

- Blueprint: `CoinCore by ODEIAfrica/ODEI Core.docx` (**relocate** when Core repo/folder is created)
- Runtime seeds today: patterns inside OPMS services + Docker; Studio packages as build tooling

---

## 3. Role

Single place for auth clients, events, config, ID types, payment intents, audit — consumed by ≥2 apps before declaring Core real.

---

## 4. Dependencies

Soft: Cloud/K8s. Provides to: all products.

---

## 5. Build-order

P0 first engineering after OPMS authz. Exit: shared SDK used by Identity extract + one other consumer.

---

## 6. Actions

1. Create `ODEI Core/` folder or repo. 2. Move Core.docx there. 3. Scaffold packages. 4. Stop putting Core under CoinCore.

---

## 7. Cross-references

- Master index: [`README.md`](./README.md)

---

