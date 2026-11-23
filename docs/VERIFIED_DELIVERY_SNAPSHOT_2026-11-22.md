# Verified Delivery Snapshot — 2026-11-22

This snapshot records the repository state at the current-main MAC/MAD integration review. It is not a production-readiness declaration. Repository code, CI evidence, independent review, merge, external acceptance and production deployment are distinct states.

## Mainline and open work

- Main at snapshot: `f25e6fc71d3eff77e8c45c6aa4eed0b7520614c5`.
- Merged PRs:
  - [#68](https://github.com/helloinnovators1/odeistudio/pull/68): NEXUS browser shell and responsive regression coverage.
  - [#69](https://github.com/helloinnovators1/odeistudio/pull/69): NEXUS implementation documentation synchronization.
  - [#70](https://github.com/helloinnovators1/odeistudio/pull/70): delivery snapshot correction.
  - [#71](https://github.com/helloinnovators1/odeistudio/pull/71): stale project-discovery response guard and unit tests.
  - [#72](https://github.com/helloinnovators1/odeistudio/pull/72): npm lockfile, pinned npm toolchain and deterministic `npm ci` CI installs.
  - [#73](https://github.com/helloinnovators1/odeistudio/pull/73): documentation synchronization after PR #72.
- [PR #74](https://github.com/helloinnovators1/odeistudio/pull/74) is open and ready for independent review. It replaces the conflicted PR #66 branch and is based on current main. Latest merge-synchronized branch tip: see PR #74 Checks for the exact SHA. The immediately preceding code-equivalent head `a80c8005b6ee9bdae7b4304368a67be0238c1e0a` passed both workflows; the current branch tip is rerunning them; see the PR Checks tab for its exact SHA.
- [PR #66](https://github.com/helloinnovators1/odeistudio/pull/66) is closed as superseded by #74, not merged.
- Open issues: [#63](https://github.com/helloinnovators1/odeistudio/issues/63) (branch protection and independent review policy) and [#64](https://github.com/helloinnovators1/odeistudio/issues/64) (authenticated E2E, accessibility and visual regression). [Issue #62](https://github.com/helloinnovators1/odeistudio/issues/62) is closed after PR #72 merged.

## Verified capabilities in main

| Area | Current implementation | Remaining acceptance |
|---|---|---|
| NEXUS identity/chat | ODID PKCE browser foundation, authenticated organization/project discovery, consent-gated chat, SSE streaming/cancellation and durable owner/tenant-scoped conversations | Real ODID issuer/client/callback/scopes/audience, API issuer/JWKS/CORS, staging identity and tenant-isolation tests |
| Organization/project selection | PR #71 request-generation guard prevents stale project-list success/error/loading completions crossing organization changes, sign-out or session expiry | Full authenticated browser tests for org/project switching, race and failure states |
| Inspection/proposals | Bounded tool loop over explicitly attached excerpts, secret redaction, persisted patch proposals, owner approval/rejection and signed one-use capability for one-file local apply | Safe multi-file context management, conversation/proposal mutation-audit consistency and authenticated proposal/apply/recovery tests |
| Task planning | Durable tenant/project-scoped tasks, approval, cancellation and lifecycle events | End-to-end acceptance under real ODID/MongoDB configuration |
| Execution | Approved task/profile flow, separate upload and execution consent, bounded filtered workspace snapshot, durable runs/events/leases, worker/sandbox integration, cancellation, artifacts and project history | Dedicated hardened worker infrastructure, immutable image/profile provenance, storage/secrets, crash/retry/lease/cancel/cleanup drills and staging acceptance |
| Local companion | Explicit workspace selection, bounded read-only scan, pairing and signed fresh-challenge-bound one-file apply | Multi-file transaction journal, rollback, crash recovery, durable apply receipt/audit, signed installer/update and physical Windows 10 build 18362.1256 acceptance |
| MAD | Aggregate worker/execution telemetry and persisted incident lifecycle UI/API | Real infrastructure telemetry, alert delivery, calibrated thresholds and real operator provisioning |
| MAC | Main contains the base RBAC/permission foundation. PR #74 proposes the environment revision store, NEXUS MAC panel, deployment worker and transactional audit governance. | PR #74 independent review, concrete provider/secret-manager adapters, staging migration/rollback, hardened worker deployment and real operator acceptance |
| Browser QA | Playwright/Chromium CI; panel open/shortcut, accessible NEXUS landmark, safe unauthenticated state, overflow at 320/360/390/768/1024/1440px and project request-generation unit tests | ODID/org/project/conversation/stream/cancel/task/execution/patch/companion/MAC/MAD authenticated journeys; axe, keyboard/focus/dialog and deterministic visual baselines |
| Web dependency reproducibility | PR #72: lockfile v3, npm 10.9.4 pin, Node/npm engine range, `npm ci` in API CI and Security Scanning | Keep lockfile current through Dependabot and require lockfile-based installs in new workflows |

## PR #74 candidate implementation and CI evidence

PR #74 carries forward the MAC/MAD implementation on current main and adds:

- MAC state mutation fails closed when MongoDB transaction support is unavailable; state and success audit must commit in the same session.
- A hard deadline bounds the complete secret-resolution phase; timed-out resolver work is cancelled.
- Deployment request and approval are separate permissions.
- Provider and secret-resolver factory references must match exact deployment-owned JSON allowlists; malformed, duplicate and unlisted references fail closed before work is claimed.
- Provider adapters receive stable idempotency keys; a crash-window regression test verifies the same key is reused after provider success but before receipt persistence.
- Revision-store startup fails closed for incomplete history; migration tests cover dry-run, idempotent retry, gaps, divergent records and BSON mismatch.
- The NEXUS MAC panel is restored without reverting the newer project-discovery race guard. MAC UI requests are invalidated on sign-out and session expiry.

At the preceding code-equivalent head `a80c8005b6ee9bdae7b4304368a67be0238c1e0a`:

- Security Scanning passed all four jobs: CodeQL, Python dependency audit, web dependency audit and secret scanning.
- API CI had passed Ubuntu Python 3.10/3.12, Windows Python 3.12, MongoDB replica-set transaction integration and web unit tests/build/Playwright.
- API CI passed all six jobs, including the Windows Python 3.10/3.12 matrix. The latest merge-synchronized branch tip is rerunning API CI and Security Scanning; see the PR Checks tab for the exact SHA.
- GitHub reports PR #74 mergeable against current main. It is not merged and has no independent security approval.

## Open engineering blockers

1. **Independent review:** PR #74 requires independent security review of transaction/audit coupling, secret-resolution cancellation, factory allowlists, migration cutover and worker recovery.
2. **Real adapters:** no concrete production cloud-provider or secret-manager adapter has been shipped or accepted. Verify upstream provider idempotency across provider success / receipt-write-failure.
3. **Migration:** run dry-run and transactional legacy backfill in staging, verify every revision history, and prove rollback before rollout.
4. **Worker isolation:** use a hardened hostile-code isolation boundary (gVisor, Kata, microVM or equivalent), immutable images, no host credentials, restricted egress, quotas, monitoring and recovery drills.
5. **Authenticated browser acceptance:** complete issue #64's ODID/org/project/conversation/stream/cancel/task/execution/patch/companion/MAC/MAD journeys, accessibility automation and visual baselines.
6. **Audit consistency:** conversation and patch-proposal mutation/audit paths need transaction coupling or explicit idempotent reconciliation.
7. **Windows acceptance:** GitHub-hosted Windows CI is not equivalent to installing and exercising the companion on the actual Windows 10 build 18362.1256 target.
8. **Repository governance:** `main` remains unprotected. The connected repository integration cannot administer branch protection/rulesets; a repository administrator must configure required independent reviews, CI/security checks, stale-approval dismissal, conversation resolution and force-push restrictions.
9. **Production readiness:** verify real ODID, production MongoDB replica-set transactions, model/provider credentials, secret manager, backup/restore, retention/deletion, staging, monitoring, deployment and rollback. No production migration or deployment was performed.

## Release rule

Do not equate a green check, open/ready PR, documentation statement or local test with production acceptance. Record exact commit, test evidence, independent review, deployment target, migration status, external identity/provider acceptance, monitoring and rollback evidence separately. No production deployment is claimed.
