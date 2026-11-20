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

Membership records live in MongoDB collection `organization_memberships`. The endpoint does not accept tenant or role claims from the browser. Missing membership storage returns 503; a valid identity without active membership returns 403. Malformed membership records fail closed. Successful lookups, missing-membership denials and malformed-record failures are appended to the MongoDB `audit_events` collection before the response is returned. If the audit writer is unavailable or an append fails, the route returns 503 rather than returning an unaudited authorization result. The API initializes audit indexes during startup when MongoDB is configured. This is a narrow membership-route integration only: the route does not yet define or enforce a production role vocabulary, project-level authorization, membership provisioning, companion-session audit, task audit or audit query/export API. Do not expose project, workspace or task resources until those controls are implemented.

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

The service exposes append and index initialization only; it intentionally has no update/delete methods. This is not yet wired into membership denials, companion pairing/revocation, task operations or other authorization decisions, and no audit read/export API is exposed. Production tamper resistance additionally requires a dedicated MongoDB role that can insert/read but cannot update/delete audit records, plus backup, retention, access-review and replica-set integration tests.
