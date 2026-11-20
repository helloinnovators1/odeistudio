# Global Technical Research and Architecture Decisions

**Research snapshot:** 20 November 2026  
**Purpose:** Record primary-source guidance that materially affects implementation. Recheck provider behavior, pricing, SDK versions and regional availability before production integration.

## 1. OpenAI agent platform

### Findings
- OpenAI recommends the Responses API for new integrations and supports typed output items, built-in tools and custom function calling.
- The API supports tool calls that must be executed by application code; tool outputs are returned using their call identifiers.
- The Agents SDK provides agent, runner, tool, guardrail and handoff abstractions; local shell, apply-patch and computer-use harnesses still run in the application's execution environment.
- The Assistants API sunset on 26 August 2026; do not start new implementation on Assistants API.

### Decisions
- NEXUS model requests use the official OpenAI Python SDK and Responses API.
- Model selection is configuration, not a hard-coded assumption. `OPENAI_API_KEY` and `ODEI_MODEL` are server-side settings.
- Initial planning calls have no tools enabled. Model-generated plans are proposals, not authorization.
- Tool execution remains an ODEI-controlled service with permission checks, validation, audit, timeouts and sandboxing.
- Evaluate the Agents SDK when multi-agent orchestration is implemented; do not add it solely to create an agent label or screen.

### Primary sources
- https://developers.openai.com/api/docs/guides/migrate-to-responses
- https://developers.openai.com/api/docs/guides/tools
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://openai.github.io/openai-agents-python/agents/
- https://openai.github.io/openai-agents-python/tools/

## 2. GitHub source integration

### Findings
- GitHub's Git Trees API can inspect repository trees and create tree objects; new trees should be based on the existing tree when preserving unrelated paths.
- GitHub App installation tokens support scoped repository access and are preferable to broad personal access tokens for a multi-tenant integration.

### Decisions
- Use GitHub App authorization for customer repositories.
- Verify webhook signatures, installation/repository scope and event replay behavior.
- Keep repository ingestion read-only by default. Branch creation, commits, pushes and PRs are explicit user-approved actions.
- Use content hashes and commit SHAs for provenance and concurrency checks.

### Primary sources
- https://docs.github.com/en/rest/git/trees
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/

## 3. Project indexing and ignore behavior

### Findings
- The Python `pathspec` library provides `GitIgnoreSpec` to emulate Git's ignore rules, including important edge cases that differ from simplified glob matching.
- Ignore files can be nested; their patterns are interpreted relative to the directory containing each ignore file.

### Decisions
- NEXUS indexing uses GitIgnoreSpec rather than a custom glob approximation.
- Always exclude known secret paths and dependency/build directories even if ignore rules attempt to include them.
- Apply file-count, total-byte, per-file-byte and result-count budgets.
- Do not follow symbolic links outside the selected workspace; a future cross-platform hardened file handle layer is required before exposing file operations to untrusted network callers.

### Primary sources
- https://python-path-specification.readthedocs.io/en/latest/api.html
- https://python-path-specification.readthedocs.io/en/latest/readme.html

## 4. MongoDB Atlas and secrets

### Findings
- Atlas connection strings are provided for the target cluster/network; application deployments must be allowed by Atlas network access rules.
- MongoDB guidance recommends using environment variables or a secret manager for credentials and separate credentials/configuration for development, staging and production.

### Decisions
- Never commit Atlas connection strings or passwords.
- Store secret values in a managed secret manager/KMS-backed vault; MongoDB stores references and metadata only.
- Use separate least-privilege database users and network rules per environment.
- Rotate any credential that has appeared in chat, source control or shared project documentation.

### Primary sources
- https://www.mongodb.com/docs/atlas/reference/faq/connection-changes/
- https://www.mongodb.com/resources/products/fundamentals/atlas-connection-strings

## 5. MongoDB asynchronous Python driver

### Findings
- MongoDB's supported PyMongo Async API uses `AsyncMongoClient`; network operations are awaited and the client must not be shared across event loops.

### Decisions
- Use PyMongo Async rather than introducing a new Motor dependency for new async services.
- Construct the client lazily from a private Atlas URI; verify connectivity through a bounded ping/health check when lifecycle management is implemented.
- Do not claim database readiness until an actual ping succeeds.

### Primary sources
- https://pymongo.readthedocs.io/en/stable/api/pymongo/asynchronous/index.html
- https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/

## 6. FastAPI authorization

### Findings
- FastAPI supports OAuth2 scopes and dependency-based authorization checks; scope requirements can be enforced centrally per route.

### Decisions
- No project-file or agent execution route is exposed until authenticated identity and tenant/workspace authorization exist.
- Use server-resolved organization membership and least-privilege scopes; never trust tenant IDs supplied only by the browser.
- CORS is not an authorization mechanism.

### Primary source
- https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/

## 7. Research limitations
This document records architectural research, not completed provider integrations, a legal/compliance assessment, production security certification or an exhaustive survey of every provider product tier. Before enabling a provider action, validate its current official API, account permissions, regional availability, rate limits and product plan. Update the relevant adapter capability matrix and tests with evidence.


## JWT and OIDC verification

- IETF RFC 8725 (JWT Best Current Practices): https://www.rfc-editor.org/rfc/rfc8725.html
- Decision: the initial API verifier pins RS256, verifies the signature against a configured issuer JWKS, validates issuer and audience, requires expiry and subject, and never follows token-provided `jku`/`x5u` URLs. Organization membership is resolved from server-side storage rather than trusting client-supplied tenant IDs or role claims.
- Remaining profile decision: confirm the actual ODID access-token type/claim contract before enforcing `typ`, `azp`, scopes or provider-specific role claims. Do not infer those claims from the browser-local auth UI or local role registry documented upstream.
