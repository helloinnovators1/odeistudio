# Verified Delivery Snapshot — 2026-11-22

This snapshot supersedes earlier content in this file. It records repository evidence after PR #68 was merged. It is not a production-readiness declaration.

## Mainline and open work

- Current `main`: `b5e76e6a5f43f617216b3383f6e8b4b3f35d7316`.
- PR [#68](https://github.com/helloinnovators1/odeistudio/pull/68), expanded NEXUS browser shell regression coverage, is merged.
- PR [#66](https://github.com/helloinnovators1/odeistudio/pull/66), MAC/MAD transactional governance and NEXUS project-load race protection, remains open and has no independent review submissions.
- Issues [#62](https://github.com/helloinnovators1/odeistudio/issues/62) (npm lockfile/`npm ci`), [#63](https://github.com/helloinnovators1/odeistudio/issues/63) (branch protection/reviews) and [#64](https://github.com/helloinnovators1/odeistudio/issues/64) (authenticated E2E/accessibility/visual regression) remain open.

## Verified capabilities in main

| Area | Current implementation | Remaining acceptance |
|---|---|---|
| NEXUS chat and identity | ODID PKCE browser foundation, authenticated org/project discovery, consent-gated chat, SSE streaming/cancellation and durable owner-scoped conversations | Real ODID issuer/client/callback/scopes/audience, API issuer/JWKS/CORS, staging identity and tenant-isolation tests |
| Inspection and proposals | Bounded tool loop over explicitly attached excerpts, secret redaction, persisted patch proposals, owner approval/rejection | Safe multi-file context management, mutation/audit consistency and complete authenticated browser tests |
| Task planning | Durable tenant/project-scoped tasks, approval, cancellation and lifecycle events | End-to-end acceptance under real ODID/MongoDB configuration |
| Execution | Approved task/profile flow, separate upload and execution consent, bounded filtered workspace snapshot, durable runs/events/leases, worker/sandbox integration, cancellation, artifacts and project history | Dedicated hardened worker infrastructure, immutable image/profile provenance, storage/secrets, crash/retry/lease/cancel/cleanup drills and staging acceptance |
| Local companion | Explicit workspace selection, bounded read-only scan, pairing and signed fresh-challenge-bound one-file apply | Multi-file transaction journal, rollback, crash recovery, durable apply receipt/audit, signed installer/update and physical Windows 10 build 18362.1256 acceptance |
| MAD | Aggregate worker/execution telemetry and persisted incident lifecycle UI/API | Real infrastructure telemetry, alert delivery, calibrated thresholds and real operator provisioning |
| MAC | Base RBAC/permission foundation in main; environment governance/revision/worker work is in unmerged PR #66 | Independent review, real provider/secret-manager adapters, migration, enforcement audit, worker deployment and staging acceptance |
| Browser QA | Playwright/Chromium CI; panel open/shortcut, narrow shell overflow, accessible NEXUS landmark, safe unauthenticated state, panel-open overflow at 320/360/390/768/1024/1440px | ODID/org/project/conversation/stream/cancel/task/execution/patch/companion/MAC/MAD authenticated journeys; axe, keyboard/focus/dialog and deterministic visual baselines |

## CI evidence for PR #68

PR #68 exact head `7c5fed37a585bfe6a610a29eb56fe66b41765c57` passed all reported GitHub Actions checks before merge, including CodeQL, secret scanning, Python and web dependency audits, Ubuntu/Windows Python 3.10 and 3.12, web build/tests/Playwright and MongoDB integration. Merge commit: `b5e76e6a5f43f617216b3383f6e8b4b3f35d7316`.

These checks verify the tested repository commit on GitHub-hosted runners. They do not prove real identity-provider integration, deployment, physical Windows device compatibility, hostile-code isolation in production or complete authenticated user journeys.

## Open engineering blockers

1. **Deterministic web dependencies:** `apps/web/package.json` exists but no tracked `apps/web/package-lock.json` was found. `.github/workflows/api-ci.yml` and `.github/workflows/security.yml` still use `npm install`. Generate the lock with Node 22/npm 10 in a trusted network-enabled CI environment, review the full graph and integrity data, then use `npm ci` in both workflows. Do not hand-author a partial or guessed lockfile.
2. **Repository governance:** `main` is unprotected. Configure required independent reviews and CI/security status checks, dismiss stale approvals, restrict force pushes and block direct unreviewed changes in GitHub repository settings. The connected repository integration used for this audit exposes reads and content/PR operations but not branch-protection mutation.
3. **Authenticated browser acceptance:** PR #68 is shell coverage only. Complete issue #64's mocked identity/API/companion journeys, accessibility automation and visual baselines.
4. **Audit consistency:** task lifecycle and audit writes have transaction coupling. Conversation and patch-proposal mutation/audit paths need review for ambiguous commit outcomes, idempotency and reconciliation.
5. **Local multi-file safety:** keep multi-file apply disabled until a durable transaction journal, full preflight/base-hash validation, recoverable commit protocol, idempotent restart recovery and rollback have passed Windows and POSIX tests.
6. **Execution productionization:** ordinary OCI flags alone are insufficient for hostile multi-tenant execution. Use a hardened isolation boundary (gVisor, Kata, microVM or equivalent), immutable images, no host credentials, restricted egress, quotas, monitoring and operational recovery drills.
7. **Windows acceptance:** GitHub-hosted Windows CI is not equivalent to installing and exercising the companion on the actual Windows 10 build 18362.1256 target.
8. **Production readiness:** verify MongoDB replica-set transactions, backups/restores, encryption/retention/deletion, model/provider credentials, secret-manager integration, ODID configuration, staging, monitored rollout and rollback. A database credential was previously identified as exposed in setup material; verify source rotation, dependent-service updates and revocation of the old credential before any deployment.

## Release rule

Do not equate a green check, merged PR, documentation statement or local test with production acceptance. Record exact commit, test evidence, independent review, deployment target, migration status, external identity/provider acceptance, monitoring and rollback evidence separately. No production deployment is claimed in this snapshot.
