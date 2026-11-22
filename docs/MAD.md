# Master Admin Dashboard (MAD)

## Purpose
MAD is the operational and executive visibility surface for ODEI Studio. MAC remains the source of truth for configuration and administrative actions.

## Dashboard domains
- Platform health: API, worker, queue, database, event transport and storage health.
- Agent operations: active/queued/failed tasks, latency, cancellation and retry rates.
- Execution fabric: workspace count, resource utilization, sandbox failures and cleanup backlog.
- Integrations: provider connection health, last successful check, permission expiry and webhook delivery.
- Deployments: status, duration, rollback, environment and commit provenance.
- Model economics: token usage, provider cost, budget utilization, quota and per-tenant attribution.
- Security: privileged actions, suspicious activity, policy denials and unresolved incidents.
- Product adoption: active workspaces, projects, feature usage and retention, subject to privacy policy.

## Metric contract
Every metric must declare:
- name and definition;
- authoritative source and query;
- aggregation window and timezone;
- freshness timestamp and expected delay;
- tenant and role visibility;
- missing/stale-data behavior;
- alert threshold and owner, if applicable.

Never render fabricated sample metrics as live production data. Clearly label demo data and simulated states.

## Alerts and incidents
Alerts have severity, source, timestamp, affected service/tenant, deduplication key, owner, status and runbook link. Acknowledge, assign, resolve and reopen actions must be audited.

## Acceptance criteria
- Dashboard distinguishes healthy, degraded, unknown and stale states.
- Each chart/table links to underlying records where authorized.
- Tenant-scoped operators cannot see other tenants' metrics.
- Cost figures reconcile to provider usage records and state currency/window.
- No secret values or sensitive command output appear in dashboard telemetry.


## Implemented execution telemetry foundation

The current backend change adds an internal, token-authenticated execution-metrics endpoint at `GET /api/v1/internal/mad/execution-metrics`. It is deliberately not a browser dashboard API and is excluded from the public OpenAPI schema. It reports only aggregate values:

- Worker heartbeat totals, fresh workers, stale workers and workers in graceful shutdown. Freshness threshold: 60 seconds.
- Queued and active execution-run counts, plus the oldest queued timestamp.
- Completed, failed and cancelled execution counts over the preceding 24 hours (UTC).
- An observation timestamp and explicit unknown/degraded states when there are no workers or a queue has no fresh worker.

The standalone worker writes a low-cardinality heartbeat at startup, while idle, during long-running execution and on shutdown. Heartbeats contain a worker identifier, idle/busy/stopping state, optional active run identifier, protocol version and timestamps. They do not contain hostnames, environment variables, tenant identifiers, prompts, command output or credentials. Heartbeat records expire after 30 days.

### Internal endpoint security

Configure `MAD_METRICS_TOKEN` as a high-entropy secret of at least 32 ASCII characters in the API environment. Send it in the `X-ODEI-MAD-Token` header from a trusted server-side operations client. The endpoint fails closed if the token is absent or invalid, does not accept browser identity tokens as an alternative, and must additionally be protected by private networking, ingress allowlists and secret rotation. Never put this token in browser code, source control, telemetry, URLs or logs.

### Current scope and non-claims

This is a first operational telemetry slice, not the complete MAD product. It does not yet provide the MAD web dashboard, MAC-managed operator identities and roles, incident lifecycle, alert delivery, integrations/deployment status, model-cost reconciliation, product analytics, or tenant-visible drill-down. Those capabilities remain gated on the MAC governance model and their authoritative data sources. A green CI run is not evidence of production monitoring or deployment.


## Deterministic alert evaluation

The internal aggregate-metrics response now includes a derived `alerts` array:
- **Critical — worker pool unavailable:** queued or active execution work exists and there are no fresh worker heartbeats.
- **Warning — worker pool degraded:** workers are stale or stopping, unless the critical no-fresh-worker rule applies.
- **Warning — queue backlog:** the oldest queued execution is at least 15 minutes old.
- **Warning — failure burst:** at least five executions failed in the rolling 24-hour window.

Each alert includes a stable ID and deduplication key, severity, firing state, observation timestamp, summary and runbook path. Evaluation uses only aggregate telemetry and excludes tenant IDs, worker IDs, prompts, artifact contents and command output. Malformed timestamps do not trigger backlog alerts.

**Operational boundary:** these are stateless firing observations, not persisted incidents. Acknowledgement, assignment, resolution/reopen history, notification delivery, alert ownership and MAC-controlled threshold configuration remain unimplemented. The baseline thresholds must be tuned against real staging workload before production paging is enabled.


## ODID-scoped operator read API

A second read path is available at `GET /api/v1/mad/execution-metrics`. It uses the normal RS256/JWKS-verified API bearer identity and requires the explicit `mad:read` access-token scope. The route does not accept a browser-supplied role, organization ID or static MAD operations token. The identity provider must explicitly grant `mad:read` to approved operator clients/identities.

Every permitted or denied request is written to the append-only audit store under the platform scope before a response is returned. If the audit store is unavailable or the audit write fails, the route fails closed. The response contains the same aggregate-only metrics and stateless alerts as the internal endpoint. It does not expose tenant drill-down or incident mutation actions.

The existing `/api/v1/internal/mad/execution-metrics` endpoint remains a separate server-to-server path protected by `MAD_METRICS_TOKEN` and private network policy. Never expose that token to browser JavaScript.

**Remaining:** this is an authenticated read API, not the MAD dashboard or complete operator authorization system. The real ODID issuer must configure and issue `mad:read`; staging authorization/audit tests, a dashboard UI, persisted incident workflows and alert delivery remain acceptance gates.


## Persisted incident lifecycle — implementation increment

The API now persists deterministic execution alerts in the `mad_incidents`
collection when the authenticated operator metrics route observes them. The
deduplication key is the incident ID; repeated observations update the active
incident rather than creating a new record. If a resolved alert fires again,
the incident reopens and its version/history advances.

Authenticated endpoints:

- `GET /api/v1/mad/incidents?include_resolved=false&limit=100` requires the
  verified `mad:read` scope and returns bounded platform incident records.
- `POST /api/v1/mad/incidents/{incident_id}/transitions` requires the
  verified `mad:incident:manage` scope. Supported actions are
  `acknowledge`, `assign`, `resolve` and `reopen`; each request supplies
  `expected_version` to prevent stale concurrent updates.

Every successful or denied read/transition is written to the append-only
platform audit store. State transitions also append an incident history item
with actor, action, timestamp and version. The compare-and-set update rejects
stale versions with HTTP 409. No tenant IDs, prompts, command output, artifact
contents, hostnames or secrets are stored in incident records.

This increment does not implement the MAD dashboard UI, external paging/email
delivery, configurable thresholds, MAC-managed role provisioning or production
incident-response staffing. The identity provider must explicitly grant
`mad:read` and `mad:incident:manage` to approved operator identities.
