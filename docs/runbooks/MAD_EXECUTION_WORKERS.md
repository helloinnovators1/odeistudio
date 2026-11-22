# MAD Execution Worker Runbook

## Scope
Use this runbook for the aggregate MAD alerts:
- `mad.execution.worker_pool_unavailable`
- `mad.execution.worker_pool_degraded`
- `mad.execution.queue_backlog`
- `mad.execution.failure_burst`

This runbook is operational guidance, not proof that a production worker fleet or alert-delivery integration is deployed.

## Initial triage
1. Confirm the alert observation timestamp and compare it with the current UTC time.
2. Query the protected MAD metrics endpoint from an approved server-side operations host. Never place `MAD_METRICS_TOKEN` in a browser, URL, source file or chat.
3. Check API and MongoDB availability, then inspect worker process/service health and recent deployment changes.
4. Verify that the worker can reach MongoDB and its configured container runtime, and that its approved immutable execution profiles are available.
5. Check host disk capacity, workspace permissions, container runtime health and the worker's restricted network policy.

## Worker pool unavailable
- Confirm whether worker heartbeats are absent or older than the 60-second freshness window.
- Inspect the worker service logs locally; do not copy prompts, environment values, credentials or command output into MAD telemetry.
- Restart only through the approved service manager and change process. Do not launch an unreviewed worker or loosen sandbox isolation to restore capacity.
- Verify a fresh heartbeat and a controlled staging execution before declaring recovery.

## Degraded workers
- Identify stale or stopping worker processes through the infrastructure's authenticated inventory; the MAD aggregate endpoint intentionally does not disclose worker IDs.
- Check shutdown/restart loops, host pressure and database connectivity.
- Replace unhealthy capacity through the approved immutable image and deployment process.

## Queue backlog
- Compare queue age with worker availability and execution profile capacity.
- Check lease expiry, exhausted attempts, worker throughput and snapshot/artifact storage health.
- Do not manually mutate execution-run documents or replay jobs outside the supported lease protocol.

## Failure burst
- Review failure categories and run-level audit records under the applicable tenant authorization.
- Distinguish user-code failures, sandbox timeouts, infrastructure faults and policy denials.
- Do not expose stdout/stderr or workspace content in shared dashboards or alert notifications.

## Recovery and escalation
- Record incident owner, affected service, start/end times, actions and evidence in the organization's approved incident system.
- Confirm the alert condition clears on fresh metrics and run a controlled staging execution.
- Escalate suspected credential exposure, tenant isolation failure, sandbox escape or unauthorized network access immediately to the security owner.
- Preserve audit records and follow the approved incident-retention policy.

## Safety constraints
Never disable network restrictions, mount host credentials, use mutable/unverified images, broaden worker privileges, or bypass approval/audit controls as a troubleshooting shortcut. Production changes require the platform's approved change and rollback process.
