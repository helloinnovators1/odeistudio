# NEXUS Chat Panel Operationalisation

**Status:** the NEXUS panel now has an interactive ODID PKCE sign-in/callback path, tenant-scoped project listing, per-request cloud consent and a functional synchronous read-only composer. Production use remains gated on real ODID/API configuration and staging validation. SSE streaming and durable history are implemented in separate merged/in-review increments. Repository tools, patch application, isolated execution and agents remain future work.

## 1. Product responsibility

NEXUS Chat is the conversational control plane for a selected Studio project. It accepts developer intent, establishes trusted project context, explains what it can do, routes eligible requests to approved capabilities, and reports evidence-backed outcomes.

It is not itself an authorization boundary. Every server operation must independently authenticate the caller, resolve active organization and project membership, enforce capability policy, and audit sensitive decisions. UI state, client-supplied role claims, project paths and model-generated instructions are never authorization evidence.

## 2. Operational modes

| Mode | User experience | Permitted effects |
|---|---|---|
| Explain | Ask questions, discuss architecture, explain selected code | Read-only model response |
| Inspect | Ask NEXUS to inspect selected project files | Explicitly authorized bounded reads/search only |
| Plan | Ask for an implementation or remediation plan | Create a tenant/project-scoped plan and task records |
| Propose | Request code changes | Create reviewable patch proposals; no file mutation |
| Apply | Approve a reviewed proposal | Future capability: audited atomic handle-relative writes with rollback |
| Execute | Run tests, diagnostics or commands | Future capability: isolated, policy-constrained execution |
| Delegate | Assign work to agents | Future capability: scoped agent jobs with checkpoints and cancellation |

The first production chat release must not advertise Apply, Execute or Delegate until their services and tests are available.

## 3. Request lifecycle

1. **Compose:** collect a non-empty user message and explicit attachments/references.
2. **Bind identity:** obtain a short-lived access token through the approved ODID public-client authorization-code-with-PKCE flow. Keep access tokens in memory; never accept pasted bearer tokens or put tokens in local storage, URLs, logs or analytics.
3. **Bind project:** resolve the active organization and project through trusted membership/project APIs. The API rechecks authorization on every request.
4. **Consent:** disclose that the message and selected excerpts will be sent to the configured cloud model. Consent is affirmative, scoped to the request/session policy, revocable, and never inferred from connecting the local companion.
5. **Build context:** attach only explicitly selected, bounded, authorized excerpts. Do not silently upload the entire workspace. Redact secrets before provider submission; treat conversation history and file contents as untrusted data.
6. **Submit:** send the project-scoped request over HTTPS with bearer authorization, bounded payload, request correlation ID, no cookies, no caching and redirects disabled.
7. **Process:** API validates token profile, tenant membership, project membership, consent, limits and audit availability before invoking the model. Model output is untrusted and cannot grant permissions.
8. **Deliver:** stream typed events where supported; distinguish queued, started, text delta, tool activity, approval required, completed, failed and cancelled. A transport interruption must not be displayed as success.
9. **Persist:** persist conversations only after a documented retention, encryption, tenant isolation, deletion/export and audit design is approved. Until then, keep chat stateless and clearly label that history is session-only.
10. **Close the loop:** show the response, citations/file references where available, proposed actions, approvals and verifiable execution/test results. Never claim an action occurred without a successful service result.

## 4. Chat panel interaction contract

### Header
- NEXUS identity and current mode.
- Active organization/project identity (or an explicit “not connected” state).
- Model/provider indicator only when known from the server.
- Connection status and close control.

### Conversation body
- Distinguish user, assistant, system status and tool activity visually and accessibly.
- Render Markdown safely; do not execute HTML or model-supplied scripts.
- Show selected file references and context provenance.
- Show request lifecycle and timestamps.
- Support retry only for safe idempotent requests; use idempotency keys for task/proposal creation.
- Preserve partial stream state and show interruption/cancellation distinctly.
- Provide accessible live announcements without announcing every token.

### Composer
- Multiline input, send, stop/cancel, retry, clear-session and attachment/reference affordances.
- Enter sends; Shift+Enter inserts a newline. Respect IME composition.
- Disable duplicate submissions while a request is active.
- Show remaining context budget and explain rejected oversized input.
- Consent is visible before any cloud transmission; no prechecked consent.
- Composer remains disabled until trusted identity and active project context are established.

### Context controls
- Attach active editor selection, active file or explicitly selected files only after user action.
- Display each attached path and size; allow removal before send.
- Never interpret a local companion pairing token as an API identity token.
- Never send a full workspace scan or hidden files by default.

### Activity and action cards
- Tool name, purpose, bounded inputs/outputs, start/end state and correlation ID.
- Approval cards must show exact affected files/commands, risk, expected effects and rollback availability.
- Approval is a separate authenticated API operation; a natural-language “yes” must be bound to a specific proposal/version and cannot approve a different action.
- Show test command, environment, exit status and captured summary for execution results.

## 5. Capability and security boundaries

- **Identity:** approved ODID issuer, discovery metadata, authorization endpoint, token endpoint, registered public client ID, exact redirect URI, supported scopes/audience, access-token profile, expiry/refresh/revocation behavior, and API JWKS/issuer/audience configuration are deployment prerequisites. Do not invent these values.
- **Authorization:** tenant and project checks are server-side and repeated for every chat, context, task, proposal, event, approval and execution request.
- **Cloud consent:** required before sending prompts or source excerpts to a cloud provider. Companion pairing is not cloud consent.
- **Data minimization:** default to no workspace context; send only selected bounded excerpts. No credentials, environment files, private keys or ignored sensitive paths.
- **Prompt injection:** user content, history, repository files, tool output and model output are untrusted. System policy is not overridable by repository content.
- **Tool policy:** expose a typed allowlist with per-tool schemas, path scoping, timeouts, output caps, rate limits and audit events. No arbitrary function names from model output.
- **Writes:** no browser-side direct filesystem writes. Implement Windows handle-relative and POSIX descriptor-relative safe atomic replacement, race/path-swap protections, concurrency hashes, rollback and audit before enabling apply.
- **Execution:** no shell in the browser or API process. Use isolated workers with resource, network, filesystem, process and time policies.
- **Persistence:** no plaintext prompts, source code, diffs, access tokens or provider secrets in audit metadata. Conversation persistence requires encryption/key management, tenant-scoped access, retention and deletion semantics.
- **Observability:** correlate requests and events without logging sensitive content. Redact secrets from errors and traces.
- **Abuse controls:** request quotas, per-user/project concurrency limits, provider cost budgets, cancellation and backpressure.

## 6. API and event contracts

The existing read-only endpoint remains the first interaction:
`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat`

Current request contract: `messages`, optional bounded `workspace_files`, and strict `cloud_model_consent: true`. Current response is a single JSON answer with `read_only: true`, `tools_executed: 0`, and `conversation_persisted: false`.

Streaming must be a separately versioned/negotiated contract (SSE is the preferred initial transport) with:
- `message.started`
- `message.delta`
- `message.completed`
- `activity.started` / `activity.completed`
- `approval.required`
- `request.failed`
- `request.cancelled`

Every event includes a request ID and monotonic sequence number. The server must enforce event ordering, bounded buffers, heartbeat/timeout behavior, disconnect cancellation policy and authorization on reconnect. Do not silently change the existing JSON endpoint into an SSE endpoint.

Conversation/session APIs, if introduced, must use opaque server-generated IDs and tenant/project scoping. A client-provided conversation ID is never proof of ownership.

## 7. Persistence model (future, gated)

Separate entities are required:
- Conversation: tenant/project, owner identity (issuer + subject), lifecycle, retention class and timestamps.
- Message: conversation, sequence, role, content reference, model metadata and safety metadata.
- Request: idempotency key, status, cancellation, provider usage and correlation ID.
- Activity: typed tool/agent events with bounded redacted metadata.
- Proposal: exact base hashes, patch content reference, author, version and review status.
- Approval: approver identity, proposal/version, decision and timestamp.
- Execution: isolated environment identity, command/test reference, policy, exit status and artifacts.

Conversation/message content must be encrypted at rest with managed keys and must not be copied into audit events. Tenant filters must be applied in every query and backed by compound indexes. Define export, deletion, retention expiry, legal hold and key rotation before production persistence.

## 8. Delivery sequence and acceptance gates

### Gate 0 — prerequisites
- Confirm exact ODID public-client and access-token contract.
- Confirm API issuer/audience/JWKS and browser CORS allowlist.
- Confirm organization/project discovery and selection workflow.
- Configure exact API base URL and registered redirect URI per environment.
- No credentials committed to source or sent through chat.

### Gate 1 — authenticated read-only chat
- Implement PKCE login/callback/logout and in-memory access-token lifecycle.
- Add trusted organization/project selection.
- Connect composer to the existing typed transport.
- Add consent, selected-file references, transcript UI, cancellation, retry and error states.
- Add API/web tests for login state/PKCE, token expiry, project denial, consent denial, secret redaction, request bounds, cancellation and no token persistence.
- Acceptance: an authorized user can ask a project-scoped question end-to-end; unauthorized or unconfigured users cannot submit.

### Gate 2 — streaming and session history
- Add a distinct streaming endpoint and typed event parser.
- Add reconnect/cancellation/sequence tests.
- Decide and implement encrypted conversation persistence, retention and deletion.
- Acceptance: no lost/duplicated events across tested reconnects; no cross-tenant history access.

### Gate 3 — project inspection and planning
- Register bounded read-only search/read tools and project-context retrieval.
- Connect task planning and task/event views.
- Add citations/provenance for retrieved files.
- Acceptance: tool calls are allowlisted, bounded, audited and project-scoped; prompt injection tests pass.

### Gate 4 — patch proposals and approval
- Connect chat output to multi-file proposal creation and review UI.
- Persist proposals only with approved encryption/key management.
- Bind decisions to proposal ID and version.
- Implement safe Windows/POSIX atomic apply and rollback only after threat-model review.
- Acceptance: stale-base, path traversal, junction/symlink, race, partial-write, rollback and authorization tests pass.

### Gate 5 — isolated execution
- Add isolated command/test/diagnostic workers and streamed activity.
- Enforce resource/network/filesystem policy, quotas and cancellation.
- Acceptance: escape, exfiltration, resource exhaustion and cross-project tests pass.

### Gate 6 — agent orchestration
- Add agent assignment, independent workspaces/branches, task dependencies, checkpoints, recovery and human approval.
- Connect Agents Window, CLI and background/cloud agent services.
- Acceptance: every delegated action is attributable, scoped, observable, cancellable and reviewable.

## 9. Current repository evidence

Implemented:
- NEXUS panel shell, left/right preference and Ctrl+I/Command+I toggle.
- Project-scoped authenticated read-only API foundation.
- Bounded chat transport with in-memory bearer token input, HTTPS/loopback validation, no cookies/cache, abort signal and response-contract validation.
- Provider-neutral OAuth 2.0 Authorization Code + PKCE S256 browser client with issuer discovery validation, callback-origin/state validation, bounded token exchange and no access-token persistence. It is not wired to the app and has not been tested against ODID staging.
- Secret redaction, explicit cloud consent, server-side membership checks and audit events.
- Bounded selected workspace excerpt contract.

Not yet implemented or connected:
- ODID production browser login integration: the generic PKCE helper exists, but approved ODID issuer/client/redirect/resource/scope configuration, callback route, runtime configuration and real issuer/JWKS verification are still absent.
- Trusted organization discovery and project selector.
- Composer-to-transport integration.
- Streaming and cancellation endpoint.
- Durable conversation history and retention controls.
- Whole-project indexing/semantic retrieval.
- Chat-invoked tools, patch workflow and approval.
- Safe patch application/rollback.
- Isolated command execution and diagnostics.
- Agent delegation, CLI, cloud/background agent controls.

## 10. Release rule

A capability is “implemented” only when its code, authorization boundary, tests, documentation and CI evidence exist. A design, UI control, mock response or provider configuration placeholder does not count. Do not merge to `main`, deploy, or enable destructive capabilities without the applicable review and release authorization.


## Delivered interactive read-only chat slice — 2026-11-21

The current web implementation now includes:
- ODID authorization-code + PKCE sign-in and callback handling through the provider-neutral client.
- In-memory access-token lifecycle with expiry clearing and UI sign-out. No bearer token is stored in localStorage, sessionStorage, cookies or URL parameters.
- User-entered organization ID and server-authorized project selection. Organization discovery is not yet available.
- Active-file excerpt attachment only after an explicit checkbox selection; no automatic full-workspace upload.
- An unchecked, per-request cloud-model consent checkbox. Sending is disabled until consent, a selected project and a non-empty bounded message exist.
- A working synchronous send/response transcript, Enter-to-send, Shift+Enter, request abort and session-only history.
- Strict browser CORS allowlist configuration through `CORS_ALLOWED_ORIGINS`; origins must be explicit HTTPS origins, with HTTP allowed only for loopback development.

This slice still uses the existing JSON chat endpoint. It does not stream, persist conversations, invoke repository tools, generate or apply patches, execute commands/tests, or orchestrate agents. The backend remains read-only and stateless. The user must provide approved environment-specific public ODID values and the API owner must configure matching issuer/audience/JWKS/client allowlist, MongoDB, model credentials and exact CORS origins. Do not enable production use until an actual ODID staging/browser end-to-end test passes.


### Organization discovery delivered — 2026-11-21

- Added authenticated `GET /api/v1/organizations` to discover only active organization memberships for the verified identity. The response is bounded to 100, malformed/duplicate membership data fails closed, and returned membership reads are audited.
- Added a typed browser transport and organization selector. The user now selects from server-discovered memberships rather than manually typing an organization ID. Project selection remains a separate server-authorized step.


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


## Task planning and approval controls — implementation in review (2026-11-21)

- The chat composer exposes a separate **Plan task** action. It submits the draft as a task goal through the existing tenant/project-authorized task API.
- Planning requires the same unchecked-by-default per-request cloud-model consent as chat. An active-file excerpt is included only when the user explicitly selects the attachment checkbox.
- The panel displays the persisted plan, task status, task ID and version, and provides project-owner approval and cancellation controls.
- The API remains authoritative for approval. Only the project owner may approve; client-side visibility is not authorization.
- **Approval is not execution.** The current task approval endpoint records intent and does not write files, apply patches, run commands or launch agents.
- This UI increment is on `feat/nexus-task-planning-ui`, not merged until CI passes.
