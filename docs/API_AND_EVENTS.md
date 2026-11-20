# API and Event Contracts

## API conventions
- Version public APIs under `/api/v1` until a deliberate versioning strategy is adopted.
- Use JSON request/response bodies, consistent error envelopes and stable resource identifiers.
- Authenticate every non-public endpoint and authorize every resource operation server-side.
- Validate request schemas, size limits, pagination bounds and content types.
- Use idempotency keys for retryable create/apply/deploy operations.
- Include request/trace IDs in responses and logs.
- Never return secret values or internal stack traces.

## Implemented protected identity routes

| Method | Route | Authorization and behavior |
|---|---|---|
| GET | `/api/v1/auth/me` | Requires a verified RFC 9068-style bearer access token; returns issuer and subject only. |
| GET | `/api/v1/organizations/{organization_id}/membership` | Requires the same verified identity and an active server-side membership record matching organization ID + issuer + subject. Returns only organization ID and role. |

Membership records live in MongoDB collection `organization_memberships`. The endpoint does not accept tenant or role claims from the browser. Missing membership storage returns 503; a valid identity without active membership returns 403. Malformed membership records fail closed. Successful lookups, missing-membership denials and malformed-record failures are appended to the MongoDB `audit_events` collection before the response is returned. If the audit writer is unavailable or an append fails, the route returns 503 rather than returning an unaudited authorization result. The API initializes audit indexes during startup when MongoDB is configured. The organization-membership route is one narrow authorization hook. The project-scoped NEXUS task API also writes task-create, approve and cancel audit events in the same MongoDB transaction as the task state and lifecycle events; any audit insert failure rolls back the task mutation. These transactional task operations require a MongoDB replica set or sharded cluster. This is not yet a complete audit trail: task reads and some denial paths, companion pairing/revocation, authentication outcomes, tool executions and audit query/export are not comprehensively covered. Production role vocabulary, membership provisioning and database-level immutability remain outstanding.

## Suggested resource groups
- `/auth`, `/users`, `/organizations`, `/memberships`
- `/projects`, `/repositories`, `/workspaces`
- `/tasks`, `/tasks/{id}/plan`, `/tasks/{id}/approve`, `/tasks/{id}/cancel`
- `/tasks/{id}/events`, `/tasks/{id}/artifacts`
- `/integrations`, `/environments`, `/deployments`
- `/admin`, `/audit`, `/health`, `/usage`

## Error envelope
Return a stable shape containing `code`, safe `message`, `request_id` and optional field-level `details`. Do not expose provider credentials, raw secrets or sensitive internal exception details.

## Asynchronous events
Task events should be durable and ordered per task. Suggested event types:
- `task.created`, `task.plan.ready`, `task.approval.requested`
- `task.started`, `tool.started`, `tool.completed`, `tool.failed`
- `task.validation.started`, `task.validation.completed`
- `task.repair.started`, `task.review.ready`
- `task.completed`, `task.failed`, `task.cancelled`

Every event includes event ID, task ID, tenant ID, sequence/version, timestamp, schema version, trace ID and redacted payload. The initial Mongo implementation stores task state in `tasks` and append-only state changes in `task_events`, with a unique `(organization_id, task_id, version)` index. Task state mutation and event insertion must commit in the same MongoDB transaction; this requires a replica set or sharded cluster with transaction support. Clients reconnect using a durable cursor; do not rely on an ephemeral websocket as the only record. Define event retention, export and archival policies before production.

## Webhooks
Verify provider signatures, timestamps and replay windows. Persist delivery attempts and provider event IDs. Make handlers idempotent and return promptly; process long work asynchronously.

## Compatibility
Document request/response examples and schema changes. Prefer additive changes; version breaking changes. Contract tests must validate adapters and clients.

## Local companion API (loopback-only prototype)

The local companion API is separate from the cloud `/api/v1` surface. It binds to 127.0.0.1 only and requires an exact configured browser Origin plus an allowed loopback Host header for browser-facing routes. It is not a public or LAN API.

| Method | Route | Contract |
|---|---|---|
| GET | `/health` | Local process health only; no workspace data. |
| POST | `/v1/pair` | Exchange a one-time console-displayed pairing code for a one-hour workspace:read bearer token. |
| GET | `/v1/workspaces` | Return explicitly selected workspace identifiers and safe basename labels. |
| GET | `/v1/workspaces/{workspace_id}/files` | Return a bounded relative-path/size manifest. |
| GET | `/v1/workspaces/{workspace_id}/file?path=...` | Return one bounded UTF-8 text file, subject to scanner exclusions and path checks. |
| POST | `/v1/session/revoke` | Revoke the current bearer token. |

Pairing codes expire after five minutes and failed exchanges are throttled. Responses are non-cacheable. CORS allows only configured exact origins. Chrome's current Local Network Access model requires the ODEI frontend to be served from HTTPS and to request the loopback-network permission from an explicit user gesture; the first request must use `targetAddressSpace: "loopback"`. Do not rely on legacy `Access-Control-Allow-Private-Network` PNA headers. No write, shell, terminal, deployment or arbitrary-path registration endpoint exists. ODID user/tenant binding for the local companion is not implemented, so it remains a developer prototype rather than a production authorization boundary.


## Audit event persistence (initial service primitive)

The API package includes `MongoAuditEventStore` in `odei_api.services.audit_store`. It validates tenant/actor/target identifiers, requires an HTTPS identity issuer, constrains action and outcome values, requires timezone-aware timestamps, and writes a versioned event with request/trace correlation. Metadata is bounded by depth, field count and string length; sensitive key names are replaced and common credential patterns are redacted before insertion.

The service exposes append and index initialization only; it intentionally has no update/delete methods. The writer is wired to organization-membership outcomes and to project-scoped NEXUS task create/approve/cancel operations. For those task mutations, audit insertion shares the MongoDB transaction with task state and lifecycle events. Companion pairing/revocation, authentication outcomes, all task reads/denials and tool executions are not comprehensively covered, and no audit read/export API is exposed. Production tamper resistance additionally requires a dedicated MongoDB role that can insert/read but cannot update/delete audit records, plus backup, retention, access-review and replica-set integration tests.


## NEXUS planning

- `POST /api/v1/organizations/{organization_id}/nexus/plan` requires a verified bearer access token, active server-side organization membership and explicit cloud-model consent.
- Request fields: `task` (1–8,000 characters), optional `project_context` (0–24,000 characters), and strict boolean `cloud_model_consent`.
- The route returns a plan identifier, organization identifier, model and plan text. It does not persist the plan as a durable task and does not execute tools or modify a workspace.
- Plan success/failure is written to the append-only audit event collection. Audit metadata excludes task, context and plan content; audit failure returns 503.


## Project-scoped NEXUS authorization foundation

The API package includes a fail-closed project access service. A project must be active and tenant-matched; access is granted only to the exact owner issuer+subject or an active project-membership record. Missing and unauthorized projects are intentionally indistinguishable (404). This service is not yet exposed as a project API; project creation, membership administration and role policy remain unimplemented.

The task store supports atomic planned-task creation: it writes the task in `awaiting_approval` and four ordered lifecycle events (created, context gathering, planning, approval requested) in one MongoDB transaction. It requires a MongoDB replica set or sharded-cluster transaction capability.


## Project-scoped NEXUS task HTTP API (first integrated slice)

The API now exposes the following project-scoped task routes. Every operation requires a verified bearer identity, active organization membership, an active tenant-matched project, and either exact project ownership or active project membership.

| Method | Route suffix | Behavior |
|---|---|---|
| POST | `/organizations/{organization_id}/projects/{project_id}/tasks` | Requires explicit cloud-model consent, generates a plan, and atomically persists an approval-ready task with lifecycle events. |
| GET | `/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}` | Returns a task only within the authorized organization and project; task owner or project owner only. |
| POST | `/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}/approve` | Uses expected-version concurrency and records `approved`; it does not execute code. |
| POST | `/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}/cancel` | Uses expected-version concurrency to cancel a task. |

Approval is now an explicit domain state between `awaiting_approval` and `executing`. The execution transition remains unavailable through HTTP until the controlled execution fabric exists. Task create/approve/cancel operations append audit records. Task persistence and audit append are separate operations in this increment; production hardening must move the task event and audit record into a shared transaction or transactional outbox before treating audit as atomic with task state. Project creation and membership administration are still not exposed; project records must be provisioned by a trusted administrative process.


## Implemented NEXUS project-task API

The following routes require a verified identity, active organization membership, an active project, and project owner or active project-member access:
- \`POST /api/v1/organizations/{organization_id}/projects/{project_id}/tasks\`: requires strict \`cloud_model_consent=true\`, plans with the configured cloud model, and atomically persists task state, lifecycle events and the audit record in one MongoDB transaction.
- \`GET /api/v1/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}\`: task creator or project owner only.
- \`GET /api/v1/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}/events?after_version=-1&limit=50\`: task creator or project owner only; returns ordered persisted events, a \`has_more\` flag and \`next_after_version\` cursor for reconnect/pagination. Page size is capped at 100.
- \`POST .../tasks/{task_id}/approve\`: project owner only; records approval and does not execute code.
- \`POST .../tasks/{task_id}/cancel\`: task creator or project owner, with expected-version concurrency.

Task ownership is stored as the canonical JSON tuple \`[verified issuer, verified subject]\`; subject-only comparisons are not authorization. Task create/approve/cancel audit writes participate in the same MongoDB transaction as the task mutation and lifecycle event. Project creation/membership administration, live MongoDB replica-set integration, event streaming transport and event retention/archival remain outstanding.
