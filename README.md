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
The repository was empty at initial inspection. Product implementation and connected services must be built and verified incrementally. UI prototypes are not evidence that backend services are operational.

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

Start with [`docs/INDEX.md`](docs/INDEX.md) for the complete documentation map and [`docs/ECOSYSTEM.md`](docs/ECOSYSTEM.md) for the full product ecosystem. The docs cover NEXUS, workspace architecture, MAC, MAD, data model, API/events, security, integrations, deployment, testing, roadmap and safe desktop project ingestion.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for implementation status. Documentation describes intended behavior; it does not imply that a feature is already implemented or operational.
