# NEXUS Attached-Excerpt Inspection

**Status:** implemented on the feature branch; read-only and deliberately narrower than whole-project repository access.

## Request path

The Studio user must:
1. Sign in through the configured ODID authorization-code + PKCE client.
2. Select a server-discovered organization and an authorized project.
3. Explicitly attach the active file excerpt.
4. Separately enable **Allow NEXUS read-only tools on this attached excerpt**.
5. Give per-request cloud-model consent and send the message.

The browser calls the authenticated project-scoped endpoint:

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/chat/inspect`

The endpoint rechecks project access, loads the conversation belonging to the verified issuer/subject, appends the user turn with optimistic versioning, runs the bounded stateless NEXUS Responses tool loop, persists the assistant answer, and audits the outcome and tool-call count. Prompts and source text are not written to audit metadata.

## Tool allowlist

| Tool | Inputs | Effect |
|---|---|---|
| `list_attached_excerpts` | none | Lists paths and character counts for excerpts attached to this request |
| `read_attached_excerpt` | exact attached relative path | Returns the already-attached, secret-redacted excerpt |
| `search_attached_excerpts` | literal query up to 200 characters | Returns at most 10 matching lines, bounded to 400 characters each |

Schemas are strict and reject additional properties. The runtime caps the tool loop at six rounds and twelve calls. The excerpt map accepts one to five files, at most 8,000 characters per excerpt, and a combined path/content budget of 40,000 characters. Browser request bounds are validated before network access.

## Security boundaries

- No workspace ID, arbitrary root, companion handle, local filesystem access, or path outside the explicitly attached excerpt map is passed to the model.
- Path inputs must be safe relative paths and must exactly match an attached excerpt. Duplicate case-insensitive paths are rejected.
- Secrets are redacted before model context and again in tool output.
- Unknown tool names, unattached paths and malformed argument objects fail closed.
- Server authorization is independent of browser UI state and is repeated for every request.
- Explicit cloud consent is required; no token is persisted by the browser transport.
- Conversation history is owner-, organization- and project-scoped and version-checked.
- Audit metadata records outcome, counts, model and bounded tool-call count, not prompts or source contents.
- The tool mode cannot modify files, create proposals, approve patches, execute shell commands, run tests, install packages, deploy, or access the network.

## Cancellation and failure semantics

The browser can abort the inspection request and stop waiting for the response. Because the agent runtime runs synchronously in a worker thread, aborting the browser request does not guarantee cancellation of an upstream model operation already running on the server. The UI must describe this as best-effort rather than guaranteed provider cancellation.

User turns are persisted before model execution. If the model fails, the user turn remains in conversation history; the assistant response is not persisted. The client displays a safe error and the user may retry with a new message.

## Verification

Tests cover strict schemas, safe path checks, excerpt listing/reading/search, secret redaction, unregistered tool rejection, bounded saved-history replay, authenticated route authorization, conversation persistence, audit tool counts and browser response validation. GitHub Actions on branch head `4bf3795970f6cdd1355654c540d63bec710cb438` completed 10/10 checks successfully. No local tests or live ODID staging verification were performed in this hosted session.

## Remaining work

This is not a project-wide tool bridge. Next capabilities require separate security design and tests:
- Read-only full-project tools backed by the paired companion's retained OS handles, with an authenticated, expiring and project-bound capability.
- Chat-driven patch proposal creation and review cards bound to immutable proposal/version hashes.
- Explicit approval and safe application with recovery/rollback.
- Isolated command/test execution with resource, filesystem and network policy.
- Agent orchestration, task checkpoints, cancellation and human review.
