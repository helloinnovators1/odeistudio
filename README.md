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
The repository contains the complete ecosystem documentation mirror, a FastAPI/NEXUS backend foundation, secure read-only local companion prototype, and an initial React/TypeScript browser workspace client for pairing, multi-root browsing and file preview. Python tests run on Ubuntu/Windows with Python 3.10/3.12; the web client has unit tests and a production build; Gitleaks, pip-audit, npm audit and CodeQL are active in CI; the latest four-way Python matrix and web build/tests passed, and the security scan completed successfully. This remains an early read-only vertical slice, not a complete coding agent or production-ready platform. ODID issuer/tenant authorization, editing, sandboxed execution, MAC/MAD and provider integrations remain outstanding.

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

The health endpoints are `/api/v1/health/live` and `/api/v1/health/ready`. Readiness performs a bounded MongoDB ping and `hello` topology check. It returns HTTP 503 when MongoDB is not configured/unavailable or when the server is standalone and cannot support the multi-document transactions required by NEXUS task/audit persistence. A replica set or sharded cluster is required.

## Web workspace preview

The initial read-only browser client lives in `apps/web`:

```powershell
cd apps/web
npm install
npm run dev
```

It binds to `127.0.0.1:3002`. Configure the local companion's `ODEI_COMPANION_ALLOWED_ORIGINS` to the exact origin `http://127.0.0.1:3002` (or the exact `localhost` origin if you open it that way). The browser pairing request must be initiated by the Connect button. The client keeps the bearer token in memory only and supports read-only file preview; it is not yet the full IDE.
