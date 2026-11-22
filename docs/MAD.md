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
