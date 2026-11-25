# NEXUS trusted GitHub repository binding

A project repository is not trusted because a browser submits a URL or filesystem path. The project owner binds it through the configured GitHub App integration.

## Configure the GitHub App

Set these server-only API environment variables:

- `GITHUB_APP_ID`: numeric GitHub App ID.
- `GITHUB_APP_PRIVATE_KEY_B64`: base64-encoded PEM private key held in the deployment's managed secret store.

Install the App on the intended GitHub account or organization and grant repository **Contents: read and write** and **Pull requests: read and write** permissions. The private key is never returned by the API, logged, or written to MongoDB. Installation access tokens are short-lived and used only in memory for provider verification.

## Bind a project

An authenticated project owner calls:

`PUT /api/v1/organizations/{organization_id}/projects/{project_id}/repository-binding`

with `installation_id`, `owner`, and `repository`. The server signs a short-lived App JWT, verifies that the installation belongs to the configured App, exchanges it for an installation token, and queries GitHub for the repository through that installation. It requires contents write permission and persists the provider's immutable repository ID/node ID, canonical owner/name, default branch and its exact commit SHA, installation ID and binding version.

Replacing a binding requires the current `expected_version`. Removing one also requires the current version. Only the project owner can change the binding; authorized project members can read it. All mutations and reads are audited.

## Security and current boundary

- No client-supplied remote URL, local path, commit SHA or token is trusted.
- No installation token or private key is persisted in MongoDB.
- Repository identity is pinned to GitHub's immutable repository ID and node ID, not only a mutable name.
- A verified binding is necessary but not sufficient for merge-back.
- Production merge-back remains disabled until the isolated worker records commit/tree provenance against this binding and a separate, one-use human approval is bound to the exact repository binding version, base commit and proposed commit/tree.
- Provider configuration, real installation permissions and staging verification remain deployment acceptance gates.


## Worker commit provenance and review PRs

When an execution is created for a bound project, the API re-verifies the GitHub App installation and pins the run to the exact default-branch commit SHA and repository binding version. A successful worker rechecks that binding and base commit before publishing.

The isolated worker builds a Git commit from the post-execution workspace snapshot using GitHub's Git Data API. It rejects symlinks, Git metadata, unsafe/credential paths, known credential patterns, unsupported repository tree entries, truncated trees, more than 100 MiB of workspace content, more than 100 changed files, or more than 5 MiB of changed content. Missing snapshot paths are preserved from the base tree (deletions are not inferred). The commit must have exactly the pinned base as its parent. The worker creates only a unique odei/nexus/{run_id} branch and a review pull request; it never merges.

The API stores the repository ID/node ID, binding version, base SHA, commit SHA, tree SHA, branch, pull request number/URL and attestation timestamp under the active worker lease. The run history exposes this metadata for review. If the branch head changes, the repository binding changes, the default branch moves before publication, or the worker lease expires, provenance recording fails closed.

A pull request is a review artifact, not merge authorization. Merge-back is enabled only through the separate durable, one-use project-owner approval flow described below.


## Human-approved merge-back

A worker pull request is never merged automatically. Merge-back requires a separate project-owner action against a completed execution whose task is still approved.

1. The project owner reviews the GitHub pull request and submits the explicit confirmation string I_REVIEWED_THE_PULL_REQUEST_AND_APPROVE_MERGE to create a durable approval.
2. The approval is scoped to the organization, project, task, run, immutable repository ID/node ID, binding version, default branch, base SHA, worker commit/tree SHA, branch and pull request number/URL.
3. The approval expires after ten minutes, is bound to the same authenticated project owner who must consume it, and can be used once. A unique database index permits only one approval record per execution run. Expired, consumed or failed approvals cannot be replayed.
4. Immediately before merge, the API rechecks the binding and GitHub verifies the pull request is still open and not a draft, the head and base repositories are the trusted repository, the head SHA/branch and base SHA/ref still match the approval, and the worker commit still has exactly the approved base as its only parent and the approved tree SHA.
5. Only then does the GitHub App call the pull-request merge endpoint with the approved head SHA and squash strategy. GitHub branch protection and required reviews remain authoritative. The API records the merge commit SHA in the durable approval record and audit trail.

A stale binding, changed head/base, changed tree/ancestry, expired approval, wrong actor, branch-protection rejection or provider failure stops the operation. Once consumed, an approval is terminal even on failure; a new execution and review PR are required. If GitHub reports a successful merge but the durable result cannot be finalized, the API returns a reconciliation-required response and explicitly forbids replaying that approval.

The merge endpoints do not accept client-supplied repository coordinates, branch names, commit SHAs, base SHAs or merge methods. They use only the stored worker provenance and the server-side verified repository binding.
