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


## Implemented authorization foundation

The repository now includes a server-configured platform operator registry and a read-only access endpoint:
- Configuration: `MAC_PLATFORM_OPERATORS_JSON`, a deployment-owned JSON array of exact `issuer`, `subject` and `roles` assignments.
- API: `GET /api/v1/mac/access`, requiring a normal RS256/JWKS-verified ODEI access token. Roles are resolved only from the server configuration using the verified issuer and subject; token claims, browser parameters and organization membership roles do not grant platform privileges.
- Roles currently defined: `platform_owner`, `super_admin`, `infrastructure_admin`, `security_admin` and `read_only_auditor`.
- The response returns the resolved role names and the corresponding permission identifiers. The reusable `require_mac_permission` guard fails closed when a permission is absent.

The current baseline permission mapping is:

| Server-assigned role | Permissions |
|---|---|
| `platform_owner` | All current MAC permissions, including identity administration |
| `super_admin` | MAC read, environment, secrets, providers, security, deployment approval and audit; excludes identity administration |
| `infrastructure_admin` | MAC read, environment, provider and deployment approval |
| `security_admin` | MAC read, secrets, security and audit |
| `read_only_auditor` | MAC read and audit read only |

Assignments use exact issuer/subject strings and subjects must fit the audit identity identifier contract. A signed token scope or browser-provided role cannot add to this permission set.
- Successful and denied access checks are written to the append-only audit store under the platform scope. If audit storage or the audit write is unavailable, access fails closed.

Example shape (replace all illustrative values through the deployment's approved configuration process; do not use this example as a real assignment):

```json
[
  {
    "issuer": "https://identity.example.test/",
    "subject": "registered-operator-subject",
    "roles": ["platform_owner"]
  }
]
```

An empty registry disables MAC access and returns a configuration error. There is deliberately no self-service endpoint to grant platform roles. Initial assignments and role changes must be performed by an authorized deployment/configuration owner through a reviewed, audited change. Real issuer provisioning, scope/identity acceptance, role assignment operations, dual-control approvals, and access-review workflows remain outstanding.

This is an authorization foundation, not a complete MAC console. It does not yet implement environments, secret references/vault, provider adapters, deployments, DNS, databases, model governance, incident management, or rollback orchestration. Every future privileged route must call the server-side permission guard, write an audit event, enforce approval policy where required, and fail closed on policy/audit failure.
