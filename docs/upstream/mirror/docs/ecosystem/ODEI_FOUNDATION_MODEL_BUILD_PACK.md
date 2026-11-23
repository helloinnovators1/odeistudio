> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_FOUNDATION_MODEL_BUILD_PACK.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_FOUNDATION_MODEL_BUILD_PACK.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Foundation Model Build Pack

Last updated: 2026-08-04

This build pack defines the full execution spine to deliver:

1. Proprietary ODEI foundation models
2. ODEI-trained models
3. Full multi-model orchestration experience
4. External operational readiness

## Scope and honesty

- This pack creates the full implementation framework and executable scaffolds.
- It does not claim that a frontier model has already been trained.
- Production claims require completed data ingestion, training runs, evaluations, safety sign-off, and rollout evidence.

## Architecture workstreams

1. Data governance and ingestion
2. Pretraining and fine-tuning
3. Model registry and versioning
4. Evaluation harness and gates
5. Serving and routing policy
6. Red-team and safety controls
7. Release orchestration and rollback

## In-repo implementation

Primary workspace: `apps/ai/foundation/`

- `config/data-governance-policy.yaml`
- `config/model-registry.json`
- `pipelines/data_pipeline.py`
- `training/train_stub.py`
- `eval/eval_harness.py`
- `serving/router_policy.py`
- `safety/redteam_suite.py`
- `rollout/release_controller.py`
- `tasks.json`

Verification script:

- `apps/ai/scripts/verify-foundation-pack.mjs`

Run:

```bash
npm run verify:ai-foundation-pack
```

Runtime integration variable:

- `ODEI_FOUNDATION_INFERENCE_URL` -> foundation inference service base URL (expects `POST /v1/complete`).
- When this is set and release gates are ready, `/v1/models` and `/v1/route` can expose proprietary ODEI models as `configured`.

## Milestone gates (no omission)

### M0 - Governance Ready
- Data policy approved
- PII classification rules enabled
- Dataset lineage logging active

### M1 - Data Ready
- Curated training corpora produced
- Validation splits and leakage checks pass
- Signed dataset manifest registered

### M2 - Model Build Ready
- Base pretraining config registered
- Fine-tune adapters defined
- Budget and compute envelopes approved

### M3 - Eval Ready
- Offline benchmarks pass threshold
- Regression suite green
- Hallucination and safety metrics within policy

### M4 - Safety Ready
- Red-team suite complete
- Prompt injection and abuse scenarios mitigated
- Incident response runbook validated

### M5 - Serving Ready
- Router policy active with fallback
- Latency, cost, and quality SLOs tracked
- Rollback and canary controls validated

### M6 - Public Ready
- External usage pathways stable
- Monitoring and abuse controls live
- Transparency and model cards published

## Operational notes

- Use the existing ODEI AI gateway as the serving boundary.
- Route to proprietary model IDs only after M4 and M5 are met.
- Keep explicit status labels (`planned`, `local_sim`, `configured`, `production`) in all user-facing responses.
