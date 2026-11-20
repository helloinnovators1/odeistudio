# Master Admin Console (MAC) — Product Requirements

## Mission
The MAC is the overall management and configuration authority of ODEI Studio. It is the single administrative control plane for platform configuration and supported external services, subject to provider API capabilities and secure authorization.

## Required modules
1. **Command overview:** platform status, pending approvals, integration health, configuration drift, alerts and recent administrative activity.
2. **Environment manager:** environment inventory (development, preview/staging, production and custom); variable groups; service/target scoping; validation; versioning; controlled promotion; deployment synchronization; rollback where supported.
3. **Secrets vault:** encrypted secret storage or external secret-manager integration; key rotation; version metadata; access policies; masked values; secret references; audit events; no plaintext retrieval after write by default.
4. **Hosting control centre:** provider accounts, projects/sites, deployment targets, build configuration, environment injection, logs, resource status and supported lifecycle operations. Vercel is outside this general hosting scope and remains separate.
5. **Domains and DNS:** registrar accounts, domain inventory, DNS zones/records, verification, SSL status, expiry monitoring and deployment mapping, subject to provider support.
6. **Database management:** connection configuration, health checks, migration status, backup/restore orchestration and access policy. Never expose database passwords in UI telemetry or logs.
7. **AI and model governance:** provider credentials, model catalog, routing policies, budgets, quotas, rate limits, safety policies and evaluation configuration.
8. **Git and source control:** GitHub App connections, repository installation scopes, webhook status, branch policies and integration health.
9. **Identity and tenants:** users, organisations, memberships, roles, MFA policy, invitations, suspension and tenant-level settings.
10. **Agent and tool governance:** agent definitions, tool allowlists, execution permissions, approval gates, runtime limits, network policy and kill switch.
11. **Security and audit:** immutable or tamper-evident event trail, privileged action approvals, access reviews, incident response and export.
12. **Platform settings:** feature flags, service endpoints, retention policies, notification channels, regional settings and maintenance controls.

## Environment variable lifecycle
- Define a variable by key, owning service, environment, deployment target, sensitivity, validation rule and required/optional status.
- Support draft → validate → approve → publish → verify → rotate/rollback lifecycle.
- Show variable names and metadata to authorized operators; mask values after submission.
- Secret values must be encrypted using a managed KMS-backed vault or stored in an external secret manager. MongoDB stores references, versions and metadata only.
- Inject values server-side into the relevant runtime using short-lived access where available. Never send production secrets to client-side JavaScript or model prompts.
- Support provider-specific sync adapters and report partial failures; never claim a successful sync without provider confirmation.
- Require stronger approval for production, authentication, encryption, database and provider credentials.

## Hosting provider integration contract
Each provider adapter declares: authentication method; required scopes; account discovery; supported resources; configuration operations; deployment operations; environment-variable support; domain/DNS support; logs/metrics support; webhook support; rate limits; regional constraints; and unsupported capabilities.

Operations should be idempotent where possible and produce a normalized result, provider request ID, audit event and clear error. Destructive operations require confirmation and may require a second approver.

## Roles
Suggested roles: Platform Owner, Super Admin, Infrastructure Admin, Security Admin, Organization Admin, Developer and Read-only Auditor. Permissions must be granular and server-enforced. Separate the ability to configure a secret from the ability to reveal/use it.

## MAD relationship
The MAD is the dashboard within the MAC ecosystem for operational and executive visibility. It reads from authoritative telemetry and audit sources; it does not become a parallel source of configuration truth.

## Acceptance criteria
- Admins can see all connected providers and their actual connection health.
- Each environment variable is scoped, versioned and audited.
- Secret values are never exposed after storage through normal read APIs.
- Provider capability differences and unsupported operations are explicit.
- Production changes have approval and rollback/recovery paths.
- All privileged operations are tenant-aware, role-checked and auditable.
- Vercel is not silently included in the general non-Vercel hosting control plane.
