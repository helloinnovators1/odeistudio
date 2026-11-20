# Deployment and Environment Strategy

## Environments
- **Local:** developer-controlled, disposable data where possible.
- **Preview:** isolated per branch/PR, non-production credentials and limited data.
- **Staging:** production-like topology with synthetic or masked data.
- **Production:** controlled changes, approvals, monitoring, backup and recovery.

## Configuration
Separate non-sensitive configuration from secrets. Validate required keys at startup and fail with actionable, non-sensitive errors. Keep environment templates free of values, for example `.env.example`; never commit populated local env files.

## Secret injection
Use a managed secret manager or KMS-backed vault. Inject secrets server-side at runtime with least privilege and rotation. Do not expose server secrets to browser bundles, client telemetry or agent prompts.

## Deployment workflow
Build immutable artifact → scan dependencies and image → deploy to preview/staging → health check → smoke/integration tests → approval → production rollout → verify metrics → rollback if defined thresholds fail.

## Provider abstraction
Represent deployment targets through adapters and capability declarations. Provider-specific deployment, logs, domains and environment operations must be implemented only when the official API and granted permissions support them. Vercel remains a separate integration boundary.

## Operations
Document service ownership, health endpoints, logs, metrics, alerts, backup schedule, recovery time/point objectives, incident contacts and rollback procedure before production launch.
