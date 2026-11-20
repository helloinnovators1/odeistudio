> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/ODEI_AI_GLOBAL_TOOLS_RESEARCH_AND_IMPLEMENTATION.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ai/ODEI_AI_GLOBAL_TOOLS_RESEARCH_AND_IMPLEMENTATION.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI AI Global Tools Research and Implementation

Last updated: 2026-08-04

## Objective

Identify globally necessary AI-agent platform tools and implement them into ODEI AI production pathways with governance, safety, and observability controls.

## Research basis

This implementation maps to recurring control-plane requirements observed across:

- OWASP LLM Top 10 and prompt-injection guidance
- NIST AI RMF 1.0 and NIST GenAI Profile (AI 600-1)
- Enterprise agent control-plane patterns (model gateway, tool firewall, approvals, audit)
- OpenTelemetry GenAI observability conventions

## Capability domains required globally

1. Planning and execution tools
2. Data and code workspace tools
3. SQL and state tools
4. Integrations and deployment tools
5. Network and reliability tools
6. Payment and financial-rail tools
7. Multi-tenant LLM operations
8. ModelOps and registry tools
9. Evaluation and quality tools
10. Safety and guardrail tools
11. Governance, incidents, and risk tools
12. Observability and audit export

## Implemented in ODEI AI

Registry: `apps/ai/api/tools/registry.json`
Runtime: `apps/ai/api/tools/runtime.mjs`

### New production tool additions

- `model_registry_status`
- `model_registry_upsert`
- `eval_suite_run`
- `eval_suite_history`
- `guardrail_policy_status`
- `guardrail_policy_update`
- `prompt_injection_scan`
- `pii_scan_text`
- `otel_trace_summary`
- `incident_create`
- `incident_list`
- `risk_register_upsert`
- `risk_register_list`
- `provenance_attest`
- `tool_audit_export`

These are integrated into gateway-exposed forge runtime and included in `verify:ai-tools`.

## Verification

- `npm run verify:ai-tools`
- `npm run verify:ai-foundation-pack`

## Honesty boundary

- Implemented controls are production-ready local code and data-plane scaffolds.
- External infrastructure dependencies (cloud inference fleets, SIEM backends, OTLP collectors, regulated payment production contracts) require environment-level deployment and credentials.
