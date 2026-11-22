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

The execution worker must build a new snapshot from an explicitly authorized project/workspace version. Snapshot ingestion must reject absolute paths, traversal, symlinks, hard links, device/FIFO/socket entries, duplicate normalized paths, oversized files and aggregate size/file-count overflow. It must record a content digest and provenance. Snapshot extraction and object-store persistence are not part of the current runner module and must be implemented before exposing execution to users.

## Tool and profile contract

NEXUS may select only profile identifiers registered by the server, such as `python-tests`, `python-lint`, `node-tests` and `node-build`. The profile registry binds each identifier to a verified image digest, fixed executable/entrypoint, allowed argument grammar, resource budget and timeout. The model must not provide shell strings; commands are passed as argument vectors and never through a shell.

## Worker and persistence requirements

The durable run/lease store is now implemented in services/execution_runs.py with transactional run/event writes, worker claim and heartbeat, lease expiry reclamation, version checks and cancellation intent. See EXECUTION_RUNS.md. It remains an internal persistence layer, not a public execution service. The next integration layer must provide:
1. MongoDB-backed execution-run records and append-only events with optimistic versions.
2. Atomic task/run/event/audit transitions and transaction-capable MongoDB topology.
3. A worker lease with heartbeat, lease expiry, retry limits and idempotent completion.
4. Cancellation that terminates the container and confirms cleanup.
5. Bounded, redacted logs and artifacts with tenant-scoped retrieval and retention.
6. Worker readiness and queue-depth metrics with freshness timestamps.
7. Recovery for worker restart, lost lease, timeout, partial artifact upload and orphaned containers.
8. API authorization on every read, create, approve, cancel and artifact request.

## Current implementation status

The branch `feat/nexus-isolated-execution-engine` adds `services/execution_sandbox.py`, a shell-free OCI command builder and runner with digest-pinned profiles, network isolation, non-root execution, read-only root filesystem, capability drop, no-new-privileges, resource limits, bounded output, workspace containment checks, link/special-file rejection and cleanup attempts. Unit/contract tests are added for the security arguments, workspace validation and runner result handling.

This remains an execution-backend foundation plus a durable run/lease persistence layer only. The API CI run on commit `df36b08` passed on Ubuntu and Windows with Python 3.10 and 3.12: Ubuntu reported 264 passed and 10 skipped on each version; Windows reported 266 passed and 8 skipped on each version. MongoDB replica-set integration and web tests/build passed. CodeQL, secret scanning and Python/web dependency audits also passed. The in-process server-approved profile registry is implemented, but it is not yet connected to authenticated tenant-scoped profile selection, NEXUS task approval, durable execution-run records, snapshot creation/storage, a worker queue, API routes, cancellation events, artifact retrieval or MAD metrics. No production command execution is enabled by this branch.

## Acceptance gates

- Prove network isolation and host-path isolation against the supported OCI runtime.
- Verify image signatures/provenance and pin immutable digests.
- Test path traversal, symlink/hard-link races, archive bombs, oversized output and malformed arguments.
- Verify non-root identity, read-only rootfs, dropped capabilities, no-new-privileges, PID/CPU/memory/time limits and cleanup after timeout/cancel.
- Prove tenant isolation for tasks, snapshots, runs, logs and artifacts.
- Test worker crash/restart, lease expiry, duplicate delivery, cancellation races and audit rollback.
- Run the full end-to-end path: project snapshot → approved task → sandbox run → test report → reviewable artifact → user acceptance.
- Do not mark execution operational until the actual worker host, OCI runtime, image digests, queue, storage and monitoring are configured and tested.
