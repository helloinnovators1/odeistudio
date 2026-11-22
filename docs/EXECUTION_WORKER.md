# NEXUS Execution Worker Operations

## Process boundary

The worker is a separate, trusted server-side process. It is not started by the FastAPI web process and does not expose an HTTP listener. Install the API package and start the console entrypoint `odei-execution-worker` (or `python -m odei_api.execution_worker`) under a dedicated service account or isolated worker deployment.

Do not run the worker on the user's desktop. Do not mount a Docker socket, host home directory, cloud credential directory, or application secrets into execution containers. The worker host must have a reviewed OCI runtime, an isolated private workspace root, network egress policy, resource monitoring and access to the MongoDB replica set.

## Required configuration

- MONGODB_URI and MONGODB_DATABASE: the same transaction-capable MongoDB deployment used by the API.
- EXECUTION_PROFILES_JSON: exactly the same reviewed, server-owned JSON profile registry as the API. Images must use immutable SHA-256 digests; commands and limits are deployment-owned.
- EXECUTION_RUNTIME_PATH: absolute path to the approved OCI runtime executable on the worker host.
- EXECUTION_WORKSPACE_ROOT: private worker-owned directory for disposable snapshot extraction; it must not be shared with unrelated services or user files.
- EXECUTION_WORKER_ID: optional stable worker identifier. If omitted, the process creates a random identifier at startup.

Example service invocation after package installation:

```sh
odei-execution-worker
```

## Worker lifecycle

1. Atomically lease the oldest available run, increment its attempt and version, and retain the lease token only in worker memory.
2. Fetch the referenced GridFS archive and verify organization, project, task and manifest-digest metadata.
3. Re-ingest the archive into a new private direct-child workspace and recompute the content-manifest digest. Reject and clean up mismatches.
4. Transition the run to running and invoke only the server-registered digest-pinned OCI profile through the shell-free sandbox runner.
5. Renew the lease while execution is active and poll durable cancellation intent. Cancelling the worker coroutine invokes the sandbox cleanup path, which terminates the process and removes the container.
6. Transition to collecting, redact known secret patterns, and persist bounded stdout/stderr to separate GridFS buckets.
7. Atomically finalize the run, append its event and audit record, and transition the task from executing to validating, failed or cancelled.
8. Reclaim expired leases. Mark attempts exhausted as failed. Periodically delete expired snapshots and artifacts only after confirming their run is no longer active.

## Operational controls and limits

Worker logs include run identifiers and exception classes, not lease tokens, prompts, environment values or raw output. Container output is bounded by the profile. Artifact retrieval is tenant/project/task/run authorized and returns redacted output. Artifact retention defaults to 30 days; snapshot retention defaults to 7 days. Tune these policies against legal, security and product requirements before production.

MongoDB GridFS is not transaction-compatible. Blob upload and metadata insertion are separate operations with compensating cleanup; the approved-task-to-run, task/run event and audit writes themselves use a MongoDB transaction. Configure backups and orphan-blob reconciliation for GridFS.

Successful sandbox completion moves the task to validating; it does not mark the task completed. A separate validation/review and user-acceptance workflow must finish before task completion. This worker does not implement self-modifying repair loops or unrestricted network access.

## Production readiness gates

Verify the exact OCI runtime, digest-pinned images, resource isolation (prefer a hardened runtime such as gVisor/Kata/microVM where supported), rootless execution, filesystem mount behavior, worker host patching, network policy, MongoDB backup/restore, lease expiry and crash recovery, cancellation races, retention cleanup, artifact redaction, MAD metrics/alerts and incident response. Execute the full test matrix and deployment acceptance suite against the actual worker host. Do not mark the service production-ready based only on unit tests.