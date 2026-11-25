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
