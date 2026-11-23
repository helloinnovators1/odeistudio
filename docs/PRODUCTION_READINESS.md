# Production and Deployment Readiness

**Assessment date:** 2026-11-23  
**Assessed main commit:** `bad8b29b8e5f6fe6010824ee6417ff4d24724453`  
**Decision:** **NO-GO for production deployment.** The repository has a clean post-merge CI/security result, but external infrastructure, identity, security operations, browser acceptance and deployment controls have not been demonstrated. This document is a release gate, not a claim that those external steps have occurred.

## Verified repository evidence

- PR [#74](https://github.com/helloinnovators1/odeistudio/pull/74) is merged; its squash merge is the assessed main commit above.
- Post-merge API CI [45111357797](https://github.com/helloinnovators1/odeistudio/actions/runs/45111357797): web, MongoDB integration, and Ubuntu/Windows Python 3.10/3.12 jobs all completed successfully.
- Post-merge Security Scanning [45111357731](https://github.com/helloinnovators1/odeistudio/actions/runs/45111357731): Python dependency audit, web dependency audit, secret scanning and CodeQL completed successfully.
- API readiness checks MongoDB ping and transaction-capable topology. A replica set or sharded cluster is required; a standalone server correctly fails readiness.
- MAC environment governance, revision lifecycle, deployment ledger/worker foundation and MAD incident/audit work from PR #74 are integrated. The code provides allowlisted factory hooks; this is not proof of a real cloud provider or external secret-manager adapter.
- No production deployment, production smoke test, staging acceptance, target-device acceptance, backup restoration, or rollback drill is recorded by this assessment.

## Release-blocking gates

A gate is complete only when its evidence is attached to the release record and independently reviewed. Do not mark a gate complete from a configuration example, unit test, CI pass, or code path alone.

### 1. Identity and access

- [ ] Register the production ODID issuer, client IDs, exact callback URLs, scopes, audience/resource and JWKS endpoint.
- [ ] Verify PKCE S256, state/nonce handling, callback error paths, token expiry/refresh/revocation and key rotation against the real identity provider.
- [ ] Configure API `AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL`, `AUTH_ALLOWED_CLIENT_IDS`; prove invalid issuer/audience/client, expired token, unknown key and JWKS outage fail closed.
- [ ] Provision and review organization/project memberships and privileged operator identities; require MFA for privileged access.
- [ ] Configure exact HTTPS `CORS_ALLOWED_ORIGINS`; verify production browser origin, cookies/token handling, security headers, rate limits and abuse controls.
- [ ] Exercise cross-tenant denial and role boundaries with at least two real test tenants.

### 2. Database and data protection

- [ ] Provision production MongoDB replica set or sharded cluster with TLS, private network access, least-privilege application identity and encrypted storage.
- [ ] Verify `MONGODB_URI` and `MONGODB_DATABASE` injection from the deployment secret manager; never put credentials in source, images, build args or browser variables.
- [ ] Run migrations/index initialization against a production-like restored copy; capture before/after counts and validation output.
- [ ] Verify task/audit transaction behavior, unique indexes, connection-pool/timeouts and failure behavior under primary stepdown/network interruption.
- [ ] Define retention, deletion, export, data residency and tenant offboarding procedures.
- [ ] Configure automated encrypted backups and point-in-time recovery; restore into an isolated environment and record measured RPO/RTO.

### 3. Secrets and cryptographic material

- [ ] Treat the database credential previously disclosed in project setup material as compromised until rotated. Rotate it at the source, revoke the old credential, inspect access logs and record the rotation evidence.
- [ ] Select and integrate a real managed secret manager/KMS. Validate workload identity, least privilege, secret versioning, rotation, revocation and outage behavior.
- [ ] Configure MAC provider and secret-resolver factories only from deployment-owned exact allowlists; prove unknown, malformed, duplicate and unapproved references fail closed.
- [ ] Generate and store patch-approval signing keys in an approved secret boundary; document key ID rollover, revocation and recovery. Never export private keys to client devices.
- [ ] Keep MAD metrics credentials server-side, high entropy, rotated and restricted by network policy; verify unauthorized requests are rejected.
- [ ] Scan container images, release artifacts, logs, traces and browser bundles for credentials and sensitive configuration.

### 4. API and web deployment

- [ ] Choose and document supported hosting/runtime targets, regions, DNS/TLS, ingress, WAF, request/body limits, timeouts and autoscaling.
- [ ] Build reproducible immutable API and web artifacts from the exact reviewed commit; pin base images by digest and generate an SBOM/provenance record.
- [ ] Run the API as non-root with read-only root filesystem where possible, dropped capabilities, bounded resources and graceful shutdown.
- [ ] Configure production environment variables from a secret manager; validate startup fails safely when mandatory configuration is absent or malformed.
- [ ] Confirm production docs are disabled, debug/dev routes are absent, error responses are non-sensitive, and CORS contains only exact approved origins.
- [ ] Verify liveness and readiness through the real load balancer; readiness must remain 503 until the transaction-capable database is available.
- [ ] Verify frontend API origin, ODID redirect URI and CSP/security headers in the built artifact, not only in local development.
- [ ] Exercise rolling deployment, old/new compatibility, drain behavior, startup failure and rollback on the target platform.

### 5. Execution worker and hostile-code isolation

- [ ] Provision a dedicated Linux worker pool separate from API/web hosts.
- [ ] Use rootless OCI execution plus a stronger hostile multi-tenant isolation boundary (gVisor, Kata Containers, microVM or equivalent); document the threat model and residual risk.
- [ ] Pin verified immutable runtime image digests; prohibit mutable tags in production.
- [ ] Ensure no host, cloud, database, source-control or production credentials enter jobs or containers.
- [ ] Enforce default-deny network egress, filesystem boundaries, non-root UID, seccomp/AppArmor/SELinux policy, PID/memory/CPU/disk/time quotas and bounded output/artifacts.
- [ ] Validate archive traversal, symlink/hardlink, decompression bomb, oversized artifact, malware/content policy and workspace snapshot limits.
- [ ] Test worker crash/restart, lease expiry, duplicate delivery, idempotent provider retry, cancellation races, timeout, cleanup and orphan artifact handling.
- [ ] Demonstrate queue backpressure, worker capacity limits, drain/maintenance mode and emergency execution kill switch.

### 6. MAC/MAD governance and audit

- [ ] Configure separate production requester, approver and operator identities; prove no self-approval and least-privilege access.
- [ ] Connect and test real provider adapters and secret manager adapters; test provider idempotency, timeout, cancellation, partial failure and reconciliation.
- [ ] Run MAC schema migration in staging, validate revision history and execute a tested rollback/recovery procedure.
- [ ] Verify latest-revision-only submit/approve/promote behavior and stale revision rejection against the deployed database.
- [ ] Enforce append-only audit storage permissions at the database level; test that update/delete are denied to application identities.
- [ ] Test audit failure atomicity for every privileged state transition; reconcile any remaining non-transactional conversation/proposal audit paths.
- [ ] Verify MAD telemetry, alert deduplication, incident acknowledge/assign/resolve/reopen, delivery integrations, retention and access control.

### 7. Browser, accessibility and device acceptance

- [ ] Complete authenticated browser E2E for ODID PKCE success/error, organization/project switching, conversation create/load/send/stream/cancel/delete, task approval, execution consent, artifacts, patch lifecycle, companion pairing and MAC/MAD authorization denial.
- [ ] Complete keyboard-only navigation, focus visibility/restoration, dialogs, accessible names/roles/live regions and automated axe (or equivalent) checks.
- [ ] Add deterministic screenshots at mobile/tablet/desktop breakpoints and review visual diffs.
- [ ] Validate companion install, update, signing, pairing, revocation and recovery on the actual supported Windows 10 build 18362.1256 device; CI Windows runners are not a substitute.
- [ ] Validate Chrome loopback Local Network Access permission and HTTPS browser-origin requirements on supported browsers.

### 8. Observability and incident operations

- [ ] Centralize structured logs, traces and metrics with request/correlation IDs and strict secret/PII redaction.
- [ ] Define SLOs and alert thresholds for API availability/latency, auth failures, MongoDB health/replication, queue age, worker failures, execution timeouts, artifact errors and provider failures.
- [ ] Configure paging/on-call ownership, escalation, incident severity, status communications and runbooks.
- [ ] Test credential compromise, tenant isolation incident, malicious execution, provider outage, database outage/data loss and key compromise tabletop scenarios.
- [ ] Verify log/metric access controls, retention, export controls and auditability.

### 9. Release governance and rollback

- [ ] Protect `main`: require independent approving review, dismiss stale approvals, require current CI/security checks, require conversation resolution, and block force pushes/direct pushes.
- [ ] Keep browser E2E/accessibility/visual regression as required checks after issue #64 is implemented.
- [ ] Produce a release manifest containing commit, artifact digests, SBOM, test evidence, migration version, configuration version and approvers.
- [ ] Deploy to staging first; run migration, smoke, tenant isolation, execution safety, browser E2E and rollback tests against production-like services.
- [ ] Obtain explicit release approval and a documented change window.
- [ ] Use canary/rolling rollout with abort thresholds and tested rollback; verify data/schema compatibility before rolling back application code.
- [ ] Record post-deploy smoke results, dashboards, error budget and operator sign-off.

## Configuration inventory (API)

The names below are defined by the current API settings model. Supply values only through the deployment platform or managed secret manager; this document intentionally contains no secret values.

| Setting | Purpose | Production gate |
|---|---|---|
| `ENVIRONMENT` | Runtime environment | Set to `production`; verify docs disabled |
| `MONGODB_URI` | MongoDB connection | Secret manager; TLS/private endpoint; replica set/sharded |
| `MONGODB_DATABASE` | Database name | Explicitly provisioned and least-privilege |
| `AUTH_ISSUER` | ODID issuer | Exact HTTPS issuer |
| `AUTH_AUDIENCE` | API audience/resource | Exact production audience |
| `AUTH_JWKS_URL` | Signing keys | HTTPS, monitored rotation |
| `AUTH_ALLOWED_CLIENT_IDS` | Client allowlist | Explicit production client IDs |
| `CORS_ALLOWED_ORIGINS` | Browser origins | Exact HTTPS origins only |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Model provider | Server-side secret and approved model |
| `MAD_METRICS_TOKEN` | Internal metrics | 32+ ASCII chars; secret manager + network policy |
| `PATCH_APPROVAL_ISSUER`, `PATCH_APPROVAL_KEY_ID`, `PATCH_APPROVAL_PRIVATE_KEY_B64` | Signed companion approval | Configure all together; private key protected and rotated |
| `MAC_PLATFORM_OPERATORS_JSON` | MAC operator registry | Deployment-owned identity/permission review |
| `MAC_PROVIDER_FACTORY_ALLOWLIST_JSON` | Provider factories | Exact reviewed factory references only |
| `MAC_SECRET_RESOLVER_FACTORY_ALLOWLIST_JSON` | Secret resolver factories | Exact reviewed factory references only |
| `EXECUTION_PROFILES_JSON`, `EXECUTION_RUNTIME_PATH`, `EXECUTION_WORKSPACE_ROOT`, `EXECUTION_WORKER_ID` | Worker runtime | Worker-only deployment; immutable images and sandbox policy |

Confirm any additional settings in the exact release commit's `apps/api/odei_api/config.py` and worker entrypoint before rollout. Do not assume this table is an exhaustive schema for external provider integrations.

## Operational commands and acceptance

- API liveness: `GET /api/v1/health/live` — process alive only; not a readiness signal.
- API readiness: `GET /api/v1/health/ready` — requires reachable MongoDB and transaction-capable topology.
- Internal MAD metrics: `GET /api/v1/internal/mad/execution-metrics` — requires `X-ODEI-MAD-Token` and should additionally be network-restricted.
- Authenticated MAD metrics: `GET /api/v1/mad/execution-metrics` — requires verified identity and operator permission.

A release is **GO** only when every release-blocking gate above has an evidence link, an owner and an approval. Until then, keep production traffic disabled and use isolated development/staging environments with synthetic data.
