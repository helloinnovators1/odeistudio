# Local Approved Patch Application

## Scope

This increment connects project-owner approval to a single-file local write through the paired loopback companion. It is a deliberately narrow first application path, not general repository write access.

The cloud API never receives a local filesystem path. The local companion never trusts a MongoDB approval record or a browser-supplied `approved: true` flag. It requires a signed Ed25519 capability from the configured API issuer, a live companion pairing session, and a fresh one-use challenge issued by that same companion process.

## End-to-end sequence

1. The user signs in through ODID and selects an authorized organization and project in NEXUS.
2. The user connects the local companion, pairs with its one-time code, and selects one explicitly authorized workspace.
3. NEXUS creates a bounded patch proposal from the explicitly attached file excerpt. The proposal is persisted with base/result hashes and a unified diff.
4. A project owner reviews the diff and approves the exact proposal version. Approval alone does not modify the local file.
5. The browser asks the paired companion for `POST /v1/workspaces/{workspace_id}/apply-challenge`. The companion creates a cryptographically random, 60-second challenge bound to the selected workspace and current pairing-session token.
6. The browser submits that challenge to the authenticated project API's `POST .../patch-proposals/{proposal_id}/apply-capability`. The API rechecks project-owner authorization, approved status and proposal version, then signs an Ed25519 token bound to organization, project, workspace, proposal/version, the canonical patch digest and the companion challenge.
7. The browser sends the capability and exact single-file proposal to `POST /v1/workspaces/{workspace_id}/apply-patch`.
8. The companion consumes the challenge, validates the token signature against its pinned public keys, checks issuer/audience/expiry and every resource/hash binding, rejects replay, and rechecks the live file's base hash before applying.
9. The Studio reloads the changed file and refreshes Explorer from the local companion.

## Security properties

- Companion session authentication remains mandatory. The challenge is bound to that session and workspace; another paired session cannot consume it.
- Challenges are one-use and held only in process memory. Restarting the companion invalidates all outstanding challenges, so a pre-restart capability cannot be used by a new process.
- Capabilities use Ed25519, an explicit issuer and audience, a key ID, a short expiry (30–300 seconds), a unique token ID and an exact canonical patch digest.
- The API private signing key is server-side only. The local companion receives only pinned public keys.
- The companion accepts exactly one file operation per apply request. Multi-file proposals are not silently partially applied.
- Paths are checked by the shared patch-path validator. POSIX operations use retained directory descriptors and no-follow opens. Windows operations use relative NT file opens from the retained directory handle, reject reparse points, stage a temporary file in the same directory and rename through the directory handle.
- Existing file content is re-read and its SHA-256 checked immediately before replacement/deletion. Create operations refuse to overwrite an existing path.
- Request content, capability size, file size and path length are bounded. The route does not expose shell, process execution, network tools or arbitrary filesystem paths.
- The browser receives no private signing key and does not persist the capability. The token is held only for the immediate apply request.

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

- **Single-file only.** The current companion apply endpoint requires exactly one file. The chat-generated attached-file proposal flow fits this scope. Multi-file proposals remain reviewable but cannot be applied through this endpoint.
- **No automatic rollback yet.** A single file is replaced or created atomically on the supported filesystem path, but the product does not yet maintain a durable backup/transaction journal or expose a rollback action. Make a Git commit or other external backup before applying important changes.
- **No crash-recovery journal.** The one-file replacement itself is atomic; a process interruption around metadata durability still requires filesystem-level recovery procedures. There is no multi-file transaction to recover.
- **No command/test execution.** The companion still exposes no shell, package installation, build/test execution, deployment or arbitrary process launch.
- **No production key configuration is present by default.** An unconfigured companion remains read-only.
- **No user-machine verification has occurred yet.** CI must pass on Windows and Ubuntu, and the companion must then be installed and tested on the user's Windows 10 build 18362 environment before claiming that local application works on that machine.
- **No production deployment or real ODID staging E2E is implied by these source changes.**

## Verification

The acceptance suite covers challenge expiry/session binding/replay, signed capability validation, wrong-workspace and changed-content rejection, stale-base rejection, atomic create/update/delete, and browser request/response contracts. GitHub Actions on the exact PR head—not this design document—determines whether the implementation passes Windows, Ubuntu, web, MongoDB and security checks.
