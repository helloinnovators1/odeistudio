# Verified Delivery Snapshot — 2026-11-22

This document records the repository state verified on `main` at commit
`6106b06cb4cdbab625c7628991a67c8f0edbc794`. It is a point-in-time engineering
snapshot, not a production-readiness declaration. Older historical notes in
other documents must not override the merged source and current CI evidence.

## Mainline and CI

- PR #45, **Connect approved NEXUS single-file local apply flow**, is merged.
- Main commit: `6106b06cb4cdbab625c7628991a67c8f0edbc794`.
- PR #45 exact-head checks passed 21/21.
- Post-merge API CI run [45004675704](https://github.com/helloinnovators1/odeistudio/actions/runs/45004675704)
  completed successfully on this commit.
- Post-merge Security Scanning run
  [45004675660](https://github.com/helloinnovators1/odeistudio/actions/runs/45004675660)
  completed successfully on this commit.
- This verifies GitHub-hosted checks only. It does not prove target-device
  compatibility, production configuration, staging acceptance or deployment.

## Delivered repository capabilities

| Area | Verified implementation | Remaining acceptance |
|---|---|---|
| NEXUS chat | Browser PKCE client foundation, authorized organization/project selection, consent, chat transport/streaming and cancellation, durable owner-scoped conversations, attached excerpt inspection, task planning/approval and patch proposal review | Real ODID issuer/client/redirect/resource/scope registration, production API issuer/JWKS/CORS, staging identity and tenant tests |
| NEXUS execution | OCI sandbox foundation, durable runs/events/leases, bounded workspace snapshots, authenticated execution API/worker, panel execution, event timeline and project-wide execution history | Dedicated hardened Linux worker, immutable profiles, production storage/secrets, staging E2E, crash/retry/cancellation/recovery drills |
| Local companion | Explicit selected-folder read-only scanning, pairing, diagnostics, signed challenge-bound approved single-file local apply | Physical Windows 10 build 18362.1256 acceptance, installer/update, real key configuration and rotation |
| Patch application | Exact one-file apply only; owner approval, fresh session-bound challenge, short-lived signed capability, base-hash validation and filesystem atomic replacement | Multi-file transaction, durable journal, rollback, crash recovery and verifiable apply receipt |
| MAD | Worker heartbeat/aggregate metrics, stateless deterministic alerts, authenticated `mad:read` metrics endpoint with audited access and fail-closed audit behavior | Dashboard, persisted incident lifecycle, acknowledgement/assignment/resolution, alert delivery/integrations, calibrated thresholds |
| MAC | Server-configured exact issuer/subject RBAC foundation, fixed permission matrix, access endpoint and fail-closed permission guard | Operator provisioning, enforcement across privileged modules, full console, KMS/vault, provider adapters, dual-control approvals, access review, rotation and rollback |
| Ecosystem docs | Product, architecture, NEXUS, execution, MAC/MAD, identity, workspace, security and release-gate documentation | Keep status synchronized with implementation and remove superseded claims as reviewed |

## Local apply safety contract

The companion accepts exactly one file operation per request. The API refuses
multi-file capability issuance; the companion request schema also limits the
apply list to one file. Do not bypass either guard.

The apply flow requires project-owner approval, explicit local confirmation,
a fresh one-use challenge bound to the paired session/workspace, a short-lived
owner-signed capability, and a live base-hash match. The companion independently
verifies the signature against pinned public keys. It reports whether metadata
durability was confirmed; a false durability result must not be presented as a
durable success.

There is no multi-file transaction journal, automatic rollback or crash
recovery. Back up important work before applying. The browser editor remains
read-only; no shell or arbitrary process execution is exposed by the companion.

## Operational blockers outside repository-only implementation

1. **ODID:** an authorized administrator must register the real browser client,
   callback URI, scopes/audience and API issuer/JWKS/CORS configuration, then
   run staging identity and tenant-isolation tests.
2. **Windows:** install and test the companion on the actual Windows 10
   version 1903 / build 18362.1256 machine. GitHub-hosted Windows CI is not
   equivalent to this device acceptance.
3. **Execution:** provision a dedicated Linux worker with a hardened isolation
   boundary (gVisor, Kata, microVM or equivalent), immutable image digests,
   restricted egress, no host credentials, quotas and monitoring; run recovery
   and cancellation drills.
4. **Secrets:** a database credential previously exposed in project setup
   material must be rotated at its source, all dependent services updated and
   the old credential revoked. Never paste secrets into chat or commit them.
5. **Production:** configure real MongoDB, model/provider, identity, secret
   manager and hosting resources; verify backups/restores, staging acceptance,
   monitored rollout and rollback. No production deployment is claimed.
6. **MAD/MAC:** implement persisted incident workflows and enforce MAC
   permissions at every privileged operation before treating these planes as
   operational consoles.

## Next implementation sequence

1. Design and test a journaled multi-file transaction protocol: preflight every
   target and base hash, stage all replacements, persist a transaction journal,
   commit with a recoverable protocol, and support idempotent restart recovery
   and explicit rollback. Preserve single-file-only behavior until this is
   proven on Windows and POSIX filesystems.
2. Add durable apply receipts and an append-only local apply audit trail without
   recording file contents or secrets.
3. Implement persisted MAD incident state and audited acknowledge/assign/
   resolve/reopen transitions, followed by notification delivery.
4. Integrate MAC permission checks into actual privileged routes/services,
   retaining fail-closed behavior.
5. Complete target-machine, ODID staging and production release acceptance.

A repository merge is not a deployment. External credentials, local device
access, infrastructure provisioning and production approvals remain explicit
operator-controlled steps.
