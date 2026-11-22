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

This increment supplies the persistence service and unit tests. It does **not**
wire HTTP routes, NEXUS/MAC screens, provider-specific deployers, secret-manager
connectors, staging identity provisioning, or production infrastructure changes.
Those are explicit subsequent integration and acceptance gates; do not expose this
service as an operational API until the route-level authorization and audit tests
are in place.
