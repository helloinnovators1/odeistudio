# Provider Capability Research — Initial Verification

Research date: 2026-11-20. This is an initial official-documentation review, not a claim that ODEI has connected or tested these providers.

## Verified integration surfaces

| Provider | Officially documented surface | MAC integration implication |
|---|---|---|
| Namecheap | Namecheap API supports domain search/registration and account domain operations; DNS methods include nameserver and host-record management. A sandbox environment is provided. | Build a registrar/DNS adapter first. Use sandbox for integration tests. Do not assume its API manages arbitrary hosting workloads. |
| Bluehost | Bluehost documentation describes account API keys for its AI Gateway. Hosting account developer access may be through cPanel/Plesk or FTP/SFTP depending on the package. | Do not claim a universal Bluehost hosting-control API. For compatible accounts, investigate customer-authorized cPanel UAPI/WHM API access and test the exact hosting plan. Treat Bluehost AI Gateway keys as a separate AI-provider integration. |
| cPanel / WHM (hosting control panel, not a host) | Official UAPI and WHM API 1 support account and server administration; API tokens and permissions are documented. | Implement a distinct cPanel/WHM adapter where the hosting account enables the relevant API and grants least-privilege tokens. This can support some Bluehost and other cPanel-based hosts, but is not guaranteed on every plan. |
| AWS | Official AWS IAM documentation and service APIs support programmatic, permission-scoped cloud administration. | Build service-specific AWS adapters using IAM roles/temporary credentials and narrowly scoped policies. Avoid broad root access keys. |
| Google Cloud | Official IAM and service APIs support resource-level access controls, service accounts and short-lived credentials. | Use service accounts/workload identity and least-privilege IAM roles; build adapters per product (compute, storage, DNS, etc.). |
| DigitalOcean | Official API covers Droplets, Kubernetes, databases and other resources; App Platform API documents app creation, deployment, logs, health and rollback operations. Domains/DNS are also exposed. | Strong candidate for an early full hosting adapter, with scopes and per-endpoint capabilities. |
| Cloudflare | Official APIs/documentation support zone and DNS configuration; availability depends on product and account plan. | Build DNS/edge/security adapter with explicit zone permissions and plan-aware capability checks. |

## Sources (official documentation)

- Namecheap API overview: https://www.namecheap.com/support/api/intro/
- Namecheap API methods: https://www.namecheap.com/support/api/methods/
- Namecheap DNS methods: https://www.namecheap.com/support/api/methods/domains-dns/
- Bluehost API keys (AI Gateway): https://www.bluehost.com/help/article/bh-manage-and-create-api-keys
- Bluehost developer access guidance: https://www.bluehost.com/help/article/granting-developer-access-to-bluehost-best-practices-and-security-guidelines
- cPanel & WHM developer portal: https://api.docs.cpanel.net/
- cPanel WHM API 1: https://api.docs.cpanel.net/whm/introduction
- cPanel API tokens: https://docs.cpanel.net/cpanel/security/manage-api-tokens-in-cpanel/
- AWS IAM: https://docs.aws.amazon.com/iam/
- Google Cloud IAM: https://docs.cloud.google.com/iam/docs
- DigitalOcean API overview: https://docs.digitalocean.com/reference/api/
- DigitalOcean App Platform API: https://docs.digitalocean.com/reference/api/reference/apps/
- DigitalOcean DNS API: https://docs.digitalocean.com/products/networking/dns/reference/
- Cloudflare DNS documentation: https://developers.cloudflare.com/dns/zone-setups/

## Engineering rules

1. The MAC is the unified control plane; adapters expose only capabilities verified for that provider, account, product and plan.
2. Never equate domain registrar access with application hosting access.
3. Never equate cPanel access with full Bluehost account/billing access.
4. Never collect provider account passwords when scoped OAuth/API tokens or delegated access are available.
5. Validate credentials and discover account capabilities during connection setup.
6. Keep Vercel outside the general non-Vercel hosting adapter scope, as required by product direction.
7. Before enabling write operations, implement preview/dry-run where possible, explicit confirmation, audit events, least privilege, rate-limit handling and post-write verification.
8. Do not mark an integration as connected until a real authenticated health check succeeds.
