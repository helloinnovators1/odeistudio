# MAC environment configuration and promotion lifecycle

## Implemented service boundary

`MongoMacRevisionEnvironmentStore` provides versioned environment configuration records for
`development`, `staging`, and `production`. It supports draft creation and editing,
author submission, approval by a distinct verified identity, compare-and-set promotion,
and rollback as a new reviewable draft. Existing revision history is retained.

The store is deliberately separate from deployment execution. Promotion records the
approved active configuration version; it does not contact a cloud provider, mutate
infrastructure, or claim a deployment succeeded. A deployment adapter must consume
only an approved/promoted revision and independently verify its authorization and
provider result before updating deployment state.

## Security properties

- Callers must pass the verified issuer/subject-derived actor, never a browser role.
  API routes must resolve `mac:environment:manage` for draft changes and rollback,
  `mac:deployments:approve` for approval/promotion, and audit every decision.
- The draft author cannot approve their own revision.
- Writes use revision and active-version compare-and-set preconditions.
- Secret material is not accepted. Sensitive configuration keys may contain only
  opaque `secret://` references to an external vault/KMS integration.
- Configuration is bounded to 100 scalar entries; values are bounded.
- Rollback creates a new draft from an approved historical configuration; it never
  rewrites history or directly changes the active version.

## Persistence and operational gates

The collection must be provisioned with the application MongoDB database. Database
credentials should permit application writes while operational audit collections
remain insert-only. MongoDB backups and point-in-time recovery are required before
production use.

The authenticated API is mounted under `/api/v1/mac/environments`. It exposes
read, draft create/edit, author submission, distinct-identity approval, compare-and-set
promotion, and rollback-draft operations. Every successful and failed lifecycle
operation is written to the append-only platform audit store. Permissions are resolved
from the deployment-owned issuer/subject registry, never from browser-supplied roles.

The NEXUS panel now includes a MAC environment governance view and browser transport
for loading revisions, saving drafts, submitting, approving, promoting the active
configuration pointer, and creating rollback drafts. Browser controls are convenience
only: the API remains authoritative for every permission and lifecycle transition.

This increment now uses a separately indexed `mac_environment_revisions` collection for runtime history. The runtime updates only active/latest pointers in environment metadata; revision configuration and provenance are stored as separate documents keyed by environment/version. A pre-existing embedded `versions` array is retained unchanged as a frozen recovery copy until a separately reviewed archival/removal procedure is approved. Lifecycle metadata changes are coordinated with revision writes by the API's MongoDB transaction. Promotion changes the approved active configuration pointer only; it is not evidence that a cloud deployment ran. No automatic pruning is enabled. A formally approved retention/archival policy, immutable backup verification and restore drills remain required before production history can be treated as fully governed.


## Additional hardening and explicit production boundaries

- Sensitive-key detection covers secret, password/passwd, token, API/access/private/signing/encryption keys and credential names. Every matching value must be a `secret://` reference regardless of its JSON type; plaintext strings, numbers, booleans, null and objects are rejected.
- Rollback expected-version values use strict integer validation; JSON booleans are rejected.
- Successful MAC lifecycle mutations and their success audit events now share one MongoDB transaction/session. If the audit insert fails, the configuration mutation is rolled back. Failure/denial audit records are written separately because the failed state change must not commit. This requires a replica set or sharded MongoDB deployment with transaction support; readiness checks explicitly reject standalone MongoDB.
- Runtime reads and writes now use `mac_environment_revisions`; new history no longer grows the legacy embedded array. The unique `(environment, version)` index prevents duplicate revision identities. Startup fails closed if a legacy environment's revision sequence has not been backfilled completely. Legacy embedded arrays are retained unchanged as recovery copies and are not automatically pruned.
- `secret://` validation is not secret resolution. A production secret-manager adapter must authorize each reference against the environment/provider, resolve values only inside the server-side deployment worker, prevent values from entering API responses/logs/audit/events, and support rotation/revocation.
- Durable deployment attempts, request idempotency, worker leases, health-verification state, and provider-neutral worker orchestration are implemented. Concrete provider deployment adapters, an external secret-manager adapter, provider-specific health probes, provider-side rollback, and a hardened worker deployment remain unconfigured. No cloud deployment is performed by this lifecycle API.


### Atomicity verification

`apps/api/tests/test_mac_store_mongodb_integration.py` exercises the MAC route mutation helper against a real MongoDB replica set. It verifies that a simulated audit insert failure leaves no environment revision behind, and that a successful mutation commits exactly one environment revision and one corresponding audit event. The API CI MongoDB integration job runs this test alongside the task/execution transaction integration tests.


## Durable deployment-attempt ledger (implemented; provider execution pending)

The API now accepts an authenticated deployment request at
`POST /api/v1/mac/environments/{environment}/deployments` and returns
`202 Accepted` with a durable queued attempt. The request requires
`mac:deployments:approve`, a positive strict-integer revision, a bounded
provider identifier, and an idempotency key. Only revisions already in
`approved` or `promoted` state are eligible. Repeating the same key and
same request returns the existing attempt; reusing the key for a different
environment/revision/provider is a conflict.

The attempt ledger uses a separate MongoDB collection and indexes for unique
environment-scoped idempotency, environment history, and worker queue ordering.
Its state transitions are compare-and-set guarded and worker leases expire:

- `queued -> running`: one worker claims the attempt with a bounded 15–900 second lease.
- `running -> running`: the owning worker renews its lease with a heartbeat.
- A crashed worker's expired lease can be reclaimed by another worker, subject to a bounded attempt count. The new worker replaces the old owner; stale workers cannot heartbeat, complete or fail the reclaimed attempt.
- `running -> succeeded`: the current lease owner records a positive verification.
- `running -> verification_failed`: provider execution completed but verification
  did not pass.
- `running -> failed`: the owning worker records an execution failure.

The authenticated read endpoint is
`GET /api/v1/mac/environments/{environment}/deployments/{attempt_id}` and
requires `mac:read`. Both request and read actions are audited. Attempt records
store provider deployment identifiers and bounded summaries, not resolved secret
material or provider logs.

**Not yet implemented:** deployment and operation of the worker process, concrete cloud-provider adapters,
production secret-manager integration, provider-specific health probes, durable retry/backoff
orchestration, automatic compensation/rollback, and deployment UI. The provider-neutral
worker orchestration contract is implemented but must be wired to reviewed adapters and
run in a hardened worker deployment. A queued record is not a deployment;
neither API acceptance nor a worker claim is evidence that infrastructure changed.
Provider credentials and a concrete provider/environment configuration are required
before a real deployment can be executed safely.


### Worker lease and crash-recovery contract

The deployment store now persists `attempt_count` and `lease_expires_at`.
`claim()` uses a single MongoDB compare-and-set update to claim a queued
attempt or reclaim a running attempt whose lease has expired. The default lease
is 120 seconds; callers may request 15–900 seconds and at most 20 attempts
(the default maximum is five). `heartbeat()` can renew only a currently valid
lease held by the same worker. Completion and failure require that same
unexpired lease. Reclaiming changes the worker owner, fencing out the old
worker from subsequent ledger writes.

This provides durable lease ownership and crash recovery in the ledger; it is
not a substitute for provider-side idempotency. A worker must still use a stable
provider idempotency token and reconcile ambiguous provider outcomes before
retrying, otherwise a timeout after a provider accepted a request could create
duplicate infrastructure changes. No worker process or provider adapter is
configured by this change.


### Provider-neutral worker orchestration (implemented; adapters not provisioned)

`apps/api/odei_api/services/mac_deployment_worker.py` implements a provider-neutral
worker runner. It atomically claims the oldest queued attempt, loads the approved
revision, resolves only sensitive-key `secret://` references through an injected
environment/provider-aware secret resolver, and calls an injected provider adapter.
Resolved secret material exists only in worker memory and is never included in
ledger summaries or API responses. Provider exceptions are deliberately sanitized
before persistence.

The adapter receives the stable deployment idempotency key. Once the provider
returns a deployment identifier, the worker persists that identifier in the
attempt ledger before health verification. Replaying an idempotency key from
the same authenticated actor returns the existing attempt; reusing it for a
different actor or request is rejected. The lookup-before-insert path works
inside the same MongoDB transaction as the request audit; a concurrent unique-key
race is rejected for safe client retry rather than reading inside an aborted transaction. If the worker crashes after that point,
a reclaimed worker resumes verification against the existing provider deployment
instead of issuing another apply. Long-running secret resolution, deployment and
verification calls renew the worker lease; lease loss fences the worker from
subsequent ledger writes. Verification failures and timeouts are recorded as
`verification_failed`, retaining the provider deployment identifier for
operator reconciliation.

This is an orchestration interface and tested worker implementation, not a
configured production service. No concrete provider adapter, secret-manager
adapter, hardened worker runtime, credentials, network policy or provider
environment has been supplied. No cloud infrastructure has been modified.

## Revision-history runtime cutover (implemented; operator migration required)

`apps/api/odei_api/services/mac_environment_migrations.py` adds a
transaction-scoped, repeatable backfill from legacy embedded `versions` arrays
into `mac_environment_revisions`. It creates a unique `(environment, version)`
index plus an environment/time history index, assigns deterministic revision
IDs, validates sequence continuity against `latest_version`, and compares
pre-existing target documents before accepting a retry. A divergent target
raises `MacRevisionMigrationConflict`; neither side is overwritten.

The backfill must be invoked by an operator-controlled migration runner inside a MongoDB replica-set/sharded transaction using the same session for source reads, target reads and inserts. It returns copied/already-present counts. Runtime now reads/writes the separate revision collection. Before deploying this runtime against a database containing legacy environments, operators must arrange a write freeze (or formally approved consistency barrier), take and verify a backup, run the dry run, apply the backfill, reconcile every environment's revision count and sequence, then deploy. Startup validates that every environment has the complete `1..latest_version` sequence and fails closed rather than serving incomplete history. The embedded array remains as a recovery copy; it is not automatically deleted. Do not enable revision pruning until a separately reviewed retention/archival and restore policy exists. Immutable revision content remains available for approvals, rollback, audit correlation and regulatory retention.

### Running the backfill command

Install the API package in the deployment environment, set the intended
`MONGODB_URI` and `MONGODB_DATABASE`, and run from the API package environment:

```sh
odei-mac-revision-migration
```

The default is a dry run: it validates every legacy environment and revision,
checks existing target records for exact consistency, and reports how many
revision documents would be copied without inserting them. After taking and
verifying a database backup, arranging a write freeze (or another formally
approved consistency barrier), reviewing the dry-run output, and confirming
replica-set/sharded transaction support, an authorized operator can explicitly
apply:

```sh
odei-mac-revision-migration --apply
```

The dry run performs no database writes or index DDL. With `--apply`, the
command creates the target indexes and runs the backfill in a MongoDB
transaction. It exits non-zero on malformed history, gaps, duplicate sequence
numbers, target conflicts, or database/transaction errors. It does not remove legacy embedded history, alter active-version pointers, or deploy infrastructure. The runtime cutover is enabled in this branch, so the operator must complete and reconcile this migration before deploying the new API against any database with legacy environment records. Re-run the dry run after application and verify all environment/version sequences before deployment.


### Deployable worker process entry point (implemented; adapters/deployment pending)

The API package exposes `odei-mac-deployment-worker`, implemented in
`apps/api/odei_api/mac_worker.py`. It initializes the separate revision store
(and refuses to run against incomplete legacy history), initializes the durable
deployment ledger, loads trusted provider and secret-resolver factories, and
polls the queue until interrupted. It supports `--once` for a single-attempt
smoke run and a bounded `--poll-interval` for continuous operation. Logs include
only attempt identifiers and final state; adapter exception text and resolved
secret values are not logged.

The worker requires deployment-controlled configuration:

- `ODEI_MAC_PROVIDER_FACTORY=package.module:factory`: returns a non-empty
  mapping of provider names to reviewed `deploy/verify` adapters.
- `ODEI_MAC_SECRET_RESOLVER_FACTORY=package.module:factory`: returns an
  environment/provider-authorized secret resolver.
- `ODEI_MAC_WORKER_ID`: optional stable worker identity; defaults to hostname
  plus process ID.
- The normal API MongoDB settings must point to the same replica-set/sharded
  database used by the API and migration runner.

Run one queued attempt with:

```sh
odei-mac-deployment-worker --once
```

Run the continuous worker with:

```sh
odei-mac-deployment-worker --poll-interval 2
```

Build the non-root worker image from the repository root:

```sh
docker build -f apps/api/Dockerfile.mac-worker -t odei-mac-worker:local apps/api
```

The image runs as UID/GID 10001, uses SIGTERM as its stop signal, and starts
only the worker entry point. Supply MongoDB, provider-factory and secret-resolver
configuration through the deployment platform's secret/config injection; do not
bake credentials or adapter modules into the image.

This is a packaged, fail-closed process entry point—not proof of an operational
worker deployment. Provider and secret-manager factory modules must be reviewed,
installed and configured by the deployment owner; credentials, network policy,
resource limits, process supervision, health monitoring and staging acceptance
remain external deployment gates. No cloud provider adapter or real deployment
is supplied by the generic worker entry point.
