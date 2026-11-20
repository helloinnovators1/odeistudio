# ODEI Studio — Architecture Foundation

## Product principle
ODEI Studio is an AI-native development operating system: a coordinated environment for developers, AI agents, code intelligence, execution infrastructure and governance. The MAC is the authoritative control plane for managing and configuring the studio. The MAD is its operational visibility surface.

## Logical planes
1. **Experience plane** — modular multi-card workspace; multi-tab navigation; editor, terminal, agent chat, file explorer, diffs, previews and logs.
2. **Intelligence plane** — repository ingestion, symbol/dependency graph, embeddings, semantic retrieval, project rules and durable task context.
3. **Orchestration plane** — task planner, specialist agents, tool registry, policy checks, queues, state machine and human approval gates.
4. **Execution plane** — isolated ephemeral workspaces, shell, package installation, tests, browser automation and resource/time limits.
5. **Integration plane** — GitHub App, model providers, MongoDB, hosting providers, domain registrars, DNS providers, observability and optional MCP servers.
6. **Control plane (MAC)** — environment configuration, secret references, provider connections, infrastructure operations, identity, tenant administration, policies, feature flags and platform settings.
7. **Operations plane (MAD)** — service health, agent queues, execution utilization, model spend, hosting status, deployments, incidents, security events and operational analytics.

## MAC authority and scope
The MAC is the overall management and configuration centre of ODEI Studio. It must provide a unified provider-neutral interface for supported integrations, while exposing provider-specific capabilities accurately.

- **Environment configuration:** inventory variables by environment, application, service and deployment target; create/update/validate/rotate values; version changes; support approval workflows; provide change history and rollback where safe.
- **Secret lifecycle:** store values in a managed secret manager or encrypted vault using envelope encryption/KMS. Persist references and metadata in MongoDB, not plaintext secrets. Reveal-once or masked input; never return saved secrets to the browser. Redact logs and agent context. Restrict read/write access by role and record every privileged action.
- **Hosting management:** connect, inspect and manage supported non-Vercel providers through official APIs, SDKs, webhooks or documented control mechanisms. Support account connection, projects/sites, deployment targets, environment configuration, build settings, logs, domains, SSL and resource management only where the provider supports them.
- **Vercel boundary:** Vercel remains a distinct integration boundary and is excluded from the MAC's general hosting-provider management scope as specified. If a Vercel connection is later added, its scope must be explicitly defined rather than silently folded into the other-hosting adapter.
- **Domains/DNS:** registrar and DNS provider connections, zone/record operations, verification, SSL status and domain-to-deployment mapping where supported.
- **Other platform services:** databases, GitHub, AI/model providers, storage, queues, observability, billing, user/tenant identity and agent/tool policies.

The MAC must not promise universal one-click configuration. Providers have different APIs, product tiers, account permissions and operational limits. Each adapter must publish its supported capabilities and report unsupported actions clearly.

## MAD scope
The MAD presents live operational state, not fabricated placeholder metrics: service health, provider connection status, deployment history, queue depth, active agent runs, error rates, spend, quotas, security alerts and audit summaries. Every metric must have a defined source, freshness indicator and tenant/role access policy.

## Agent lifecycle
`request → classify → plan → approve → execute → validate → repair → review → merge/deploy`

Every step requires a durable task record, traceable tool calls, bounded permissions, cancellation, retry limits and structured output. Untrusted repository content must never be treated as system instructions.

## Data domains
Suggested MongoDB domains: users, organizations, memberships, projects, repositories, workspaces, tasks, agent_runs, tool_events, artifacts, deployments, usage_records, policies, audit_events, integration_connections, environment_configs and secret_references. Enforce tenant ownership in every query and index access patterns. Store secret material in a managed secret store; persist only references, versions and metadata in MongoDB.

## Security baseline
- Rotate exposed credentials before connecting services.
- Keep secrets server-only; never commit `.env.local`.
- Prefer GitHub App installation tokens over personal access tokens.
- Use short-lived provider credentials and scoped permissions.
- Run agents in disposable isolated containers with network egress controls.
- Require approval for destructive actions, DNS changes, credential rotation and production-impacting operations.
- Redact secrets from logs and model context.
- Add rate limits, quotas, audit trails, break-glass access and recovery procedures.

## Implementation boundary
A module is not operational until its backend behavior, provider authorization, tenant isolation, tests, observability, failure handling and documentation are implemented. A visual control or placeholder metric is not evidence of a functioning service.
