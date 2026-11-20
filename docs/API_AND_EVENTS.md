# API and Event Contracts

## API conventions
- Version public APIs under `/api/v1` until a deliberate versioning strategy is adopted.
- Use JSON request/response bodies, consistent error envelopes and stable resource identifiers.
- Authenticate every non-public endpoint and authorize every resource operation server-side.
- Validate request schemas, size limits, pagination bounds and content types.
- Use idempotency keys for retryable create/apply/deploy operations.
- Include request/trace IDs in responses and logs.
- Never return secret values or internal stack traces.

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

Every event includes event ID, task ID, tenant ID, sequence number, timestamp, schema version, trace ID and redacted payload. Clients reconnect using a durable cursor; do not rely on an ephemeral websocket as the only record.

## Webhooks
Verify provider signatures, timestamps and replay windows. Persist delivery attempts and provider event IDs. Make handlers idempotent and return promptly; process long work asynchronously.

## Compatibility
Document request/response examples and schema changes. Prefer additive changes; version breaking changes. Contract tests must validate adapters and clients.
