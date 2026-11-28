# Local Approved Patch Application

## Scope

This implementation connects project-owner approval to a bounded multi-file local write through the paired loopback companion. It remains a deliberately narrow, approval-gated write path, not general repository write access.

The cloud API never receives a local filesystem path. The local companion never trusts a MongoDB approval record or a browser-supplied `approved: true` flag. It requires a signed Ed25519 capability from the configured API issuer, a live companion pairing session, and a fresh one-use challenge issued by that same companion process.

## End-to-end sequence

1. The user signs in through ODID and selects an authorized organization and project in NEXUS.
2. The user connects the local companion, pairs with its one-time code, and selects one explicitly authorized workspace.
3. NEXUS creates a bounded patch proposal from the explicitly attached file excerpt. The proposal is persisted with base/result hashes and a unified diff.
4. A project owner reviews the diff and approves the exact proposal version. Approval alone does not modify the local file.
5. The browser asks the paired companion for `POST /v1/workspaces/{workspace_id}/apply-challenge`. The companion creates a cryptographically random, 60-second challenge bound to the selected workspace and current pairing-session token.
6. The browser submits that challenge to the authenticated project API's `POST .../patch-proposals/{proposal_id}/apply-capability`. The API rechecks project-owner authorization, approved status and proposal version, then signs an Ed25519 token bound to organization, project, workspace, proposal/version, the canonical patch digest and the companion challenge.
7. The browser sends the capability and exact bounded file batch to `POST /v1/workspaces/{workspace_id}/apply-patch`.
8. The companion consumes the challenge, validates the token signature against its pinned public keys, checks issuer/audience/expiry and every resource/hash binding, rejects replay, and rechecks the live file's base hash before applying.
9. The Studio reloads the changed file and refreshes Explorer from the local companion.

## Security properties

- Companion session authentication remains mandatory. The challenge is bound to that session and workspace; another paired session cannot consume it.
- Challenges are one-use and held only in process memory. Restarting the companion invalidates all outstanding challenges, so a pre-restart capability cannot be used by a new process.
- Capabilities use Ed25519, an explicit issuer and audience, a key ID, a short expiry (30–300 seconds), a unique token ID and an exact canonical patch digest.
- The API private signing key is server-side only. The local companion receives only pinned public keys.
- The companion accepts a bounded batch (up to 20 file operations and the configured aggregate content limit) and applies it as one journaled transaction; it does not silently treat a partial batch as success.
- Paths are checked by the shared patch-path validator. POSIX operations use retained directory descriptors and no-follow opens. Windows operations use relative NT file opens from the retained directory handle, reject reparse points, stage a temporary file in the same directory and rename through a least-privilege duplicate of the held parent handle. Replacement uses `NtSetInformationFile` with `FileRenameInformationEx` (class 65), `FILE_RENAME_REPLACE_IF_EXISTS` and `FILE_RENAME_POSIX_SEMANTICS`; the latter allows the hash-checked original to remain open while the staged file atomically replaces its name. There is no absolute-path fallback. The POSIX-semantics flag requires a supporting filesystem; unsupported filesystems fail closed.
- Existing file content is re-read and its SHA-256 checked immediately before replacement/deletion. Create operations refuse to overwrite an existing path.
- Request content, capability size, file size and path length are bounded. The route does not expose shell, process execution, network tools or arbitrary filesystem paths.
- The browser receives no private signing key and does not persist the capability. The token is held only for the immediate apply request.
- The companion reports whether directory-metadata durability was confirmed. POSIX attempts to flush the parent directory after the atomic namespace operation; Windows flushes staged file contents before rename but does not claim that the directory metadata was durably flushed. A false durability flag means the operation was applied in the current filesystem view, but the metadata flush could not be confirmed.

## Configuration

Configure the API signer and the companion verifier as a matched key pair:

| Component | Environment variable | Purpose |
|---|---|---|
| API | `PATCH_APPROVAL_ISSUER` | Exact HTTPS origin identifying the signing issuer |
| API | `PATCH_APPROVAL_KEY_ID` | Key ID placed in the signed capability header |
| API | `PATCH_APPROVAL_PRIVATE_KEY_B64` | Base64url-encoded raw Ed25519 private key; keep in a managed secret store |
| API | `PATCH_APPROVAL_TTL_SECONDS` | Capability lifetime, 30–300 seconds |
| Companion | `ODEI_PATCH_APPROVAL_ISSUER` | Must exactly match the API issuer |
| Companion | `ODEI_PATCH_APPROVAL_PUBLIC_KEYS` | JSON object mapping key IDs to base64url-encoded raw Ed25519 public keys |

The companion grants the `patch:apply` permission only when both issuer and a non-empty pinned public-key map are configured. If either is absent, the companion remains read-only. The public key map may contain up to 16 keys to support controlled rotation. Do not place the private key in the companion environment, web application, repository, or browser.

For key rotation, first add the new public key to the companion's pinned map, then switch the API key ID/private key, verify a staging apply, and remove the old public key only after all old capabilities have expired. Use a secret manager or KMS-backed process for private-key creation, storage and rotation; do not paste key material into ChatGPT or commit it.

## Current limits and outstanding safeguards

- **Bounded batch only.** The companion accepts at most 20 files and enforces per-file and aggregate content budgets. This is not unrestricted repository write access.
- **Rollback is bounded and hash-guarded.** The companion records a durable transaction journal and attempts reverse-order compensation when a later file operation fails. If compensation is incomplete, it returns `PATCH_BATCH_RECOVERY_REQUIRED`; inspect the journal receipt and affected paths before retrying. This is not a general user-facing undo/history system.
- **Crash recovery is local and journal-driven.** Pending transactions are reconciled when the selected workspace root is registered again. This recovery is process/filesystem scoped and does not provide a server-side project write lease.
- **No command/test execution.** The companion still exposes no shell, package installation, build/test execution, deployment or arbitrary process launch.
- **No production key configuration is present by default.** An unconfigured companion remains read-only.
- **No current-head CI or target-device verification is recorded for the active remediation branch.** The Windows 10 build 18362 target-device acceptance remains outstanding. Windows directory-metadata durability is not confirmed; the companion must continue to report that limitation honestly.
- **No production deployment or real ODID staging E2E is implied by these source changes.**

## Verification

The test suite includes challenge expiry/session binding/replay, signed capability validation, wrong-workspace and changed-content rejection, stale-base rejection, multi-file create/update/delete rollback and crash-recovery paths. These tests have not been executed against the current remediation branch; no current-head CI result is claimed.


## Project lifecycle boundary

The companion holds a per-workspace in-process lock across the local filesystem
transaction. That lock is not a durable server-side project lease and cannot be
used by a project-deletion worker to prove that all desktop writers have
drained. A future API/companion lease protocol must bind the selected workspace,
organization, project, capability and transaction ID; renew while the
filesystem journal is active; and release only after commit or recovery. Until
that protocol and deletion-side drain are implemented and fault-tested,
complete project deletion must remain unavailable.
