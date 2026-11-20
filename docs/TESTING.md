# Quality Engineering and Testing Strategy

## Test layers
1. **Unit:** pure business logic, validators, state transitions, policy evaluation and adapter normalization.
2. **Integration:** database repositories, secret-manager adapter, queues, model gateway and provider sandboxes.
3. **Contract:** API schemas, event schemas and provider adapter contracts.
4. **Security:** tenant isolation, authorization bypass, path traversal, prompt injection, secret leakage, unsafe command execution and webhook replay.
5. **End-to-end:** project open → agent plan → approval → patch → test → diff/review.
6. **Operational:** worker restart, queue retry, cancellation, timeouts, backup/restore and provider outage behavior.

## Required NEXUS negative tests
- Path traversal and symlink escape attempts are rejected.
- Binary and oversized files are not loaded as ordinary text.
- Concurrent file edits cause safe conflict detection.
- Unapproved commands and network access are blocked.
- Command timeouts terminate child processes.
- Tool output containing prompt injection cannot change policy.
- Tenant A cannot access Tenant B's project, task or artifact.
- Secrets are redacted from model context, logs, exceptions and artifacts.
- Cancellation stops execution and cleans up workspace resources.
- Failed provider calls do not create false-success states.

## CI quality gates
Run formatting, lint, type checks, unit/integration/contract tests, dependency and secret scanning on each change. Run end-to-end and container security checks before release. Store artifacts with access control and retention limits.

## Test client compatibility
- Install `httpx2` for Starlette's `TestClient`; current Starlette releases deprecate the legacy `httpx` backend. Keep `httpx` as the API's async HTTP client dependency where application code imports it. The `httpx2>=2.14,<3` development constraint resolves to a Python 3.10-compatible release on the 3.10 matrix and current compatible releases on newer Python versions.

## Reporting
For every validation report the exact command, environment, exit code, test count and known skips. Distinguish not run, blocked, failed and passed. Do not infer success from a commit or successful build alone.
