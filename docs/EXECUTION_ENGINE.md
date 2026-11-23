# NEXUS Isolated Execution Engine

## Purpose

The execution engine runs explicitly approved build, test, lint and diagnostic commands in disposable workspaces. It is a separate trust boundary from the NEXUS model runtime, browser and local companion. Repository content and command output are untrusted data; neither can grant additional capabilities.

## Required lifecycle

`planned → owner_approved → queued → leased → preparing → running → collecting → validating → completed`

Terminal alternatives are `failed`, `cancelled` and `expired`. Each transition must be tenant/project scoped, version checked, durable and represented by an append-only event. A plan approval is not blanket permission to execute arbitrary commands: the approved execution request must identify its profile, workspace snapshot, command arguments, resource budget and expiry.

## Execution boundary

The first backend is an OCI-container runner intended for a dedicated Linux worker host:

- Use a server-defined execution profile with a digest-pinned image. Never accept an image, runtime flag or host path from the browser or model.
- Use an unprivileged fixed UID/GID, read-only container root filesystem, dropped Linux capabilities, no-new-privileges, default seccomp, PID/memory/CPU limits and a bounded tmpfs.
- Disable network access by default. A future network-enabled profile requires a separately reviewed egress policy and explicit approval.
- Mount only a fresh, worker-created project snapshot at `/workspace`. Never mount the host home directory, Docker socket, SSH agent, cloud metadata socket, secret store or production credentials.
- Do not inherit host environment variables into the container. The initial runner supplies only fixed non-secret environment values.
- Pulling images at job time is disabled. The worker must pre-provision and verify approved digest-pinned images.
- Bound command arguments, wall-clock duration, stdout/stderr capture and workspace entry count. Always attempt to stop and remove the container after completion, timeout or cancellation.
- Treat the mounted workspace as disposable. Preserve user source by snapshotting it before execution; copy validated artifacts back only through a separate approved patch/review workflow.

## Snapshot contract

The authenticated execution API accepts only explicitly consented bounded workspace archives and validates them through the snapshot ingestor before GridFS storage. The worker retrieves tenant/project/task-bound metadata, re-ingests the archive into a fresh private workspace and verifies the deterministic content-manifest digest before invoking the sandbox. This path is integrated in the repository; production content/DLP/malware scanning policy, hardened runtime and live staging acceptance remain required.

## Tool and profile contract

NEXUS may select only profile identifiers registered by the server, such as `python-tests`, `python-lint`, `node-tests` and `node-build`. The profile registry binds each identifier to a verified image digest, fixed executable/entrypoint, allowed argument grammar, resource budget and timeout. The model must not provide shell strings; commands are passed as argument vectors and never through a shell.

## Worker and persistence requirements

The durable run/lease store is integrated with authenticated execution routes and the standalone worker. It provides transactional run/event/audit/task transitions, tenant-scoped access, worker leases and renewal, expiry reclamation, retry limits, cancellation intent, bounded redacted artifacts and retention. The operational recovery boundary remains subject to staging tests for worker crash/restart, duplicate delivery, cancellation races, partial GridFS writes, orphaned containers and orphaned blobs.

## Current implementation status

The integrated mainline includes `services/execution_sandbox.py`, a shell-free OCI command builder and runner with digest-pinned profiles, network isolation, non-root execution, read-only root filesystem, capability drop, no-new-privileges, resource limits, bounded output, workspace containment checks, link/special-file rejection and cleanup attempts. Unit/contract tests cover the security arguments, workspace validation and runner result handling.

The integrated repository now contains the authenticated tenant-scoped execution API, task approval/consent gate, snapshot storage, durable run/events, standalone worker, cancellation and artifact retrieval, plus worker heartbeat and private MAD aggregate metrics. The assembled mainline commit `47fcd781a39bfff27a60eee7bc77b5ea9fe4685c` passed the Windows/Ubuntu Python 3.10/3.12 matrix, MongoDB integration, web, dependency audits and secret scanning; CodeQL was still in progress at the last check. Follow-up commit `21b6ffbf73dd575f29050c00a49cbe1abb3ceefe` corrects MAD worker-state classification and adds regression tests; its exact-head CI must finish before the fix is considered verified. No production command execution is enabled until a dedicated hardened worker host, reviewed profiles and staging acceptance exist.

## Acceptance gates

- Prove network isolation and host-path isolation against the supported OCI runtime.
- Verify image signatures/provenance and pin immutable digests.
- Test path traversal, symlink/hard-link races, archive bombs, oversized output and malformed arguments.
- Verify non-root identity, read-only rootfs, dropped capabilities, no-new-privileges, PID/CPU/memory/time limits and cleanup after timeout/cancel.
- Prove tenant isolation for tasks, snapshots, runs, logs and artifacts.
- Test worker crash/restart, lease expiry, duplicate delivery, cancellation races and audit rollback.
- Run the full end-to-end path: project snapshot → approved task → sandbox run → test report → reviewable artifact → user acceptance.
- Do not mark execution operational until the actual worker host, OCI runtime, image digests, queue, storage and monitoring are configured and tested.


## Workspace snapshot ingestion

A bounded ZIP ingestion module is integrated into the authenticated execution API and worker path. It validates archive metadata and expanded bytes, rejects unsafe path/link entries and creates a deterministic content snapshot in a fresh worker directory. GridFS stores the archive and tenant-scoped metadata. Production scanning policy and staging acceptance remain open.


## Authenticated API and snapshot storage

The API provides authenticated project/task-scoped execution profile listing, execution creation with separate upload and execution consent, run reads, cursor-paginated events, cancellation requests and tenant-authorized artifact retrieval. GridFS stores archive bytes; metadata and run records are tenant scoped. Creation atomically consumes the approved task and creates the run/event/audit records. See EXECUTION_API.md. This is still not a live worker deployment.


## Standalone worker and result lifecycle

A separate `odei-execution-worker` process is implemented. It claims and heartbeats leases, validates snapshot tenant bindings and content digest, runs only the configured OCI profile, polls cancellation, persists redacted bounded stdout/stderr, finalizes run/task state, fails exhausted attempts and schedules snapshot/artifact retention cleanup. It is not deployed or operational until a dedicated host, OCI runtime, reviewed profile digests and environment are configured. See EXECUTION_WORKER.md.
