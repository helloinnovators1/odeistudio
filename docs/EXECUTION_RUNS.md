# NEXUS Durable Execution Runs

## Scope
This increment adds durable run persistence and worker leases on top of the OCI sandbox foundation. It is not a public execution API or production worker deployment. Workers are trusted server-side processes; the model and browser never receive lease tokens or select runtime images or flags.

## Run creation contract
A run binds an organization, project, approved task, server-registered profile identifier, immutable workspace snapshot SHA-256, and bounded argv vector. It starts queued at version zero. Before creating a run, the API must verify active organization and project membership, task ownership and approval, explicit execution approval, snapshot provenance, and profile availability. Those checks are not delegated to this store.

## Worker lease contract
- claim_next atomically leases the oldest available queued run or reclaims a run whose prior lease expired.
- A random 128-bit lease token and worker identity bind each lease. The token remains server-side and must never be returned to browser clients or logged.
- A worker must heartbeat before expiry. Expired leases cannot be renewed or used for state transitions.
- Each lease acquisition increments attempt count and version and appends an ordered event in the same MongoDB transaction.
- Worker state changes compare organization, run, worker, lease token, version, status and unexpired lease.
- Cancellation is durable intent. A running worker must observe it, terminate the sandbox, confirm cleanup, and then finalize as cancelled. A queued run can be cancelled immediately.
- Run events and audit events commit transactionally with state mutations.

## Explicit remaining gates
This increment does not yet provide HTTP routes, API authorization/approval checks, immutable snapshot ingestion or object storage, worker process/queue deployment, retry exhaustion handling, sandbox cancellation wiring, artifact/log storage, artifact retrieval, output secret redaction, or MAD metrics/alerts. Do not enable user execution until these layers and crash/restart, tenant-isolation, lease-race and cancellation-cleanup tests are complete.


## Snapshot ingestion increment

A bounded ZIP snapshot ingestor is now implemented in services/workspace_snapshots.py. It rejects traversal, absolute and non-portable paths, duplicate normalized paths, symlinks and special files, file/directory conflicts, encrypted or unsupported entries, oversized archives/files and excessive compression ratios. It extracts only to a fresh worker-owned directory, uses exclusive no-follow file creation where supported, and calculates a deterministic content-manifest digest. See WORKSPACE_SNAPSHOTS.md. Authenticated upload, durable object storage, explicit consent and tenant-scoped API integration remain separate gates.
