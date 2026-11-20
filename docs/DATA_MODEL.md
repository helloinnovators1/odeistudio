# Canonical Data Model

This document defines logical domains, not a final ORM schema. Choose exact fields and indexes during implementation and migrations.

## Tenant and identity
- `users`: identity profile and account status.
- `organizations`: tenant boundary and organization settings.
- `memberships`: user-to-organization relation, role and status.
- `invitations`: expiring, single-use invitation records.
- `roles` / `permissions`: permission definitions and assignments.

## Projects and source
- `projects`: organization-owned project metadata.
- `repositories`: provider, external repository ID, default branch and installation reference.
- `workspaces`: project execution workspace, owner, isolation profile and expiry.
- `project_indexes`: index version, file inventory, symbols and embeddings metadata.

## Agent orchestration
- `tasks`: user goal, plan, state, approvals, owner and timestamps; tenant-scoped optimistic version.
- `task_events`: append-only task lifecycle events, uniquely sequenced per `(organization_id, task_id, version)`; never embed an unbounded event array in task documents.
- `agent_runs`: model/provider, agent profile, budgets and execution status.
- `tool_events`: tool name, validated arguments summary, result metadata, duration and policy decision; redact secrets.
- `artifacts`: patches, diffs, logs, reports and test output with access controls.
- `approvals`: requested action, risk, approver, decision and expiry.

## Platform and integrations
- `integration_connections`: provider, external account reference, status, scopes and secret reference.
- `environment_configs`: environment, service, key metadata, version and secret reference where sensitive.
- `deployments`: target, commit, build, status and provider operation reference.
- `policies`: tool, runtime, network, model and approval policies.
- `feature_flags`: scoped rollout configuration.
- `usage_records`: measured model/runtime/provider usage and cost provenance.

## Governance and operations
- `audit_events`: actor, tenant, action, target, outcome, timestamp, request/trace ID and redacted metadata.
- `incidents`: severity, owner, status, timeline and runbook.
- `service_health`: measured health checks with freshness metadata.

## Data rules
1. Every tenant-owned document has an immutable organization/tenant reference.
2. Every read/write query applies tenant authorization on the server.
3. Unique indexes include tenant scope where uniqueness is tenant-specific.
4. Use optimistic concurrency/version fields for mutable configuration and files.
5. Define retention and deletion policies for logs, artifacts and source indexes.
6. Do not store plaintext credentials, API tokens or database passwords in MongoDB.
7. Avoid storing full source files redundantly when a controlled workspace or object store is appropriate; store hashes and provenance for indexes.
8. Define backup, restore and migration strategy before production launch.
