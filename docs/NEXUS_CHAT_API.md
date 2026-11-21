# NEXUS project chat API

**Current status (2026-11-21):** the main branch includes authenticated project-scoped JSON chat, SSE streaming, durable owner-scoped conversations, bounded read-only inspection of explicitly attached excerpts, persisted patch proposals, project-owner decisions, signed apply-capability issuance and a merged one-file local companion apply path. Production ODID configuration, MongoDB deployment controls, model credentials, Windows 10 build 18362 acceptance and staging E2E remain open. The basic chat route remains tool-free; the separate inspection route exposes only the attached-excerpt allowlist.

## 1. Identity and authorization

All API routes require the existing RS256/JWKS bearer dependency and validate issuer, audience, access-token type, client allowlist and required claims. Organization membership and project access are resolved server-side. Client-supplied organization roles, project IDs and conversation IDs are not authorization evidence.

The browser uses a provider-neutral OAuth 2.0 Authorization Code + PKCE S256 client. It keeps access tokens in memory and does not put them in localStorage, sessionStorage, cookies, URLs or logs. Actual ODID issuer/discovery, public client ID, registered redirect URI, scopes/resource, token profile and refresh/revocation contract must be configured and staging-verified by the identity/API owners.

## 2. Chat request contract

### JSON chat

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat`

The request contains:
- `messages`: 1–20 user/assistant messages, final message from the user, at most 8,000 characters each.
- Optional `workspace_files`: at most five explicitly selected excerpts, at most 8,000 characters each.
- Strict `cloud_model_consent: true`.
- Optional server-generated `conversation_id` for durable history.

Combined request context is bounded to 40,000 characters. Secret-like values are redacted before model submission. Repository content and prior conversation are untrusted data, never instructions.

The basic JSON chat route is tool-free and read-only. Its response includes the answer/model and a contract indicating no tools were executed; when a conversation ID is supplied, user and assistant turns are persisted separately by ODEI. Provider-side storage remains disabled (`store=false`).

### SSE streaming

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat/stream`

The separate streaming endpoint emits status, incremental delta, error and completion events. It persists the user turn before generation and the assistant turn only after successful completion, using optimistic conversation versions. Secret redaction is incremental across provider event boundaries so incomplete secret-like values are withheld before a delta reaches the browser.

The browser can abort its request and stop waiting. Provider cancellation is best-effort: the synchronous provider worker can stop only when the stream iterator yields/closes. The UI must not represent a browser abort as guaranteed upstream cancellation.

## 3. Read-only attached-excerpt tools

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat/inspect`

This route requires a saved conversation, explicit cloud consent and one to five file excerpts explicitly attached by the user. It rechecks project access and conversation ownership before running the bounded agent loop.

Allowlisted tools:
- `list_attached_excerpts`: lists only attached relative paths and character counts.
- `read_attached_excerpt`: reads the exact excerpt attached in this request.
- `search_attached_excerpts`: literal case-insensitive search, bounded result count and line size.

The schemas are strict and reject additional properties. The tool loop is capped at six rounds and twelve calls. No arbitrary workspace root, companion handle, unselected file, filesystem access, shell, network, write or deployment tool is exposed. This is not whole-repository indexing or semantic retrieval.

## 4. Durable conversations

Authenticated conversation routes create, list, read, append and delete records scoped to organization, project and verified issuer/subject. Every request rechecks membership and project access. Conversations are visible only to their owner identity, even among project members.

Writes use optimistic version checks. Message count is capped at 200 and aggregate UTF-8 content at 1 MB. Lists return metadata summaries rather than transcripts. Titles/messages are secret-redacted before persistence; audit events cover lifecycle actions without storing prompts or source contents. MongoDB indexes are initialized by API lifespan.

A CI replica-set test verifies transactional storage behavior, but it is not evidence that a production Atlas/replica-set deployment, encryption-at-rest, backups, retention, deletion/export or recovery policy is configured.

## 5. Patch proposal and approval workflow

Authenticated project-scoped proposal routes create/list/read proposals and allow the project owner to approve or reject an exact version. Proposals store bounded file operations, base/result SHA-256 hashes, proposed content and unified diffs. Limits are 20 files, 1 MB per file, 5 MB aggregate replacement content and 8 MB aggregate diff. New nested-directory creation is not supported.

Only the project owner can approve/reject. Decisions use optimistic version checks and do not themselves write local files.

The apply-capability route issues a short-lived Ed25519 capability only for an approved proposal and fresh companion challenge. The capability binds issuer/audience, identity, organization/project, workspace, proposal/version, canonical patch digest, token ID and expiry.

The paired companion independently verifies the signature and all bindings, consumes the one-use challenge, re-reads the live target and checks its base hash. It accepts exactly one file operation per apply request. Windows uses handle-relative FileRenameInformationEx POSIX-semantics replacement; POSIX uses descriptor-relative no-follow operations. The API does not receive a local filesystem path and never performs the local write itself.

Multi-file transactional apply, durable rollback journals and crash recovery are not implemented.

## 6. Audit and data handling

- Explicit cloud-model consent is required before sending prompts or attached excerpts to the provider.
- Provider requests use `store=false`; ODEI conversation history is stored separately under tenant/project/owner scope.
- Audit metadata records action, outcome, actor, project, counts, model and bounded tool-call metadata. Prompts, source content, diffs, bearer tokens and private signing keys are not audit payloads.
- If required audit storage is unavailable before a sensitive operation, the request fails closed.
- Local companion pairing is not API identity and is not cloud consent.
- No access token or private signing key is persisted by the browser.

## 7. Current tests

Coverage includes:
- Project/organization authorization and owner-only decisions.
- Consent, request bounds, role validation, secret redaction and safe errors.
- Durable conversation ownership, version conflicts, append/delete and audit behavior.
- SSE parsing, incremental secret redaction, response persistence and cancellation semantics.
- Attached-excerpt tool schemas, path scoping, secret redaction, unregistered tool rejection and bounded call loops.
- Patch proposal path/hash/size validation, owner decisions, capability signatures, replay/challenge checks and local apply safety.
- Windows/Ubuntu Python 3.10/3.12, web tests/build, MongoDB replica-set integration, CodeQL, secret scanning and Python/web dependency audits on the merged PR #24 source head.

## 8. Explicit non-capabilities and release gates

Not implemented:
- Whole-workspace model tools, semantic indexing and autonomous repository discovery.
- Multi-file atomic apply, durable rollback, crash recovery and rollback UI.
- Terminal/shell, isolated command/test execution, package installation or execution artifacts.
- Agents Window orchestration, CLI, cloud/background agents and MAC/MAD execution.
- Production deployment, production monitoring and verified production backup/restore.

Before production use, configure and staging-test the actual ODID/API trust contract, MongoDB replica-set topology and encryption/backup policy, server-side model credentials, patch signer/pinned companion public key and exact CORS origins. Install and test the local companion on the user's Windows 10 build 18362 device. No such device test, real ODID staging test or production deployment has been performed in this hosted session.

See [NEXUS chat operationalisation](NEXUS_CHAT_OPERATIONALIZATION.md), [local patch application](LOCAL_PATCH_APPLICATION.md), [patch approval capabilities](PATCH_APPROVAL_CAPABILITIES.md), [NEXUS task planning](NEXUS_TASKS.md) and [implementation status](IMPLEMENTATION_STATUS.md).
