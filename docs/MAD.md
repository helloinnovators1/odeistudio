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
