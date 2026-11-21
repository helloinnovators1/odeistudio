# Local patch-application capabilities

**Status: one-file local application is implemented and merged in PR #24.** The API issues a short-lived Ed25519 capability; the paired local companion independently verifies it and applies one approved file. The API itself never writes to a local filesystem. The response field `application_enabled: false` means that no cloud-side write is performed; it does not disable the separately authorized companion apply operation.

## End-to-end route

The authenticated API exposes:

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/patch-proposals/{proposal_id}/apply-capability`

The request requires the approved proposal version, opaque workspace ID, a fresh one-use companion challenge and `confirm_apply: true`. Only the project owner can obtain the capability, and the proposal must be approved at the expected version.

The browser obtains a challenge from the paired companion and forwards it to the API. The API signs a capability bound to the organization, project, verified identity, workspace, proposal/version, canonical patch digest and challenge. The browser sends that capability and the exact proposal payload to the companion's `POST /v1/workspaces/{workspace_id}/apply-patch` route. The companion verifies the signature and bindings, consumes the challenge, rechecks the live base hash and applies exactly one file.

## Signing configuration

The API requires all three settings together:

- `PATCH_APPROVAL_ISSUER`: the exact HTTPS API issuer origin.
- `PATCH_APPROVAL_KEY_ID`: a 1–64 character ASCII key identifier.
- `PATCH_APPROVAL_PRIVATE_KEY_B64`: base64url-encoded 32-byte Ed25519 private key material, stored only in a managed server-side secret store.

`PATCH_APPROVAL_TTL_SECONDS` is bounded to 30–300 seconds (default 60). Never put a private key in source control, browser configuration, a workspace file or a chat message.

The companion must be configured with the matching raw Ed25519 public key, encoded as base64url and pinned under the same key ID. Rotate keys by adding the new public key before switching the API signer, then remove the old key after all outstanding short-lived capabilities expire.

## Capability binding and local enforcement

The signed EdDSA JWT binds:

- API issuer and `odei-local-companion` audience;
- authenticated subject and issuer, organization and project;
- exact opaque workspace ID;
- proposal ID and approved proposal version;
- SHA-256 digest of canonical file operations (path, operation, base hash, result hash and replacement content);
- unique `jti`, issue time and expiry.

The local verifier recomputes the canonical digest from the exact payload, compares every claim, rejects untrusted key IDs and consumes the challenge/token ID once. It then independently re-reads the target through retained directory handles and compares live base hashes before mutation. A cloud approval record or valid JWT alone is never sufficient.

## Implemented scope and limitations

- Exactly one file operation is accepted per apply request. Multi-file proposals are rejected rather than partially applied.
- Create operations refuse to overwrite an existing path. Update/delete operations re-read the live file and compare its SHA-256 with the approved base hash.
- POSIX uses retained directory descriptors and no-follow operations. Windows uses retained directory handles, reparse-point protections, a staged same-directory file and `NtSetInformationFile(FileRenameInformationEx=65)` with POSIX-semantics replacement. Unsupported filesystems fail closed; there is no absolute-path fallback.
- The companion reports whether directory-metadata durability was confirmed. Windows flushes staged file contents before rename but does not claim that directory metadata was durably flushed.
- The browser exposes Apply only for an approved one-file proposal when the paired companion advertises `patch:apply`. Pairing, explicit local write opt-in, signed capability and a fresh challenge are all required.
- The operation is single-file atomic replacement, not a multi-file transaction. Durable rollback journals, crash recovery and multi-file rollback are not implemented.
- Shell, process execution, network tools, package installation and arbitrary filesystem writes remain unavailable.

## Verification and release gates

PR #24 merged as `1a5e6d9479b4a5b0dfac6d09b6dba61aac42163b`. Its exact source head passed Windows and Ubuntu CI on Python 3.10/3.12, MongoDB replica-set integration, web tests/build, CodeQL, secret scanning and Python/web dependency audits.

The companion has not yet been installed and exercised on the user's Windows 10 build 18362 device. Before production use, configure the matched API signer and companion public key through managed configuration, perform a real ODID-to-browser-to-local-companion staging test, validate the user's exact Windows/filesystem combination, and verify backup/restore and operational monitoring. Do not paste secrets or tokens into chat.
