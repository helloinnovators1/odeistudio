# NEXUS Execution API and Workspace Snapshot Storage

## API boundary

The execution API is authenticated by the same verified OIDC access-token principal used by the NEXUS task API. Every operation checks active organization membership, active project access, task ownership or project-owner access, and tenant/project/task/run binding. Client-supplied roles and tenant claims are never accepted.

### Available routes

- GET /api/v1/organizations/{organization_id}/projects/{project_id}/execution/profiles — returns only the profile IDs configured by the server.
- POST /api/v1/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}/executions — accepts a bounded base64 ZIP archive, server profile ID, expected task version, and separate workspace-upload and code-execution consent booleans.
- GET .../tasks/{task_id}/executions/{run_id} — returns a lease-token-free run projection.
- GET .../tasks/{task_id}/executions/{run_id}/events — returns version-cursor-paginated run events.
- POST .../tasks/{task_id}/executions/{run_id}/cancel — records durable cancellation intent.
- GET .../tasks/{task_id}/executions/{run_id}/artifacts — returns bounded, redacted stdout/stderr to an authorized task owner or project owner.

## Approval and transaction boundary

A task must already be in approved state, and the caller must be its owner or project owner. Approval itself is restricted to the project owner by the existing task API. Execution creation compares the expected task version and atomically changes the task from approved to executing, appends its task event, creates the queued run and run event, and writes the audit event in one MongoDB transaction. A unique partial index prevents more than one active run per task.

The upload and execution consents are distinct and both must be true. The browser cannot choose an OCI image, command, runtime path, host path, environment variable, or arbitrary argv. The server resolves the profile ID from a deployment-owned registry of SHA-256 digest-pinned profiles.

## Snapshot storage

The API validates the archive with the same bounded ZIP ingestor before storing it in MongoDB GridFS. Metadata is tenant/project/task scoped and records the deterministic content-manifest digest, file count, byte count, owner identity, creation time and expiry. Raw archive bytes are not stored in the ordinary metadata document. Snapshot metadata is not removed by a TTL index because GridFS blob cleanup must happen first; the worker-side retention task removes expired blobs after confirming no active execution references them.

The snapshot digest is a manifest digest over normalized relative paths, file sizes and per-file SHA-256 hashes. It is not the ZIP byte-stream hash. The worker must re-ingest the archive in its private workspace and compare the computed digest before invoking the sandbox.

## Deployment configuration

Set EXECUTION_PROFILES_JSON to a JSON array of server-controlled profiles. Each profile requires name, image (an OCI reference pinned with @sha256:), and command (an argument array). Optional fields are timeout_seconds, memory_mb, cpus, pids_limit, tmpfs_mb, and max_output_bytes. Unknown fields, invalid profile values and unpinned images fail startup. Leave the setting empty until reviewed production image digests and commands exist; in that state execution endpoints fail closed with EXECUTION_PROFILES_UNAVAILABLE.

PyMongo 4.13 or later is required for AsyncGridFSBucket. MongoDB must be a replica set or sharded cluster because run/task/event/audit creation is transactional. GridFS blob uploads and metadata writes are separate operations (GridFS does not participate in MongoDB multi-document transactions); upload failures use compensating blob cleanup. Configure request-body limits at the ingress/proxy as well as the application; the JSON base64 payload is bounded to a 50 MiB decoded archive.

## Current limitations

The standalone worker entrypoint is now implemented as `odei-execution-worker` / `python -m odei_api.execution_worker`. It claims and renews leases, re-ingests and verifies snapshots, invokes the sandbox, polls cancellation, persists redacted bounded output, finalizes task/run states, expires exhausted attempts and cleans expired snapshot/artifact blobs. See EXECUTION_WORKER.md. It has not been deployed or run on a configured worker host.

Do not expose this API as production-ready until those gates pass and the configured OCI profile digests have been verified by the deployment owner.