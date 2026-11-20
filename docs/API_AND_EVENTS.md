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

Membership records live in MongoDB collection `organization_memberships`. The endpoint does not accept tenant or role claims from the browser. Missing membership storage returns 503; a valid identity without active membership returns 403. Malformed membership records fail closed. Successful lookups, missing-membership denials and malformed-record failures are appended to the MongoDB `audit_events` collection before the response is returned. If the audit writer is unavailable or an append fails, the route returns 503 rather than returning an unaudited authorization result. The API initializes audit indexes during startup when MongoDB is configured. The organization-membership route is one narrow authorization hook. The project-scoped NEXUS task API also writes task-create, approve and cancel audit events in the same MongoDB transaction as the task state and lifecycle events; any audit insert failure rolls back the task mutation. These transactional task operations require a MongoDB replica set or sharded cluster. This is not yet a complete audit trail: task/task-event reads and selected task denials are now instrumented, but a route-by-route coverage review remains open. Companion pairing/revocation, authentication outcomes, tool executions and audit query/export are not covered. Production role vocabulary, membership provisioning and database-level immutability remain outstanding.

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
- `task.approved`, `task.completed`, `task.failed`, `task.cancelled`, `task.expired`

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

The service exposes append and index initialization only; it intentionally has no update/delete methods. The writer is wired to organization-membership outcomes; project-scoped NEXUS task create/approve/cancel operations; task and task-event reads; and task/approval authorization denials. For those task mutations, audit insertion shares the MongoDB transaction with task state and lifecycle events. Companion pairing/revocation, authentication outcomes, unreviewed task denial paths and tool executions are not comprehensively covered, and no audit read/export API is exposed. Production tamper resistance additionally requires a dedicated MongoDB role that can insert/read but cannot update/delete audit records, plus backup, retention, access-review and broader production replica-set/Atlas integration tests. A focused MongoDB 7.0 replica-set CI test now verifies task creation, audit-failure rollback and approval commit.


## NEXUS planning

- `POST /api/v1/organizations/{organization_id}/nexus/plan` requires a verified bearer access token, active server-side organization membership and explicit cloud-model consent.
- Request fields: `task` (1–8,000 characters), optional `project_context` (0–24,000 characters), and strict boolean `cloud_model_consent`.
- The route returns a plan identifier, organization identifier, model and plan text. It does not persist the plan as a durable task and does not execute tools or modify a workspace.
- Plan success/failure is written to the append-only audit event collection. Audit metadata excludes task, context and plan content; audit failure returns 503.


## Project-scoped NEXUS authorization foundation

The API exposes tenant-scoped project creation and listing plus owner-managed membership administration. Any active organization member may create a project; the creator becomes its owner. Project lists include only active projects owned by the caller or containing an active membership for the caller. Only the project owner may add/remove project members, and a target must already have active membership in the same organization. Membership removal is a soft status transition, preserving history. The existing project access service continues to require an active tenant-matched project and exact owner issuer+subject or active project membership; unauthorized project access is hidden as 404.

The task store supports atomic planned-task creation: it writes the task in `awaiting_approval` and four ordered lifecycle events (created, context gathering, planning, approval requested) in one MongoDB transaction. It requires a MongoDB replica set or sharded-cluster transaction capability.


## Project-scoped NEXUS task HTTP API (first integrated slice)

The API now exposes the following project-scoped task routes. Every operation requires a verified bearer identity, active organization membership, an active tenant-matched project, and either exact project ownership or active project membership.

| Method | Route suffix | Behavior |
|---|---|---|
| POST | `/organizations/{organization_id}/projects/{project_id}/tasks` | Requires explicit cloud-model consent, generates a plan, and atomically persists an approval-ready task with lifecycle events. |
| GET | `/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}` | Returns a task only within the authorized organization and project; task owner or project owner only. |
| GET | `/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}/events` | Returns ordered durable events with bounded `limit`, `after_version`, `has_more` and `next_after_version` cursor. |
| POST | `/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}/approve` | Uses expected-version concurrency and records `approved`; it does not execute code. |
| POST | `/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}/cancel` | Uses expected-version concurrency to cancel a task. |

Approval is now an explicit domain state between `awaiting_approval` and `executing`. The execution transition remains unavailable through HTTP until the controlled execution fabric exists. Task create/approve/cancel operations append audit records in the same MongoDB transaction as task state and lifecycle events; audit failure aborts the transaction. Task and task-event reads and authorization denials are audited before returning. Live MongoDB replica-set integration remains a release gate. Project creation and membership administration are still not exposed; project records must be provisioned by a trusted administrative process.



## Health routes

| Method | Route | Behavior |
|---|---|---|
| GET | `/api/v1/health/live` | Process liveness; does not imply dependencies are ready. |
| GET | `/api/v1/health/ready` | Performs MongoDB ping plus topology detection. Returns ready only for a replica set or mongos/sharded deployment; standalone MongoDB returns 503 because task/audit persistence requires multi-document transactions. |


## Project lifecycle and membership routes

| Method | Route | Behavior |
|---|---|---|
| POST | `/organizations/{organization_id}/projects` | Creates an active project for an active organization member; creator becomes owner. Returns 201. |
| GET | `/organizations/{organization_id}/projects` | Lists up to 100 active projects owned by or actively shared with the caller. |
| GET | `/organizations/{organization_id}/projects/{project_id}/members` | Project owner lists up to 100 active project members. |
| PUT | `/organizations/{organization_id}/projects/{project_id}/members` | Project owner adds an already-active organization member. |
| DELETE | `/organizations/{organization_id}/projects/{project_id}/members` | Project owner marks an active member inactive; history is retained. |

Project and membership writes use MongoDB transactions with audit insertion in the same session. Startup creates unique tenant/project and tenant/project/issuer/subject indexes. The project owner is an implicit member and is not stored as a separate membership row. Project creation/listing and membership management require configured MongoDB, verified identity and active organization membership. These routes do not implement organization administration, project ownership transfer, arbitrary roles or invitation/provisioning flows.

## NEXUS authenticated project chat

The first authenticated read-only chat endpoint is `POST /organizations/{organization_id}/projects/{project_id}/nexus/chat`. It requires a verified ODEI Identity bearer token, active organization membership, active project access and strict explicit cloud-model consent. Inputs are bounded, common secrets redacted, workspace excerpts treated as untrusted data, and chat start/success/failure are audited without storing prompt or source text. Responses API calls use `store=false` and no tools. Conversation persistence, streaming and browser ODID token integration are not implemented. See [NEXUS chat API](NEXUS_CHAT_API.md).
