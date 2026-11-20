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


## Filesystem path and symlink safety

- Python `os` documentation: https://docs.python.org/3/library/os.html (directory descriptors, `dir_fd`, no-follow behavior, and platform support).
- Decision: on supported POSIX systems, project reads traverse each path component relative to an opened workspace directory descriptor and use no-follow flags; the final handle must be a regular file and reads are byte-bounded. Directory/file listing rejects symlinks and detectable reparse points.
- Python documents that `dir_fd` support is platform-dependent and currently unavailable on Windows. The Windows implementation therefore uses a separate identity/containment fallback and is explicitly not considered race-proof. A native Windows handle-relative implementation and Windows CI coverage are required before enabling remote workspace access.


## Chrome Local Network Access for the local companion

**Decision:** Use Chrome's current Local Network Access (LNA) permission model for requests from the ODEI Studio web app to the loopback companion. Do not rely on the deprecated Private Network Access preflight mechanism or add `Access-Control-Allow-Private-Network` as a security requirement.

- Serve the ODEI Studio web app from a secure HTTPS origin.
- For a public web origin calling `http://127.0.0.1:<port>`, query the granular `loopback-network` permission where supported; if the state is `prompt`, explain the reason and initiate the first request only from an explicit user gesture.
- Use `Request`/`fetch` with `targetAddressSpace: "loopback"` so Chrome can apply the correct address-space and mixed-content checks.
- Handle permission denial and connection errors with clear browser-site-settings guidance. Do not attempt to bypass the prompt.
- Continue server-side exact Origin/Host validation and standard CORS; LNA is an additional browser control, not a replacement for server authorization.

Official references: [Chrome Local Network Access guidance](https://developer.chrome.com/docs/modern-web-guidance/guides/security/local-network-access), [Chrome LNA launch and security rationale](https://developer.chrome.com/blog/local-network-access), [WICG Local Network Access specification](https://wicg.github.io/local-network-access/). Chrome 142 introduced the LNA permission prompt; Chrome 145 split granular `local-network` and `loopback-network` permissions. The older PNA preflight approach is superseded.


## Identity access-token profile and upstream ODID maturity

**Decision:** ODEI Studio's API expects a strict RFC 9068-style JWT access-token profile and must not accept browser-local role simulations or untyped JWTs as production identity.

- RFC 9068 requires an explicit access-token type (`at+jwt` or `application/at+jwt`) and required claims including `iss`, `exp`, `aud`, `sub`, `client_id`, `iat` and `jti`. The target verifier now enforces the profile, RS256, HTTPS issuer/JWKS, bounded JWKS size/key count, compatible JWK use/key_ops and server-side membership lookup.
- RFC 8725 requires issuer/subject and audience validation and emphasizes preventing token substitution. The explicit type check prevents an OIDC ID token from being accepted as an API access token.
- The imported upstream ODID overview describes a historical OPMS identity seed, heuristic KYC and an MFA flag that was not enforced. The imported production roles document explicitly warns that localStorage roles, demo invite codes and client-side admin redirects are a browser-local simulation without protected server-side 401/403 enforcement. These are not trusted production authorization inputs.
- No production ODID issuer, audience, JWKS endpoint, membership API or role contract is confirmed in this target repository. Do not enable workspace/task routes until the ODID contract and server-side membership/permission lifecycle are verified.

References: https://www.rfc-editor.org/rfc/rfc9068.html ; https://www.rfc-editor.org/rfc/rfc8725.html ; https://www.rfc-editor.org/rfc/rfc8414.html ; docs/upstream/ODEI_IDENTITY_HOLISTIC_SOURCE.md ; docs/upstream/PRODUCTION_ROLES_SOURCE.md.
