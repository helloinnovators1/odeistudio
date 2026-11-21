# Local patch-application capabilities

**Status: signing foundation only. Local file application remains disabled.**

ODEI now has an Ed25519 capability format for authorizing one exact approved patch against one exact local workspace. The authenticated API exposes an owner-only capability issuance route:

`POST /api/v1/organizations/{organization_id}/projects/{project_id}/nexus/patch-proposals/{proposal_id}/apply-capability`

The request requires the current approved proposal version, the opaque workspace ID returned by the local companion, and `confirm_apply: true`. The API refuses to issue a capability unless the proposal is approved at the expected version and the caller is the project owner.

## Signing configuration

The API requires all three settings together:

- `PATCH_APPROVAL_ISSUER`: the exact HTTPS API issuer origin.
- `PATCH_APPROVAL_KEY_ID`: a 1–64 character ASCII key identifier.
- `PATCH_APPROVAL_PRIVATE_KEY_B64`: base64url-encoded 32-byte Ed25519 private key material, stored only in the server secret manager.

`PATCH_APPROVAL_TTL_SECONDS` is bounded to 30–300 seconds (default 60). Do not put a private key in source control, browser configuration, a workspace file, or a chat message. Do not enable this configuration until the local companion's pinned public-key verifier and atomic apply implementation are deployed together.

The companion will need the matching raw Ed25519 public key, encoded as base64url and pinned under the same key ID. Key rotation should add the new public key before switching the API signer, then remove the old public key after all outstanding short-lived capabilities expire.

## Capability binding

The signed EdDSA JWT binds:

- API issuer and `odei-local-companion` audience;
- authenticated subject and issuer, organization and project;
- exact opaque workspace ID;
- proposal ID and approved proposal version;
- SHA-256 digest of canonical file operations (path, operation, base hash, result hash and replacement content);
- unique `jti`, issue time and expiry.

The local verifier must recompute the canonical digest from the exact payload it receives, compare every claim, reject untrusted key IDs and consume the `jti` once. It must then independently re-read every target through retained directory handles and compare live base hashes before any write. A cloud approval record or valid JWT alone is never sufficient to skip local verification.

## Current limitations

The capability route currently returns `application_enabled: false`. The browser panel does not request or transmit capabilities, and the local companion does not yet verify them or accept write requests. No local files can be changed through this foundation.

Still required before enabling application: pinned public-key loading in the companion, replay-safe verification, project-to-local-workspace binding, handle-relative Windows/POSIX staging, atomic replacement, multi-file rollback, crash recovery journal, application receipt/audit, and Windows 10 build 18362 validation. Until those gates pass, keep the companion read-only.
