# Engineering Standards and Contribution Workflow

## Repository structure (target)
```
apps/
  web/                 # React + TypeScript workspace and admin surfaces
  api/                 # Python FastAPI application
services/
  orchestrator/        # durable agent task orchestration
  execution/           # isolated runtime workers
packages/
  contracts/           # shared API/event schemas
  adapters/            # provider adapter interfaces and implementations
  ui/                  # shared design system
infra/                 # deployment and infrastructure definitions
docs/                  # product, architecture and operational docs
tests/                 # cross-service and end-to-end tests
```
This is a proposed target structure, not a claim that these directories currently exist.

## Technology direction
- Python + FastAPI for agent orchestration and backend services.
- TypeScript + React for the web workspace and administration UI.
- Monaco Editor for code editing when appropriate.
- MongoDB for suitable application metadata and durable records, with indexes and tenant isolation.
- A managed secret manager/KMS for secret material.
- Containerized isolated workers for agent execution.
- Provider-neutral model gateway; use supported current provider SDKs and APIs.

Confirm versions and API behavior against current official documentation when implementation begins. Pin dependencies and keep lockfiles committed.

## Coding rules
- Strict types and input validation at service boundaries.
- Small modules with explicit responsibilities and dependency injection.
- No secrets in source, tests, fixtures, screenshots or logs.
- Use structured logs with request and trace IDs.
- Add migrations for schema changes.
- Avoid hidden global mutable state.
- Fail closed on authorization or policy errors.
- Do not swallow exceptions or return fabricated success.

## Change workflow
1. Inspect relevant code and tests before editing.
2. Write acceptance criteria and identify security impact.
3. Implement a vertical slice.
4. Add unit, integration and contract tests.
5. Run formatter, linter, type checks and tests available in the environment.
6. Review diff for secrets, unsafe paths and unintended scope.
7. Update docs and changelog.
8. Report exact commands run and results.

## Pull request checklist
- [ ] Scope and acceptance criteria are clear.
- [ ] Tenant authorization and permissions are enforced.
- [ ] Errors, retries and cancellation are handled.
- [ ] Tests cover success and failure cases.
- [ ] No credentials or sensitive data are committed.
- [ ] Logs and telemetry are redacted.
- [ ] Documentation and operational notes are updated.
- [ ] No unverified claims of provider or test success.
