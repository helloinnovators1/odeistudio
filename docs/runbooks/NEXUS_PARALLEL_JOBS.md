# NEXUS Parallel Jobs Runbook

## Purpose and execution model

NEXUS parallel job groups orchestrate execution runs that have already been created through the authenticated NEXUS execution API. The parallel worker is not an alternate code-execution API: it accepts only a reference to an existing execution run, verifies the organization, project and requesting identity, then observes the authoritative execution lifecycle.

Two separately supervised processes are required:

1. `odei-execution-worker` claims approved execution runs and performs sandbox execution using the configured immutable execution profiles and container runtime.
2. `odei-parallel-worker` claims durable parallel jobs, renews leases, restores checkpoints, propagates cancellation to the referenced execution run, and records the orchestration outcome.

The API process must be configured with MongoDB and the same tenant-scoped execution/job collections. Do not run either worker inside the browser-facing API process.

## Required configuration

### API
- `MONGODB_URI` and `MONGODB_DATABASE`
- Production identity issuer, audience, JWKS URL and allowed client configuration
- Durable audit storage and the existing NEXUS execution API configuration

### Execution worker
- `MONGODB_URI` and `MONGODB_DATABASE`
- `EXECUTION_RUNTIME_PATH`: approved OCI-compatible runtime executable
- `EXECUTION_WORKSPACE_ROOT`: dedicated, writable, non-symlink workspace root
- `EXECUTION_PROFILES_JSON`: approved immutable sandbox profiles
- Optional `EXECUTION_WORKER_ID`

### Parallel worker
- `MONGODB_URI` and `MONGODB_DATABASE`
- Optional `PARALLEL_JOB_WORKER_ID` (unique, stable per process)
- Optional `LOG_LEVEL`

Never place provider secrets, model credentials or raw tokens in job payloads or checkpoints. Job payloads are limited to the execution-run reference and the requester identity is stamped server-side by the API.

## Start and verify

1. Provision MongoDB indexes using the API and worker initialization paths before accepting traffic.
2. Start the API with production authentication, audit persistence and the required MongoDB database.
3. Start at least one `odei-execution-worker` process on a dedicated execution host with the approved container runtime and restricted network policy.
4. Start at least one `odei-parallel-worker` process. Use a distinct worker ID for each concurrent process.
5. Confirm fresh worker heartbeat records in `execution_worker_heartbeats`; the MAD aggregate worker metrics include both worker classes.
6. Submit a staging execution using the normal NEXUS flow, including explicit workspace-upload and execution consent and owner task approval.
7. Create a parallel job group referencing that execution run. The API rejects references outside the caller's organization/project or created by another requester.
8. Verify job state transitions, checkpoint hashes, execution-run terminal state and audit events. Do not inspect raw checkpoint or artifact contents through operational dashboards.

## Lifecycle and recovery

- Workers claim jobs with an atomic, expiring lease. Only the worker holding the current lease token may heartbeat, checkpoint, retry or finalize.
- The parallel worker periodically renews its lease while it polls the existing execution-run store.
- Checkpoints contain only the execution-run ID, last observed run version and status. On restart the worker re-reads the authoritative run and resumes polling; the checkpoint is not treated as the source of truth.
- A parallel-group cancellation marks queued, dependency-blocked and leased jobs for cancellation. Pending jobs are made claimable so the worker can forward cancellation to their associated execution runs; active jobs are stopped through the existing execution-run lifecycle and execution worker. Task/run state is updated through the existing transactional execution store.
- Transient execution-state storage errors schedule bounded exponential retries. Retries stop at the configured job attempt limit. Expired leases are reclaimed; cancellation requests are honored instead of re-queuing a cancelled job.
- A process shutdown releases a claimed job for retry; it must not be interpreted as a user cancellation.
- A lost lease is terminal for that worker attempt. Never attempt to finalize or overwrite a job after another worker has reclaimed it.

## Triage

### Queue is growing
- Confirm both worker classes are running and have fresh heartbeats.
- Check MongoDB connectivity, queue age, expired leases, retry counts and approved execution profile capacity.
- Confirm the execution worker can reach the container runtime and its workspace root is writable.
- Do not manually edit job or execution documents to force progress.

### Jobs repeatedly retry
- Inspect restricted worker diagnostics by error class and correlation/job ID only.
- Check database availability and whether the referenced execution run still exists.
- Confirm that execution runs are not stuck in a nonterminal state because the execution worker is offline.
- Do not increase retry limits or lease durations without staging evidence.

### Cancellation does not complete
- Verify the parallel job still has a live lease and the execution worker is healthy.
- Confirm the run's `cancel_requested` flag and subsequent terminal event.
- Never kill a worker process or mutate the database as the first response; use the normal service manager and preserve lease recovery.

### Tenant or requester mismatch
- Treat this as a security event. The API and worker must reject a referenced run that does not match organization, project and stamped requester identity.
- Preserve audit records and escalate immediately. Do not retry with relaxed authorization.

## Worktree merge-back boundary

The repository currently contains a conflict-detecting local merge-back primitive using an expected-base compare-and-swap update. It is intentionally not invoked by the execution-run bridge yet: project records do not currently provide a trusted local repository/worktree mapping, and the execution-run result does not yet carry a verified worker commit. Do not merge arbitrary client-supplied commit IDs or filesystem paths. Production merge-back must remain disabled until a trusted repository adapter supplies the project-bound repository, expected base, worker commit and approval policy, with conflict/recovery tests.

## Rollback and shutdown

1. Stop accepting new parallel job groups through the approved change process.
2. Send graceful termination to the parallel worker; it releases its current lease for retry.
3. Allow the execution worker to finish or use the authenticated execution cancellation endpoint for approved cancellation.
4. Verify no active worker leases remain before changing MongoDB indexes or collection schemas.
5. Roll back worker binaries independently from the API. Keep schema changes backward-compatible until all worker versions are drained.
6. Confirm fresh heartbeats and one controlled staging execution before reopening the queue.

## Security invariants

- No browser-facing worker endpoint.
- No arbitrary shell command, workspace path, repo path, credentials or provider configuration in parallel job payloads.
- No plaintext secrets in MongoDB job metadata or checkpoints.
- Organization, project and requester bindings are checked before observing a run.
- Lease token, version and expiry are required for worker mutations.
- Audit and event records remain durable; logs contain error classes and IDs, not prompts, source files, artifacts or secrets.
- Do not disable sandbox network isolation, approval checks or audit requirements to restore throughput.
