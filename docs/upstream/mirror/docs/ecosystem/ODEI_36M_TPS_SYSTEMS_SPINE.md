> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_36M_TPS_SYSTEMS_SPINE.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_36M_TPS_SYSTEMS_SPINE.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI 3,600,000 TPS — systems engineering spine (P4–P7)

**Design target (not a live claim):** `3600 shards × 1000 TPS/shard = 3,600,000`.

## Distinction

| Layer | Status |
|-------|--------|
| Architecture capable of scaling toward 3.6M | **Implemented as lab control plane** |
| Independently verified public-mainnet 3.6M | **Not achieved** — requires geographic fleet + native runtimes + auditor signature |

## Modules

| Module | Path | Role |
|--------|------|------|
| Global shard fabric | `odei_chain/shard_fabric.py` | Router, adaptive spawn/split/merge/retire, OS process workers (capped locally) |
| Remote agents | `odei_chain/remote_agent.py` | Regional agent registry + 3600-shard assignment packing |
| Slim BFT engine | `odei_chain/bft_shard_bench.py` | Per-shard QC commit bench (target ≥1000 lab) |
| Concurrent BFT scale | `odei_chain/bft_multi_shard.py` | Multi-engine aggregate → project ×3600 |
| Receipt bus + settlement | `odei_chain/receipt_bus.py` | Parallel bus + lock→merkle→credit→finality |
| Ops + AI scheduler | `odei_chain/ai_scheduler.py` | Telemetry dashboard + heuristic split/spawn recommendations |
| Proof verify | `odei_chain/proof_verify.py` + `verify_cli.py` | Hash verify; `mainnet_audited` requires auditor.signature |

## Measured on this host (lab)

- **P4 fleet sim:** 3600 shards assigned, gap 0, design capacity math 3,600,000
- **P5 slim BFT:** ~**5,275 TPS** on one lab shard (`meets_per_shard_target=True`) — *not* mainnet
- **P6 receipt bus:** ~**39,917** publish TPS (in-process)
- **P6 settlement graph:** ~**16.6 TPS** signed lock/aggregate/credit (500/0)

## Still required for truthful mainnet 3.6M

1. Native Rust/C++ (or equivalent) execution path per shard  
2. Geographic regional servers + QUIC/UDP production receipt bus  
3. ~3600 concurrent OS process / BFT clusters under SRE  
4. Independent auditor replay with `claim_status=mainnet_audited` + signature  

Until then: **design objective + lab proofs only**.
