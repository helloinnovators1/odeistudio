# NEXUS Patch Proposal Contract

## Purpose and current boundary

The patch proposal service validates bounded, multi-file text changes and produces immutable review data with unified diffs and SHA-256 content identities. It is deliberately read-only: it does not open workspace paths, persist proposals, apply edits, execute commands, or approve changes.

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

## Required next stages

1. Persist proposals with tenant, project, task, author, expiry, and immutable content hashes.
2. Render the exact proposal in the IDE diff/review surface; require explicit reviewer decision.
3. Re-read every target through the secure workspace handle, verify all base hashes, and reject stale snapshots before applying anything.
4. Implement atomic, handle-relative Windows writes and POSIX descriptor-relative writes, with same-directory staging, no-follow/reparse protections, rollback, and race tests. Do not use path-based writes or bypass the existing read-only scanner.
5. Record proposal, approval, application, rollback and failure events in the audit trail.
6. Run isolated tests and diagnostics only after the separately designed sandboxed execution service is available.

The current module implements only validation and diff generation. Persistence, IDE review, approval, safe application, rollback, execution and test orchestration remain unimplemented.
