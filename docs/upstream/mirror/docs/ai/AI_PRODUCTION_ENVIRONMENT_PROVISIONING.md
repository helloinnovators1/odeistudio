> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ai/AI_PRODUCTION_ENVIRONMENT_PROVISIONING.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ai/AI_PRODUCTION_ENVIRONMENT_PROVISIONING.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI AI Production Environment Provisioning

This creates all environment assets that can be provisioned from this repository, and defines the exact vendor-side handoff for external production dependencies.

## 1) Provision local production-like observability

```bash
docker compose -f hosting/docker-compose.ai-observability.yml up -d
```

Expected endpoints:

- `http://localhost:3003/` (Grafana)
- `http://localhost:9090/` (Prometheus)
- `http://localhost:3100/ready` (Loki)
- `http://localhost:3200/ready` (Tempo)
- `http://localhost:4318/` (OTLP HTTP receiver)

Related files:

- `hosting/docker-compose.ai-observability.yml`
- `hosting/observability/otel-collector-config.yaml`
- `hosting/observability/prometheus.yml`
- `hosting/observability/tempo.yaml`

## 2) Materialize production environment variables

```powershell
powershell -ExecutionPolicy Bypass -File tools/provision-ai-production-env.ps1
```

This creates:

- `hosting/.env.ai-production.local` from `hosting/.env.ai-production.example`

Fill in live values for:

- Provider keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`
- Proprietary runtime: `ODEI_FOUNDATION_INFERENCE_URL`
- OTLP/SIEM: `OTEL_EXPORTER_OTLP_ENDPOINT`, `SIEM_ENDPOINT`, `SIEM_API_KEY`
- Gateway auth: `ODEI_AI_GATEWAY_TOKEN`

## 3) External vendor-side environments (required for full production)

These are not local-code artifacts; they are provisioned in vendor accounts/contracts:

- Managed OTLP backend (Datadog / Grafana Cloud / New Relic / Elastic)
- SIEM backend (Splunk / Sentinel / QRadar / Elastic Security)
- External inference providers (OpenAI / Anthropic / Gemini / xAI)
- Regulated credential store and key rotation policy

Use this repository as control-plane plus evidence-plane:

- runtime and routing: `apps/ai/api/handler.mjs`
- governance controls: `apps/ai/governance-console.html`
- tool runtime: `apps/ai/api/tools/runtime.mjs`
- readiness reporting: `docs/AI_PRODUCTION_READINESS_EVIDENCE_REPORT.md`

## 4) Strict readiness evidence + CI gate

Generate report without failing the process (live profile):

```bash
npm run report:ai-production-readiness
```

Fail the build when any control is FAIL (CI default profile = `ci`):

```bash
npm run gate:ai-production-readiness
```

Other gate profiles:

```bash
npm run gate:ai-production-readiness:live
npm run gate:ai-production-readiness:production
```

GitHub Actions workflow: `.github/workflows/ci-ai-production-readiness.yml`  
Evidence outputs: `docs/AI_PRODUCTION_READINESS_EVIDENCE_REPORT.md` and `.json`
