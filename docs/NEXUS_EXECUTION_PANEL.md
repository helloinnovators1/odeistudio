# NEXUS Chat Panel — Execution Workflow

## Operator workflow

1. Sign in through ODID Authorization Code + PKCE and select an authorized organization and project.
2. Create a NEXUS task plan. A project owner must approve the plan before execution is available.
3. Connect the local companion and select the workspace. The browser reads only the companion's enumerated file list and file-content endpoint; it does not gain arbitrary filesystem access.
4. Select a server-approved execution profile. The profile list comes from the API and contains identifiers only; OCI image digests and commands remain server-side.
5. Check both independent consent boxes: workspace snapshot upload and code execution. Review the filtered-file warning and explicitly confirm before upload.
6. The browser creates a bounded ZIP snapshot in memory and submits it to the authenticated execution API. The API independently validates archive safety and stores it in GridFS.
7. The API atomically transitions the approved task to executing and enqueues a run. The panel polls status and exposes cancellation.
8. After terminal completion, the panel requests redacted stdout/stderr through the tenant-scoped artifact route. A successful sandbox exit moves the task to validating; it does not mark the task complete.

## Browser-side snapshot policy

The current snapshot builder includes at most 2,000 readable text files, 2 MiB per file and 40 MiB aggregate content. It excludes known secret/credential paths, VCS metadata, dependency/build/cache directories, binary content containing NUL bytes, duplicate case-insensitive paths and non-portable or traversal paths. ZIP entries use the stored (uncompressed) method. The server applies its own independent archive and credential-path validation.

Files skipped because they are unreadable, binary, oversized, unsafe or beyond the aggregate budget are counted and up to 50 paths are shown to the operator; the operator must confirm continuing with a partial snapshot. The snapshot is immutable once uploaded. This workflow does not write files back to the local workspace.

## Identity and cancellation

ODID access tokens and companion tokens remain in browser memory and are not written to localStorage or sessionStorage. The execution API client refuses non-HTTPS API origins except loopback development origins and sends credentials with `credentials: omit`. If identity, organization, project or selected workspace changes while an upload is being prepared, the UI avoids sending a stale snapshot; if a run is created after the context changed, it immediately requests cancellation.

Task cancellation propagates to any active execution run. A queued run and its task are cancelled transactionally; an active worker receives durable cancellation intent and must terminate the sandbox and confirm cleanup before the run becomes cancelled.

## Current limitations

The panel currently supports bounded one-shot execution, status polling, cancellation and completed output retrieval. It does not provide an interactive shell, live stdout streaming, arbitrary user commands, browser-selected runtime images, multi-run task history or automatic repair loops. It depends on a separately deployed worker, a configured digest-pinned profile registry, MongoDB GridFS and a hardened OCI runtime. Production enablement requires real ODID staging configuration, worker host validation, secret-scanning policy, malware/content scanning, MAD telemetry and acceptance testing.