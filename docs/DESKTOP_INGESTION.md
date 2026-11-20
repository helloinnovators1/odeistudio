# Desktop Project Ingestion — Safe Local Folder Scanning

## Goal
Allow a user to authorize ODEI Studio to index selected local project folders without requiring manual ZIP packaging. This is a product design, not a statement that ChatGPT's Chrome extension currently has unrestricted filesystem access.

## Browser security boundary
A normal browser extension or web page cannot silently enumerate arbitrary Windows folders. File System Access APIs require user interaction and browser support; directory access is permission-scoped and may need to be reauthorized. Do not promise unattended access outside the granted scope.

## Supported approaches
1. **ODEI Studio local companion (preferred for recursive project scanning):** a user-installed local service/CLI with explicit folder selection, visible status, revocable authorization and a narrow authenticated API to the ODEI Studio web app.
2. **Browser directory picker:** use supported directory selection APIs when available; request permission through a user gesture and handle permission revocation and unsupported browsers.
3. **Git provider ingestion:** use a GitHub App installation to index repositories where the user grants access.
4. **Desktop automation:** use an explicitly supported desktop/Computer Use workflow where available; it is not a substitute for a dedicated, secure filesystem agent.

## Local companion security
- Bind to loopback only; authenticate requests with short-lived pairing tokens and origin checks.
- Require explicit user selection of each root folder.
- Display active roots, indexing status and last access; provide immediate pause/revoke.
- Respect .gitignore and configurable excludes; exclude .env, credentials, private keys, dependency folders, build output and large/binary files by default.
- Prevent path traversal and symlink escape; enforce file count, size and rate limits.
- Send only user-authorized files; show a preview/manifest before upload.
- Encrypt transport; never expose local service to public network interfaces.
- Keep an audit log of selected roots and indexing actions without recording file secrets.
- Provide incremental indexing by content hash and file metadata.
- Never execute scanned files automatically.

## Initial implementation stages
1. Local CLI lists files under an explicitly supplied root and applies safe excludes.
2. CLI emits a manifest with relative path, size, modified time and content hash.
3. User reviews and approves the manifest.
4. Selected text files are streamed in bounded batches to an authenticated API.
5. Server stores index metadata and content according to retention policy.
6. User can pause, revoke, remove a root or delete indexed content.

## Acceptance tests
Verify permission revocation, symlink traversal, path traversal, ignored secrets, binary/oversized files, interrupted upload, duplicate content, incremental re-index, tenant authorization and deletion.
