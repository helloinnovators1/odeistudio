# MAC environment configuration and promotion lifecycle

## Implemented service boundary

`MongoMacEnvironmentStore` provides versioned environment configuration records for
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

This increment still does **not** provide an external secret-manager connector,
provider-specific deployment execution, staging identity provisioning, or production
infrastructure changes. Promotion changes the approved
active configuration pointer only; it is not evidence that a cloud deployment ran.
The current revision history is embedded in one environment document, so a separate
revision collection and retention/archival policy are required before unbounded
production history can be supported safely.


## Additional hardening and explicit production boundaries

- Sensitive-key detection covers secret, password/passwd, token, API/access/private/signing/encryption keys and credential names. Every matching value must be a `secret://` reference regardless of its JSON type; plaintext strings, numbers, booleans, null and objects are rejected.
- Rollback expected-version values use strict integer validation; JSON booleans are rejected.
- The audit store is append-only at the application API, but the current MAC route performs the configuration mutation and audit append as separate operations. If audit persistence fails after a successful mutation, the caller can receive a 503 even though the mutation committed. This is not an atomic mutation-plus-audit transaction and must be corrected before production governance relies on audit completeness.
- Environment revisions remain embedded in one document. Move them to a separately indexed revision collection with retention/archival before the history can grow without bound.
- `secret://` validation is not secret resolution. A production secret-manager adapter must authorize each reference against the environment/provider, resolve values only inside the server-side deployment worker, prevent values from entering API responses/logs/audit/events, and support rotation/revocation.
- Provider deployment adapters, durable deployment attempts, idempotency, health verification, and provider-side rollback are not yet implemented. No cloud deployment is performed by this lifecycle API.
