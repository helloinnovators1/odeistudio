> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/AI_PRODUCTION_READINESS_EVIDENCE_REPORT.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ai/AI_PRODUCTION_READINESS_EVIDENCE_REPORT.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# AI Production Readiness Evidence Report

Generated: 2026-08-04T10:22:10.472Z
Profile: `ci`
Gate: `on (exit 1 on FAIL)`

## Score

- PASS: 8
- FAIL: 0
- Total controls: 8
- Gate result: PASS

## Failed controls

- None

## Control Matrix

| Control | Status | Tier | Proof command | URL/Endpoint | Evidence detail |
|---|---|---|---|---|---|
| CI gate + report scripts registered | PASS | ci | `node -e "JSON.parse(require('fs').readFileSync('package.json')).scripts"` | package.json | gate=true report=true tool=true |
| Observability environment assets present | PASS | ci | `ls hosting/docker-compose.ai-observability.yml hosting/observability/` | hosting/observability/ | compose=true otel=true prom=true tempo=true |
| Production env template + bootstrap present | PASS | ci | `ls hosting/.env.ai-production.example tools/provision-ai-production-env.ps1` | hosting/.env.ai-production.example | env=true bootstrap=true |
| ODEI GPT + Governance Console + Tools UI sources | PASS | ci | `ls apps/ai/gpt.html apps/ai/governance-console.html apps/ai/tools.html` | apps/ai/ | gpt=true gov=true tools=true |
| Whitepaper links ODEI GPT + governance (dated 2026-08-04) | PASS | ci | `rg -n "gpt.html|governance-console|Updated" apps/ai/whitepaper.html` | http://localhost:5203/whitepaper.html | links+date ok |
| Foundation model pack sources | PASS | ci | `npm run verify:ai-foundation-pack` | apps/ai/foundation/ | readme=true registry=true |
| verify:ai-tools (75-tool registry) | PASS | ci | `npm run verify:ai-tools` | apps/ai/scripts/verify-ai-tools.mjs | verify:ai-tools OK — 75 tools; NOC + deploy confirm + MoMo + LLM + OCSC deferred + governance/eval/safety pack + ODEI GPT + production matrix { "total": 75, "p0": 74, "p1": 1, "toolsUi": "http://localhost:5203/tools.html", "gptUi": "http://localhost:5203/gpt.html", "gptHttp": "ok", "networkUi": "http://localhost:5203/network-intelligence.html", "nocUi": "http://localhost:5203/noc.h |
| verify:ai-foundation-pack | PASS | ci | `npm run verify:ai-foundation-pack` | apps/ai/scripts/verify-foundation-pack.mjs | [verify:ai-foundation-pack] scaffold complete Root: E:\ODEI Multi Ecosystem\apps\ai\foundation |

## Notes

- Profile `ci` = static/code controls (GitHub Actions gate).
- Profile `live` = ci + local HTTP surfaces.
- Profile `production` = live + observability stack + credentials + external endpoints.
- Re-run: `npm run gate:ai-production-readiness -- --profile=ci`
- Report-only: `npm run report:ai-production-readiness -- --profile=ci`
