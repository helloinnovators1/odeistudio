# Hosting and Infrastructure Provider Integrations

## Scope
The MAC should centrally manage supported hosting and infrastructure providers other than Vercel. Vercel remains a separate integration boundary per product direction.

## Initial provider candidates
- Namecheap: domain registrar, DNS and supported hosting/account functions.
- Bluehost: supported hosting/account/domain functions; capability depends on product and account/API access.
- AWS: cloud resources, networking, compute, storage and deployment services.
- Google Cloud: cloud resources, networking, compute and deployment services.
- DigitalOcean: droplets, app platform, databases, DNS and related resources where available.
- Cloudflare: DNS, zones, SSL/TLS, security and edge services.

These are candidate integrations, not claims that every operation is currently implemented or that every product tier exposes a public API. Verify each provider's current official API, authentication model, terms, scopes and product-specific limitations before implementation.

## Adapter design
Define a provider adapter interface with methods/capabilities such as connect, validateConnection, listAccounts, listProjects, listDeployments, getDeployment, configureBuild, listEnvironmentVariables, setEnvironmentVariable, deploy, rollback, getLogs, listDomains, manageDnsRecord, getSslStatus and disconnect. Implement only methods genuinely supported by each provider; return explicit unsupported-capability responses otherwise.

## Security
Use OAuth or scoped API tokens where available; prefer short-lived credentials. Store credentials in the secret vault, not browser storage or MongoDB plaintext. Require explicit consent and least-privilege scopes. Log actor, tenant, provider, resource, action, timestamp, outcome and provider request ID, while redacting credentials.

## Operational safeguards
- Preview changes before applying them to production.
- Require confirmation and, for high-risk actions, a second approver.
- Use idempotency keys and provider request IDs where supported.
- Respect provider rate limits and retry-after guidance.
- Verify provider state after writes instead of assuming success.
- Detect configuration drift and surface sync failures.
- Maintain provider-specific recovery procedures.
