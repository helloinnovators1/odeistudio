# NEXUS project chat API

**Status:** first authenticated, project-authorized, read-only chat endpoint implemented. Browser ODID session integration and streaming are not yet connected.

## Endpoint

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat`

Requires a verified ODEI Identity OAuth access token through the API's existing RS256/JWKS bearer dependency, an active organization membership, and active project access. Client-supplied organization roles are never trusted.

Example request:

```json
{
  "messages": [
    {"role": "user", "content": "Review the selected source file."}
  ],
  "workspace_files": [
    {"path": "src/main.py", "content": "print('hello')"}
  ],
  "cloud_model_consent": true
}
```

Example response:

```json
{
  "answer": "…",
  "model": "…",
  "read_only": true,
  "tools_executed": 0,
  "conversation_persisted": false
}
```

## Consent and bounded input

- `cloud_model_consent` is a required strict boolean and must be true.
- 1–20 conversation messages, roles limited to `user` and `assistant`; final message must be from the user.
- Maximum 8,000 characters per message; 40,000 combined input characters.
- Up to 5 selected workspace file excerpts, each up to 8,000 characters.
- Common secret formats and credential assignments are redacted before model submission.
- Workspace content and prior conversation are untrusted data, never instructions.
- Responses API uses `store=false`; server-side conversation persistence is not enabled.

## Authorization and audit

- API verifies the bearer token signature, issuer, audience, token type, client allowlist and required claims.
- Organization membership and project access are resolved from MongoDB.
- A denied project lookup is audited by the existing project authorization guard.
- Chat request start, success and failure are audited with actor issuer/subject and project target.
- Audit metadata contains counts and model identifier only; prompt text, workspace contents and model answer are not recorded.
- If the audit store is unavailable before model submission, the request fails closed.
- The model request is synchronous; no SSE/WebSocket streaming or cancellation is exposed yet.

## Capability boundaries

This is a project-authorized chat endpoint, not the complete coding agent:

- No model tools are registered for this route.
- No file writes, patch application, shell commands, test execution, deployment or settings changes.
- No server-side conversation history, durable chat sessions, streaming or reconnect cursor.
- The browser IDE does not yet acquire an ODID access token or call this endpoint. The existing NEXUS composer remains disabled until the trusted browser identity integration is implemented.
- Workspace excerpts are supplied by the authenticated caller. The endpoint cannot independently verify that the caller's selected local file bytes came from the companion; the client must only submit content read from its explicitly paired read-only companion and must present consent before sending it.

## Tests

- Consent required before any provider call.
- Active project authorization required.
- Audit start/success events exclude message contents.
- Read-only response contract is asserted.
- Stateless provider call asserts `store=false` and absence of tool definitions.
- Input bounds, role validation, missing answers and secret redaction are unit-tested.

See [NEXUS](NEXUS.md), [API and events](API_AND_EVENTS.md), and [IDE workspace](IDE_WORKSPACE.md).


## Browser transport increment

The web application now has a typed transport in `apps/web/src/nexus-chat.ts` with Vitest coverage. It sends the project-scoped request using an in-memory bearer token supplied by its future trusted identity integration; it does not persist tokens, include cookies, follow redirects or cache responses. It requires HTTPS except for loopback development, enforces message/file/combined context limits before network access, requires explicit consent, supports abort signals, and validates the read-only response contract.

This transport is not an ODID login implementation. No issuer, discovery metadata, authorization endpoint, token endpoint, registered browser client ID, redirect URI or refresh/revocation contract has been supplied. Therefore the composer remains disabled. Do not ask users to paste access tokens into the application or enable the composer until the production identity contract is approved and the browser authorization-code-with-PKCE integration is implemented and tested.


## Durable NEXUS conversations — implementation in review (2026-11-21)

Feature branch: `feat/nexus-durable-conversations`. This increment is not merged or production-deployed.

- Added MongoDB-backed conversation records keyed by conversation ID and scoped to organization, project, verified identity issuer and subject.
- Added authenticated create/list/read/append/delete endpoints. Every endpoint rechecks active organization membership and project access. A conversation is visible only to its creating identity, even among project members.
- Conversation writes use optimistic version checks; message count is capped at 200 and aggregate UTF-8 content at 1 MB. Conversation lists return metadata summaries rather than full transcripts.
- Added secret redaction before conversation titles and messages are persisted. Audit events cover create/list/read/append/delete and chat request outcomes without logging prompts or source contents.
- The chat endpoint now loads history from the authorized conversation, appends the user's turn and persists the assistant response. The provider receives only the latest bounded 19 persisted turns plus the new turn and explicitly selected workspace excerpts. Existing stateless compatibility remains available when no conversation ID is supplied.
- The Studio loads the most recent saved conversation when a project is selected, supports switching histories, starting a new conversation and deleting a saved conversation.
- MongoDB indexes are initialized by the API lifespan. Durable storage requires a configured MongoDB deployment; encryption-at-rest is a database/hosting configuration requirement and has not been verified here.
- Automated tests have been added for owner/tenant isolation, optimistic versions, create/list/read/append/delete, durable chat turns, browser transport and the audit `started` lifecycle. They are not yet verified on this branch until CI completes.

Not included in this increment: SSE/token streaming, guaranteed provider cancellation, tool invocation, chat-generated patch proposals, patch approval/application/rollback, isolated terminal/test execution, agent orchestration or production ODID/Mongo/model deployment configuration.


## NEXUS SSE streaming increment — in review (2026-11-21)

Feature branch: `feat/nexus-streaming-chat`. This increment is not merged or deployed.

- Added authenticated `POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat/stream` requiring explicit cloud-model consent and a server-owned conversation ID.
- Streams Responses API text deltas over Server-Sent Events. The API persists the user turn before generation and the assistant turn only after successful stream completion, using optimistic conversation versions.
- Added incremental credential redaction that withholds incomplete secret-like values across provider event boundaries before any text delta is sent to the browser.
- Emits `status`, `delta`, `error` and `done` events; disables response caching and proxy buffering.
- Connected the browser panel to incremental SSE parsing and rendering. The existing Stop control aborts the browser request; provider cancellation is best-effort because the synchronous SDK worker can only stop when its stream iterator yields or closes.
- Provider streaming uses `store=False`, no tools and the existing bounded/redacted context. The panel continues to require explicit per-message cloud consent.
- Added server streaming/redaction, route persistence, and browser SSE transport tests. CI on the exact feature head is required before merge.

Still outstanding: durable transactional audit coupling for every conversation mutation, guaranteed provider-side cancellation, encrypted-at-rest/retention configuration verification, repository tool invocation, task-planning UI, persistent patch proposals, approval/application/rollback, isolated command/test execution, agent orchestration and production staging E2E.
