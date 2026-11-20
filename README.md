# ODEI Studio

An African-built AI-native development operating system (AI-DOS).

## Product direction
- Modular multi-card, multi-tab engineering workspace
- AI orchestration: plan, implement, test, repair and review
- Whole-repository context and semantic search
- Local and isolated cloud agent runtimes
- GitHub, database, model-provider and deployment integrations
- Master Admin Console (MAC) as the central control plane
- Master Admin Dashboard (MAD) for operational and executive visibility
- Enterprise identity, permissions, auditability and usage controls

## MAC authority
The Master Admin Console is the overall management and configuration authority for ODEI Studio. It must manage application environment configuration, secrets references, hosting-provider integrations other than Vercel, domains/DNS, databases, AI providers, GitHub, agent policies, deployment targets, users, tenants, security and platform-wide settings. Vercel is intentionally a separate hosting/deployment integration boundary.

Provider operations must use supported APIs and permission scopes. The MAC must never imply unsupported capabilities or expose secret values after saving them.

## Current status
The repository now contains the product/architecture documentation, a FastAPI foundation, bounded project-file utilities, a Responses API planning service, guarded task lifecycle, transactional MongoDB task/event persistence, MongoDB readiness checks and an OIDC/JWKS verification foundation. The latest verified API CI run passed Ruff and 44 tests. Authentication is not yet connected to a confirmed ODID issuer or protected workspace/task routes. The application is not yet a complete coding agent or production-ready platform; each capability must be built and verified incrementally. UI prototypes are not evidence that backend services are operational.

## Security
A database credential was exposed in project setup material. Assume it is compromised and rotate it immediately in MongoDB Atlas. Never commit secrets. Store secret values in a managed secret store and use server-only environment variables for runtime injection.

## Roadmap
1. Application foundation and modular workspace
2. MAC control plane and MAD operational dashboard
3. Authentication, tenancy and RBAC
4. Secure configuration and secret lifecycle
5. Hosting-provider, domain and infrastructure integrations (excluding Vercel)
6. GitHub integration and repository intelligence
7. Agent orchestration and isolated execution
8. Testing, repair, review and deployment workflows

## Documentation

Start with [`docs/INDEX.md`](docs/INDEX.md) for the complete documentation map and [`docs/ECOSYSTEM.md`](docs/ECOSYSTEM.md) for the full product ecosystem. The audited upstream ecosystem specifications and historical remediation documents are preserved in [`docs/upstream/INDEX.md`](docs/upstream/INDEX.md); a complete 68-file source-document mirror is indexed in [`docs/upstream/MIRROR_INDEX.md`](docs/upstream/MIRROR_INDEX.md). Current migration decisions are in [`docs/UPSTREAM_ECOSYSTEM_ALIGNMENT.md`](docs/UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for implementation status. Documentation describes intended behavior; it does not imply that a feature is already implemented or operational.


## API local development

The initial API service lives in `apps/api`.

```powershell
cd apps/api
python -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
uvicorn odei_api.main:app --reload
```

The health endpoints are `/api/v1/health/live` and `/api/v1/health/ready`. Readiness performs a bounded MongoDB ping and returns HTTP 503 when MongoDB is not configured or unavailable.
