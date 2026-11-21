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
