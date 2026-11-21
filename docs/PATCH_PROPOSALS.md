# NEXUS Patch Proposal Contract

## Purpose and current boundary

The pure patch proposal validator validates bounded, multi-file text changes and produces immutable review data with unified diffs and SHA-256 content identities. It does not open workspace paths or apply edits. A separate authenticated API layer persists proposal records and records project-owner review decisions; it still does not apply edits or execute commands.

Callers must obtain the base snapshot through the existing authenticated, tenant/project-authorized workspace boundary. Never pass arbitrary client-supplied file contents as proof of the current workspace state. The base snapshot must be fresh, bounded, and derived from the selected workspace.

## Proposal inputs

- A mapping of relative workspace paths to UTF-8 base text.
- A mapping of changed paths to replacement text; `null` means delete.
- Exactly one expected base SHA-256 per changed path. New files use `null`; updates and deletes must match the hash of the supplied base text.

## Validation

- Reject absolute, drive-qualified, traversal, empty-component, NUL and backslash paths, Windows-reserved device names (including COM/LPT aliases), alternate data streams, invalid Windows filename characters, overlong components and non-NFC Unicode aliases.
- Reject sensitive paths and excluded directories such as `.git`, `.ssh`, `.aws`, `.env*`, credentials, private keys and dependency directories.
- Reject case-insensitive duplicate paths and file/directory hierarchy collisions in both the base snapshot and proposed changes.
- Reject stale/malformed hashes, deletion of missing files, binary/NUL content and invalid UTF-8 text.
- Enforce at most 20 changed files, 1 MB per base/replacement file, 5 MB aggregate changed base and replacement content, and 8 MB aggregate unified diff. Require NFC-normalized paths and enforce Windows UTF-16 component length and device-name rules.
- Return per-file operation, base/result hashes, replacement content and unified diff.

## Local companion preview endpoint

The read-only companion exposes `POST /v1/workspaces/{workspace_id}/patch-proposals`. It requires an active paired bearer session and a selected workspace ID. For updates/deletes it re-reads each target through the retained workspace handle, compares the supplied base SHA-256, and returns the generated diffs. New-file previews are currently limited to workspace-root paths; nested directory creation is not inferred.

The response explicitly reports `mode: preview_only` and `writes_performed: false`. The endpoint does not persist the proposal, authorize it, apply it, or provide a shell. It is a local preview boundary, not the cloud project/task API or a complete code-editing workflow.

The React workspace now exposes a `Preview patch` action for the active file. The user edits proposed replacement text in a separate dialog; the browser computes the base SHA-256 with Web Crypto, calls the local endpoint, validates the preview response contract, and displays the unified diff. This UI does not enable saving or applying changes.

## Current delivery and remaining stages

Completed in the authenticated API and NEXUS panel:

1. Tenant/project/author-scoped MongoDB persistence with immutable file hashes and bounded review content.
2. Saved proposal listing and detail retrieval, unified-diff review, project-owner-only approve/reject decisions, and optimistic version checks.
3. Audit events for proposal creation, listing, reading and decisions without placing prompt/source content or diffs in audit metadata.
4. Chat-triggered proposal generation for explicitly attached files only. The model can prepare a replacement, but the tool is review-only and never writes local files.

Still required before any local application:

1. Re-read every target through the secure workspace handle and independently verify all base hashes immediately before application.
2. Issue a short-lived, single-use approval capability that the local companion independently verifies; a MongoDB approval record alone must never authorize local writes.
3. Implement atomic, handle-relative Windows writes and POSIX descriptor-relative writes, same-directory staging, no-follow/reparse protections, rollback, recovery and race tests. Do not use path-based writes or bypass the existing read-only scanner.
4. Record application, rollback and failure events in the audit trail.
5. Add isolated terminal/test execution only after a separately designed sandboxed execution service is available.

The current delivery supports proposal generation, persistence, review and owner decisions only. `application_enabled` remains false; execution, safe application, rollback and test orchestration are not enabled.


## Chat-generated proposals and owner decisions

The NEXUS chat inspection route can now capture a generated replacement for an explicitly attached file through the `propose_attached_file_change` tool. It stores the original base snapshot only in request memory, redacts the replacement, computes the base/result hashes, validates the diff, and persists the proposal in the tenant/project-scoped MongoDB store. Audit events record proposal creation and owner decisions without copying source content or diffs into audit metadata.

The browser panel lists proposals, displays unified diffs, and exposes approve/reject controls only when the server confirms the authenticated identity is the project owner. Decisions use optimistic versions. The response and UI always state `application_enabled: false`.

Approval remains a review decision, not permission for the browser or API to write local files. Do not add an apply button until the local companion can independently verify a short-lived, single-use approval capability, re-read every target using retained safe handles, compare fresh base hashes, stage atomic writes, and roll back on failure.


## Signed local apply — in review

PR #22 adds an owner-only API route that issues a short-lived Ed25519 capability only for a proposal already approved at the expected version. The capability binds organization, project, workspace ID, proposal ID/version, a canonical SHA-256 digest of exact file operations and replacement bytes, and a fresh companion-issued challenge. Signing fails closed unless the server-side issuer, key ID and private key are configured together.

PR #24 adds the loopback companion's challenge endpoint and apply endpoint. The companion binds a 60-second challenge to the current pairing session and selected workspace, consumes it once, independently verifies the Ed25519 signature against pinned public keys, validates the exact patch digest and resource claims, and rejects replay. The Studio requests the challenge, obtains an owner-authorized capability and sends the exact approved one-file operation to the selected companion workspace. It reloads the file from disk after success.

The first application path is deliberately single-file. It uses same-directory staging and atomic replacement/create on POSIX, and relative NT file opens plus handle-based rename/delete on Windows. Base hashes are rechecked immediately before the operation. Multi-file application is disabled; the UI directs users to split proposals into one-file changes.

**Still outstanding:** durable rollback and recovery journals, crash-recovery, multi-file transactional application, and real user-machine validation on Windows 10 build 18362. Do not treat this in-review code as deployed or production-ready.
