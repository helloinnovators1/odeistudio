# Verified Delivery Snapshot — 2026-11-22

This snapshot records the repository state after PR #72 merged. It is not a production-readiness declaration. Repository code, CI evidence, independent review, merge, external acceptance and production deployment are distinct states.

## Mainline and open work

- Current `main` at snapshot: `7beaf69173e08a22db32309f0198bc469e1548c3`.
- Merged PRs:
  - [#68](https://github.com/helloinnovators1/odeistudio/pull/68): NEXUS browser shell and responsive regression coverage.
  - [#69](https://github.com/helloinnovators1/odeistudio/pull/69): NEXUS implementation documentation synchronization.
  - [#70](https://github.com/helloinnovators1/odeistudio/pull/70): delivery snapshot correction.
  - [#71](https://github.com/helloinnovators1/odeistudio/pull/71): stale project-discovery response guard and unit tests.
  - [#72](https://github.com/helloinnovators1/odeistudio/pull/72): npm lockfile, pinned npm toolchain and deterministic `npm ci` CI installs.
- [PR #66](https://github.com/helloinnovators1/odeistudio/pull/66) remains open, unapproved and based on an older mainline commit. It needs conflict/rebase work and independent security review. A technical review comment identified unresolved audit transaction fallback, secret-resolution timeout, migration readiness/backfill and deployment authority/idempotency concerns.
- Open issues: [#63](https://github.com/helloinnovators1/odeistudio/issues/63) (branch protection and independent review policy) and [#64](https://github.com/helloinnovators1/odeistudio/issues/64) (authenticated E2E, accessibility and visual regression). [Issue #62](https://github.com/helloinnovators1/odeistudio/issues/62) is closed after PR #72 merged.

## Verified capabilities in main

| Area | Current implementation | Remaining acceptance |
|---|---|---|
| NEXUS identity/chat | ODID PKCE browser foundation, authenticated organization/project discovery, consent-gated chat, SSE streaming/cancellation and durable owner/tenant-scoped conversations | Real ODID issuer/client/callback/scopes/audience, API issuer/JWKS/CORS, staging identity and tenant-isolation tests |
| Organization/project selection | Authenticated discovery plus PR #71 request-generation guard; stale project-list success/error/loading completions cannot overwrite state after organization changes, sign-out or session expiry | Full authenticated browser tests for org/project switching, race and failure states |
| Inspection/proposals | Bounded tool loop over explicitly attached excerpts, secret redaction, persisted patch proposals, owner approval/rejection and signed one-use capability for one-file local apply | Safe multi-file context management, mutation/audit consistency and complete authenticated proposal/apply/recovery tests |
| Task planning | Durable tenant/project-scoped tasks, approval, cancellation and lifecycle events | End-to-end acceptance under real ODID/MongoDB configuration |
| Execution | Approved task/profile flow, separate upload and execution consent, bounded filtered workspace snapshot, durable runs/events/leases, worker/sandbox integration, cancellation, artifacts and project history | Dedicated hardened worker infrastructure, immutable image/profile provenance, storage/secrets, crash/retry/lease/cancel/cleanup drills and staging acceptance |
| Local companion | Explicit workspace selection, bounded read-only scan, pairing and signed fresh-challenge-bound one-file apply | Multi-file transaction journal, rollback, crash recovery, durable apply receipt/audit, signed installer/update and physical Windows 10 build 18362.1256 acceptance |
| MAD | Aggregate worker/execution telemetry and persisted incident lifecycle UI/API | Real infrastructure telemetry, alert delivery, calibrated thresholds and real operator provisioning |
| MAC | Base RBAC/permission foundation in main; environment governance/revision/worker work remains in unmerged PR #66 | Resolve PR #66 findings, rebase, independent security review, real provider/secret-manager adapters, migration, enforcement audit, worker deployment and staging acceptance |
| Browser QA | Playwright/Chromium CI; panel open/shortcut, accessible NEXUS landmark, safe unauthenticated state, overflow at 320/360/390/768/1024/1440px, plus request-generation unit tests | ODID/org/project/conversation/stream/cancel/task/execution/patch/companion/MAC/MAD authenticated journeys; axe, keyboard/focus/dialog and deterministic visual baselines |
| Web dependency reproducibility | PR #72 merged: lockfile v3, npm 10.9.4 pin, Node/npm engine range, `npm ci` in API CI and Security Scanning | Keep lockfile current through Dependabot and require lockfile-based installs in any new web workflows |

## CI evidence

- PR #68 exact head `7c5fed37a585bfe6a610a29eb56fe66b41765c57`, PR #71 exact head `0ad87fec7eac85bb631ae38020fdeb964c469117`, and PR #72 exact head `8bf64cbf19b50fae35bd3c5615428112179e6fce` passed their reported final-head checks before merge.
- Checks included Ubuntu/Windows Python 3.10 and 3.12, MongoDB replica-set integration, web unit tests/build/Playwright, Python and web dependency audits, secret scanning and CodeQL.
- PR #72's temporary GitHub-hosted bootstrap run generated the lockfile using npm 10.9.4, then passed clean `npm ci`, web unit tests, production build and `npm audit --audit-level=high`. The temporary bootstrap workflow was removed before merge.
- PR #71's tests validate request-generation ordering and invalidation. They are not a substitute for browser-driven authenticated organization-switching acceptance.

These checks verify the tested repository commits on GitHub-hosted runners. They do not prove real identity-provider integration, deployment, physical Windows device compatibility, hostile-code isolation in production or complete authenticated user journeys.

## Open engineering blockers

1. **MAC/MAD governance:** PR #66 is stale and has no independent approval. Resolve the four review findings, rebase/update against current main, add targeted tests and obtain independent security review before merge.
2. **Repository governance:** `main` remains unprotected. The connected repository integration cannot mutate branch protection/rulesets; its branch-protection read returned 403. A repository administrator must configure required independent reviews and CI/security status checks, stale-approval dismissal, conversation resolution, force-push restrictions and direct-push controls.
3. **Authenticated browser acceptance:** Complete issue #64's mocked identity/API/companion journeys, accessibility automation and visual baselines.
4. **Audit consistency:** task lifecycle and audit writes have transaction coupling. Conversation and patch-proposal mutation/audit paths need review for ambiguous commit outcomes, idempotency and reconciliation.
5. **Local multi-file safety:** keep multi-file apply disabled until a durable transaction journal, full preflight/base-hash validation, recoverable commit protocol, idempotent restart recovery and rollback have passed Windows and POSIX tests.
6. **Execution productionization:** ordinary OCI flags alone are insufficient for hostile multi-tenant execution. Use a hardened isolation boundary (gVisor, Kata, microVM or equivalent), immutable images, no host credentials, restricted egress, quotas, monitoring and operational recovery drills.
7. **Windows acceptance:** GitHub-hosted Windows CI is not equivalent to installing and exercising the companion on the actual Windows 10 build 18362.1256 target.
8. **Production readiness:** verify MongoDB replica-set transactions, backups/restores, encryption/retention/deletion, model/provider credentials, secret-manager integration, ODID configuration, staging, monitored rollout and rollback. Verify source rotation, dependent-service updates and revocation of any previously exposed setup credential before deployment.

## Release rule

Do not equate a green check, merged PR, documentation statement or local test with production acceptance. Record exact commit, test evidence, independent review, deployment target, migration status, external identity/provider acceptance, monitoring and rollback evidence separately. No production deployment is claimed.
