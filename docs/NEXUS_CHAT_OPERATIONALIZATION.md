# NEXUS Chat Panel Operationalisation

**Verified repository status — 2026-11-21:** The current main branch includes configurable ODID Authorization Code + PKCE login/callback, server-authorized organization/project discovery, explicit per-request cloud consent, an active composer, SSE streaming with browser cancellation, durable owner-scoped conversations, bounded read-only inspection of explicitly attached excerpts, persisted patch proposals, project-owner approve/reject decisions, and a merged signed single-file local-companion apply path (PR #24, merge commit 1a5e6d9). Local apply requires a paired companion, explicit workspace write opt-in, matched Ed25519 API/companion configuration, an approved proposal, a fresh one-use challenge and live base-hash verification. Windows and Ubuntu CI passed on Python 3.10/3.12, along with web, MongoDB integration, CodeQL, secret scanning and dependency audits. This is not a complete production release: the companion has not been installed or exercised on the user's Windows 10 build 18362 device, and no real ODID staging/browser-to-companion E2E has been performed. Real ODID issuer/client/redirect/resource/scope and token refresh/revocation configuration, production API issuer/JWKS/CORS settings, MongoDB deployment, model credentials and hosting remain external gates. Multi-file transactions, durable rollback/recovery, isolated command/test execution, agent orchestration, cloud/background agents and MAC/MAD execution remain unimplemented.

## 1. Product responsibility

NEXUS Chat is the conversational control plane for a selected Studio project. It accepts developer intent, establishes trusted project context, explains what it can do, routes eligible requests to approved capabilities, and reports evidence-backed outcomes.

It is not itself an authorization boundary. Every server operation must independently authenticate the caller, resolve active organization and project membership, enforce capability policy, and audit sensitive decisions. UI state, client-supplied role claims, project paths and model-generated instructions are never authorization evidence.

## 2. Operational modes

| Mode | User experience | Permitted effects |
|---|---|---|
| Explain | Ask questions, discuss architecture, explain selected code | Project-scoped model response |
| Inspect | Ask NEXUS to inspect selected files | Read/list/literal-search only within explicitly attached, bounded excerpts |
| Plan | Ask for an implementation or remediation plan | Create tenant/project-scoped plan and task records; approval records intent but does not execute |
| Propose | Request code changes | Create persisted, reviewable patch proposals with hashes and diffs |
| Apply | Approve a reviewed proposal | One-file signed, challenge-bound companion apply; no multi-file transaction or rollback |
| Execute | Run tests, diagnostics or commands | Not available; requires isolated, policy-constrained workers |
| Delegate | Assign work to agents | Not available; requires scoped agent jobs, checkpoints and cancellation |

Apply is shown only for an approved one-file proposal when the paired companion advertises the apply capability. Production use remains gated on real ODID/API/model configuration and local Windows 10 build 18362 acceptance. Do not advertise Execute or Delegate until their isolated execution and orchestration services exist.

## 3. Request lifecycle

1. **Compose:** collect a non-empty user message and explicit attachments/references.
2. **Bind identity:** obtain a short-lived access token through the approved ODID public-client authorization-code-with-PKCE flow. Keep access tokens in memory; never accept pasted bearer tokens or put tokens in local storage, URLs, logs or analytics.
3. **Bind project:** resolve the active organization and project through trusted membership/project APIs. The API rechecks authorization on every request.
4. **Consent:** disclose that the message and selected excerpts will be sent to the configured cloud model. Consent is affirmative, scoped to the request/session policy, revocable, and never inferred from connecting the local companion.
5. **Build context:** attach only explicitly selected, bounded, authorized excerpts. Do not silently upload the entire workspace. Redact secrets before provider submission; treat conversation history and file contents as untrusted data.
6. **Submit:** send the project-scoped request over HTTPS with bearer authorization, bounded payload, request correlation ID, no cookies, no caching and redirects disabled.
7. **Process:** API validates token profile, tenant membership, project membership, consent, limits and audit availability before invoking the model. Model output is untrusted and cannot grant permissions.
8. **Deliver:** stream typed events where supported; distinguish queued, started, text delta, tool activity, approval required, completed, failed and cancelled. A transport interruption must not be displayed as success.
9. **Persist:** save conversations in MongoDB under verified issuer/subject, organization and project scope, with bounded message count/content and optimistic versions. Audit metadata excludes prompts and source text. Production retention, export/deletion policy, backup/recovery and encryption-at-rest configuration still require deployment verification.
10. **Close the loop:** show the response, attached-file provenance, proposed actions and owner decisions. For Apply, require an approved one-file proposal, a fresh companion challenge and signed capability; report the companion's result and durability flag. Never claim rollback, test execution or deployment occurred unless a corresponding service actually succeeds.

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
- **Writes:** no browser-side direct filesystem writes. The merged companion apply path performs one-file Windows handle-relative/POSIX descriptor-relative atomic replacement with reparse/symlink protections, live base-hash verification, signed short-lived capability, one-use challenge and audit. Multi-file atomicity, durable rollback/recovery and local Windows 10 build 18362 acceptance are not implemented.
- **Execution:** no shell in the browser or API process. Use isolated workers with resource, network, filesystem, process and time policies.
- **Persistence:** no plaintext prompts, source code, diffs, access tokens or provider secrets in audit metadata. Conversation persistence requires encryption/key management, tenant-scoped access, retention and deletion semantics.
- **Observability:** correlate requests and events without logging sensitive content. Redact secrets from errors and traces.
- **Abuse controls:** request quotas, per-user/project concurrency limits, provider cost budgets, cancellation and backpressure.

## 6. API and event contracts

The existing JSON endpoint remains available:

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat`

A separate SSE endpoint streams incremental assistant output and lifecycle events:

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat/stream`

The bounded read-only attached-excerpt tool mode is separate:

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat/inspect`

It permits only strict list/read/literal-search tools over one to five excerpts explicitly attached by the user. It does not expose arbitrary workspace roots, local file handles, writes, shell or network tools.

Conversation endpoints create/list/read/append/delete durable records scoped to organization, project and verified issuer/subject. Writes use optimistic versions and bounded history. Client-supplied IDs are lookups only and never prove ownership.

Patch proposal APIs persist bounded proposals and diffs; project owners can approve/reject a specific version. The apply-capability endpoint issues a short-lived Ed25519 capability only for an approved proposal and fresh companion challenge. The local companion independently verifies the signature, issuer/audience/expiry, proposal/workspace/content binding, pairing session and one-use challenge before applying one file. API approval does not itself mutate a local file.

SSE events include request/message lifecycle, incremental deltas, activity, completion, failure and cancellation. Event parsing is bounded and rejects malformed or oversized events. Browser cancellation stops waiting and requests server cancellation; upstream provider cancellation is best-effort and must not be represented as guaranteed.

## 7. Persistence model — implemented foundation, production gates remain

Implemented MongoDB conversation records include:
- Opaque conversation ID, organization/project scope and owner issuer/subject.
- Ordered user/assistant messages, bounded message count and aggregate UTF-8 content.
- Optimistic version checks for append/delete and metadata-only list responses.
- Secret redaction before persisted titles/messages and audit events for lifecycle operations.
- Tenant/project/owner filters on every conversation lookup.

Patch proposals are separately persisted with proposal ID, owner, project, version, base/result hashes, proposed replacement content and unified diff. Owner decisions record the deciding identity, decision time and proposal version. Local patch application uses a short-lived signed capability; the local companion remains the authority for actual file mutation.

Production still requires an explicit retention/deletion/export policy, verified database encryption-at-rest and managed-key configuration, backup/restore tests, operational monitoring and incident recovery. Audit events must never contain prompts, full source content, diffs, bearer tokens or signing secrets. Do not infer production durability from a successful CI MongoDB replica-set test.

## 8. Delivery sequence and acceptance gates

### Gate 0 — external production prerequisites (open)
- Configure the real ODID public client, issuer/discovery, exact redirect URI, scopes/resource, access-token profile and refresh/revocation contract.
- Configure API issuer/audience/JWKS/client allowlist and exact HTTPS CORS origins.
- Provision production MongoDB replica-set topology and verify encryption, backup and restore.
- Configure server-side model credentials and approved hosting.
- Install the local companion and validate pairing/apply on the user's Windows 10 build 18362 machine. No local desktop scan or real browser-to-companion staging test has yet been performed.

### Gate 1 — authenticated chat (code implemented; real-provider E2E open)
- Provider-neutral PKCE login/callback, in-memory token handling, server-authorized organization/project selection, active composer, explicit consent, transcript and bounded request transport are implemented.
- Acceptance still requires a real ODID staging login and an authorized user completing a project-scoped conversation with production-like issuer/JWKS/CORS settings.

### Gate 2 — streaming and durable history (code implemented; production data controls open)
- Separate SSE response transport, incremental rendering, browser cancellation, durable owner-scoped conversation APIs and optimistic versioning are implemented.
- Verify production retention, deletion/export, encryption-at-rest, backups and recovery before production use. Provider cancellation remains best-effort.

### Gate 3 — inspection and planning (bounded implementation)
- Strict list/read/literal-search tools operate only over explicitly attached file excerpts. Tenant/project authorization, secret redaction, tool-call bounds and audit metadata are enforced.
- Project-scoped task planning and approval records exist; approval does not execute a task.
- Whole-workspace companion-mediated repository tools, semantic indexing, automatic citations and task execution remain open.

### Gate 4 — proposals, approval and local apply (single-file implementation)
- Persisted patch proposals, diff review, project-owner approve/reject decisions, signed apply capabilities and challenge-bound one-file companion application are implemented.
- Apply is gated by explicit local write opt-in, a paired companion with pinned public key, fresh challenge, approved proposal version and live base hash.
- Multi-file transactional application, durable rollback/recovery journal and crash-recovery acceptance remain open.

### Gate 5 — isolated execution (not implemented)
- Build isolated command/test/diagnostic workers with resource, network, filesystem, process and time policies, quotas, streamed activity and cancellation.
- Acceptance: escape, exfiltration, resource exhaustion, cross-project access and crash recovery tests pass.

### Gate 6 — agent orchestration (not implemented)
- Add agent assignment, independent workspaces/branches, task dependencies, checkpoints, recovery, human approval and attribution.
- Connect Agents Window, CLI and background/cloud agent services.
- Acceptance: every delegated action is scoped, attributable, observable, cancellable and reviewable.

## 9. Current repository evidence

Implemented on main:
- Configurable ODID Authorization Code + PKCE browser foundation and callback; access token remains in memory. Real ODID issuer/client/redirect/resource/scope values and refresh/revocation behavior are not configured or staging-verified.
- Server-authorized organization discovery and project selection, project-scoped authentication and membership checks.
- Active NEXUS composer, explicit per-request cloud consent, message validation, send, transcript, error states and cancellation.
- Separate SSE endpoint with incremental response rendering. Provider-side cancellation is best-effort.
- Durable MongoDB conversations with owner/tenant/project isolation, bounded history, optimistic versions and audit events. Production retention and encryption-at-rest configuration remain external.
- Bounded attached-excerpt inspection tools: list, read and literal search only over explicitly attached excerpts; no arbitrary workspace root or full-workspace access.
- Task planning and owner approval records; approval does not execute tasks.
- Persisted multi-file patch proposals and unified diff review, project-owner approve/reject decisions and short-lived signed apply-capability issuance.
- One-file local companion apply, independently verifying the Ed25519 capability, challenge, pairing session, proposal/workspace/content binding and live base hash. POSIX and Windows paths use handle-relative atomic replacement; Windows uses FileRenameInformationEx POSIX semantics. The companion reports whether directory-metadata durability was confirmed.
- CI on the merged PR #24 source head passed Windows/Ubuntu Python 3.10/3.12, MongoDB replica-set integration, web tests/build, CodeQL, secret scanning, pip-audit and npm audit.

Not implemented or not verified:
- Actual ODID provider registration, token refresh/revocation, real issuer/JWKS staging verification and production environment configuration.
- Whole-workspace NEXUS repository tools or background indexing; inspection is limited to attached excerpts.
- Multi-file atomic patch transactions, durable rollback journal, crash recovery and apply across nested new-directory creation.
- Isolated terminal, command execution, build/test execution, package installation and execution artifacts.
- Agents Window orchestration, NEXUS CLI, cloud/background agents and MAC/MAD execution.
- Local companion installation, desktop-folder scan, Windows 10 build 18362 validation and real browser-to-companion staging E2E.
- Production deployment, production MongoDB, model-provider secrets and hosting/CORS configuration.

No local tests or build were run from the user's Windows machine in this hosted repository session. GitHub Actions results verify the merged source head only; they do not establish local installation, ODID staging, production infrastructure or deployment.

## 10. Release rule

A capability is “implemented” only when its code, authorization boundary, tests, documentation and CI evidence exist. A design, UI control, mock response or provider configuration placeholder does not count. Do not merge to `main`, deploy, or enable destructive capabilities without the applicable review and release authorization.


## Historical implementation notes

The dated milestone entries below are retained as an audit trail of earlier development snapshots. Their point-in-time statements such as “not implemented”, “in review” or “composer disabled” are superseded by the current verified repository evidence in sections 1–9 above. Use the current status and acceptance gates above as the source of truth.

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



## NEXUS streaming and interactive panel increment — 2026-11-21

Feature branch: `feat/nexus-streaming-chat`. This increment is not merged or deployed until its exact-head CI and review gates pass.

- Added a separate authenticated `POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat/stream` endpoint using Server-Sent Events. The existing JSON chat endpoint remains unchanged for compatibility.
- The stream uses the Responses API streaming context with provider-side storage disabled, no tools, no command execution and explicit cloud-model consent. Events include a generation status, incremental text deltas, a terminal completion event, and a safe error event; a keep-alive comment is emitted during idle periods.
- Streamed output is incrementally secret-redacted before any delta is sent to the browser. The redactor retains incomplete credential-like values across provider event boundaries and handles known API tokens, bearer values, JWT-like tokens, private-key blocks, credential assignments and credential-bearing MongoDB URIs. This is defense-in-depth, not a guarantee of detecting every secret format.
- The endpoint reloads the owner-scoped server transcript, appends only the submitted user turn with optimistic versioning, and persists the assistant turn only after provider completion. Completion confirms the conversation ID and persisted state. The browser validates the stream contract and enforces event/output bounds.
- The Studio panel uses the streaming transport, incrementally renders NEXUS deltas, provides a Stop control, preserves saved conversation history, and removes partial assistant output when a stream fails or is cancelled. Cancellation stops delivery and signals the worker; interruption of an in-flight provider network read is best-effort and must not be represented as guaranteed upstream cancellation.
- Added API streaming tests, incremental secret-redaction tests, browser SSE parsing tests, CRLF framing and oversized-event tests. The conversation-store UTF-8 byte-budget aggregation expression was corrected to reference the MongoDB map variable properly and is covered by the replica-set integration test.
- Remaining prerequisites: approved ODID issuer/client/redirect/resource/scope values, real ODID staging verification, production API/Mongo/model configuration, encryption-at-rest/retention/backup controls and deployment. No production credentials are in source and none should be pasted into chat.

This increment does not implement chat-triggered repository tools, patch creation/review/application/rollback, terminal/test execution, agent orchestration, cloud/background agents or MAC/MAD operations. The current chat agent remains read-only.


## Task planning and approval controls — implementation in review (2026-11-21)

- The chat composer exposes a separate **Plan task** action. It submits the draft as a task goal through the existing tenant/project-authorized task API.
- Planning requires the same unchecked-by-default per-request cloud-model consent as chat. An active-file excerpt is included only when the user explicitly selects the attachment checkbox.
- The panel displays the persisted plan, task status, task ID and version, and provides project-owner approval and cancellation controls.
- The API remains authoritative for approval. Only the project owner may approve; client-side visibility is not authorization.
- **Approval is not execution.** The current task approval endpoint records intent and does not write files, apply patches, run commands or launch agents.
- This UI increment is on `feat/nexus-task-planning-ui-main`, not merged until CI passes.


## NEXUS attached-excerpt tool inspection — 2026-11-21

Feature branch: `feat/nexus-chat-selected-file-tools`. This is a limited read-only tool increment, not whole-repository agent access.

- Added `SelectedExcerptTools` with three strict function schemas: list attached excerpts, read one attached excerpt, and literal search across attached excerpts.
- Tool scope is constructed from the file excerpts explicitly attached by the user to that message. It has no workspace ID, no arbitrary root, no local companion handle and no path outside the submitted excerpt map. Unknown paths and unregistered tool names fail closed.
- The authenticated `/nexus/chat/inspect` endpoint rechecks organization/project authorization, loads owner-scoped saved history, appends the user turn with optimistic versioning, runs the bounded read-only Responses tool loop, persists the assistant answer and audits the tool-call count without storing source text or prompt content in audit metadata.
- The browser exposes a separate unchecked opt-in for read-only tools, shown only after the user attaches the active file excerpt. The default streamed chat remains unchanged. The UI states that the model can inspect only the attached excerpt.
- Tool names and count are validated by the browser. No tool can edit, create, delete, execute commands, install packages, deploy, access network resources or read unselected files.
- The existing agent runtime now replays a bounded saved conversation context and returns the names of invoked tools.
- Added API tests for safe attached-file listing/reading, secret redaction, rejected paths, owner-scoped persistence and audit metadata; added browser transport contract tests and agent-history tests.

Limitations: this does not expose the whole workspace or the existing OS-handle registry to the API. It is not a replacement for a securely paired project-wide tool bridge. No patch proposals, approval, file application, rollback, terminal/test execution, agent orchestration or cloud/background agents are enabled. The synchronous inspection request cannot guarantee cancellation of a provider operation already running on the server.




## Persistent NEXUS patch review — 2026-11-21

Feature branch: `feat/nexus-persistent-patch-review`. The review API is implemented in this branch but is not merged or production-deployed.

- Added tenant/project-scoped MongoDB patch proposal storage with creator identity, title, per-file operation, base/result SHA-256 hashes, redacted replacement content, redacted unified diff, status, optimistic version and decision metadata.
- Proposal creation revalidates the supplied base snapshot and expected hashes using the existing bounded patch builder. Paths use the existing sensitive-path and Windows-reserved-name checks; new file proposals are limited to workspace-root paths until nested directory creation is supported.
- Active project members can create proposals; only the project owner can approve or reject. Creators can read their own proposals; project owners can review proposals for the project.
- Every create/list/read/decision action is audited without recording source text, replacement content, prompts or diffs. Secrets are redacted before persistent storage.
- Approve/reject use expected-version compare-and-set. Approval records a decision only; API responses explicitly return `application_enabled=false`.

Important boundary: this does not apply any changes to a local workspace. Local application still requires a verified, short-lived, single-use approval capability that the loopback companion can independently validate, plus fresh base-hash checks and an atomic write/rollback implementation. Those safeguards are not implemented, so the Studio remains read-only.


## Chat-generated patch proposals and owner review — in review (2026-11-21)

The attached-file inspection flow now supports a separate review-only change proposal tool. When the user explicitly enables attached-file inspection and asks NEXUS to modify that file, the model may call `propose_attached_file_change`. The tool can target only the explicitly attached path, enforces per-file and aggregate bounds, redacts secrets, and captures the replacement in memory. It does not write the file.

The authenticated inspection route computes the base SHA-256 from the submitted base snapshot, validates the replacement through the patch proposal validator, persists the review record under the authenticated organization/project/author, and audits proposal creation. The panel loads the saved diff and exposes owner-only approve/reject actions with optimistic version checks.

**Approval is not application.** The proposal API and UI keep `application_enabled=false`; no file writes or shell commands occur. Applying an approved proposal still requires a separately designed single-use capability, independent local companion verification, fresh handle-relative base hash checks, safe atomic writes, rollback and recovery tests. This increment is in review and has not been merged or deployed.


## Approved one-file local application — in review (2026-11-21)

- The chat review card now exposes **Apply approved patch to selected folder** only when the server identifies the signed-in user as project owner, the proposal is approved, exactly one file is included, and the paired local companion advertises `patch:apply`.
- The browser obtains a fresh one-use challenge from the paired companion, requests an Ed25519 capability from the authenticated API for the exact approved proposal version and selected local workspace, then sends the capability and exact file operation back to that companion.
- The companion binds the challenge to the current pairing-session token and workspace, consumes it once, independently validates the issuer/audience/key ID/expiry/resource claims/patch digest/challenge, and rejects capability replay. Companion restart clears outstanding challenges.
- The companion rechecks the current base hash and uses a handle-relative atomic one-file operation. The Studio reloads the file and Explorer after success. When the companion has no pinned public key configuration, it stays read-only and does not advertise `patch:apply`.
- Multi-file proposals remain reviewable but are not applicable through this first release. Durable rollback/recovery, multi-file transactions, shell/test execution and Windows 10 build 18362 validation remain outstanding. The code is in PR #24 and is not merged or deployed; signed capability issuance was merged separately in PR #22.
