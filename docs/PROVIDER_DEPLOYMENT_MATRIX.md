# Multi-provider Hosting, Domain and Infrastructure Deployment Matrix

**Assessment date:** 2026-11-23  
**Code baseline:** `1fdaaa2405682ad7839773e3aecbbc0f60349de8`  
**Decision:** ODEI frontend deployed on Vercel at `https://zurios.vercel.app/odeistudio`; API, database, workers, identity, secrets, observability and disaster recovery remain unprovisioned or unaccepted.

This document covers the full hosting chain, not just the database. A registrar, DNS operator, frontend host, API host, worker host, database, object store, secret manager and monitoring vendor are different roles. One company may sell several of them, but each role must be configured and tested independently.

## 1. Recommended logical architecture

| Layer | Recommended responsibility | Candidate providers / notes | Release state |
|---|---|---|---|
| Source and CI | Source of truth, review, build, tests, scans, artifact provenance | GitHub repository and GitHub Actions | CI/security workflows verified; branch protection is not configured |
| Domain registrar | Domain ownership, renewal, transfer lock, registrar MFA | Namecheap, Bluehost (correct spelling), Cloudflare Registrar, other ICANN-accredited registrar | Account/domain ownership, renewal and MFA not verified |
| Authoritative DNS | DNS zones, records, DNSSEC, CAA, health-based changes if supported | Namecheap DNS, Bluehost DNS, Cloudflare DNS, Route 53, other managed DNS | No production zone or records verified |
| Frontend hosting | Static/edge React web build, preview deployments, custom domain/TLS | Vercel project `odeistudio` serves `https://zurios.vercel.app/odeistudio`; separate Zuri OS root project is preserved | Deployed and HTTP-smoke-verified; production frontend configuration limited to VITE_BASE_PATH |
| API hosting | Long-running HTTPS FastAPI service, readiness/liveness, graceful shutdown, autoscaling | Render, Fly.io, Railway, DigitalOcean App Platform, AWS ECS/Fargate, Google Cloud Run, Azure Container Apps, or a properly operated VPS | No production API host selected or provisioned |
| Execution workers | Isolated long-running worker pool for untrusted code; separate from public API | Dedicated hardened VMs, Kubernetes nodes, ECS tasks, or equivalent; gVisor/Kata/microVM isolation | No production worker fleet accepted |
| MAC deployment worker | Privileged, narrowly scoped deployment control plane worker | Dedicated isolated service with separate identity, queue and provider-specific credentials | Worker foundation exists; production provider adapters and fleet unverified |
| Database | Transaction-capable MongoDB replica set/sharded cluster | MongoDB Atlas or self-managed supported topology | CI replica-set integration passed; no production cluster configured |
| Object/artifact storage | Private durable artifact and backup storage with lifecycle policies | AWS S3, Cloudflare R2, Google Cloud Storage, Azure Blob, or compatible private object store | No production bucket, encryption or lifecycle policy verified |
| Secrets and key management | Runtime secret injection, workload identity, KMS-backed key storage/rotation | AWS Secrets Manager/KMS, GCP Secret Manager/Cloud KMS, Azure Key Vault, Doppler, 1Password Secrets Automation, or equivalent | No live provider integrated or accepted |
| Identity | ODID issuer, signing keys/JWKS, client registrations and MFA | The actual ODID identity provider and operator directory | Production issuer/client registration unverified |
| Model provider | Server-side model access, budget/rate controls, retention policy | OpenAI or approved compatible provider | No production key/model/account policy verified |
| Email / notifications | Transactional email, domain authentication, delivery events | Postmark, Resend, SendGrid, Amazon SES, Mailgun, or equivalent | Not verified; only required if product flows send email |
| Observability | Logs, metrics, traces, alerting, uptime and incident paging | OpenTelemetry plus Grafana/Prometheus, Datadog, New Relic, Sentry, cloud-native tools | No production collector, alerts or on-call verified |
| Edge/security | TLS, WAF, DDoS controls, rate limits, bot controls | Cloudflare, cloud-provider edge/WAF, host-native controls | No production policy verified |
| Backup/DR | Encrypted backup, PITR, immutable/off-account copy, restore drills | Database-native backups plus independent object-store backup | No production restore evidence |

Provider names are candidate categories, not an assertion that an integration exists or that a particular vendor plan supports every required capability. Confirm current vendor product limits, regions, pricing, API access and contractual terms before selection.

## 2. Namecheap, Bluehost and domain/DNS ownership

### Correct provider roles

- **Namecheap** is a registrar and may also provide DNS and hosting products. Domain registration does not deploy the ODEI web application, FastAPI API, MongoDB or isolated execution workers.
- **Bluehost** (not “Bluegost”) is a hosting provider with domain-related products. Shared WordPress/PHP hosting should not be assumed to support a long-running FastAPI API, MongoDB replica-set topology, background worker, OCI runtime or hostile-code sandbox. A separately provisioned VPS/dedicated product must be evaluated against the full security and operations requirements.
- **Vercel** is a candidate frontend deployment platform for the web app. Do not assume it is the right place for the persistent execution worker or MAC deployment worker.
- Pick exactly one authoritative DNS service for each zone. The registrar delegates nameservers; authoritative DNS hosts the records. Avoid simultaneous competing zone authorities.

### Domain inventory to create before changing DNS

Record each actual domain and subdomain, purpose, registrar, authoritative nameservers, DNSSEC state, certificate owner, target host, TTL, renewal owner and rollback record. Do not infer the user's domain name.

| Hostname pattern | Purpose | Target | Notes |
|---|---|---|---|
| Apex domain | Marketing / canonical site | Frontend host or redirect | Follow the frontend host's verified apex instructions |
| `www` | Canonical alias | Frontend host | Set one canonical redirect direction |
| `app` | ODEI Studio frontend | Vercel or selected frontend host | HTTPS, exact ODID callback origin |
| `api` | FastAPI API | API host ingress | HTTPS, strict CORS and readiness |
| `status` | Public status page (optional) | Status provider | No internal topology or secrets |
| `assets` | Public static assets only (optional) | CDN/object store | Never expose private execution artifacts |
| `mail` / MX | Email service, if used | Mail provider | Preserve existing mail service records during migration |

The table is a naming template only; it is not a proposed live DNS change.

### DNS and registrar hardening checklist

- [ ] Verify domain ownership, registrar account recovery contacts, billing owner and renewal date.
- [ ] Enable phishing-resistant MFA where available; use unique credentials and recovery codes stored in an approved vault.
- [ ] Enable registrar transfer lock and registry lock if appropriate and available; restrict account/API access.
- [ ] Confirm authoritative nameservers and export the current zone before edits.
- [ ] Inventory and preserve existing MX, SPF, DKIM, DMARC, verification and third-party records.
- [ ] Enable DNSSEC at the authoritative DNS provider and publish/verify the DS record at the registrar; test validation end-to-end. Do not change nameservers and DS records blindly.
- [ ] Configure CAA records for only the certificate authorities intended to issue certificates, after confirming the host's CA requirements.
- [ ] Set SPF to a single valid record; configure provider-specific DKIM selectors and a DMARC policy. Start with reporting/monitoring before enforcement if current senders are unknown.
- [ ] Lower relevant TTLs ahead of a planned cutover; preserve old targets until new targets are healthy.
- [ ] Validate A/AAAA/CNAME/ALIAS/ANAME behavior with the chosen DNS provider; avoid conflicting apex records and stale AAAA records.
- [ ] Validate certificate issuance, renewal, redirects, HSTS readiness and hostname coverage before enabling strict HSTS.
- [ ] Test from multiple public resolvers and networks; record DNS propagation and TLS results.
- [ ] Keep a timestamped pre-change zone export and rollback plan; do not delete old hosting until traffic and email have been verified.

## 3. Provider selection and deployment fit

### Frontend: Vercel or equivalent

Use Vercel only for the frontend build and edge delivery unless a separate workload is explicitly evaluated. Validate:

- [ ] Repository connection and least-privilege GitHub app permissions.
- [ ] Production branch is `main`; previews use non-production API, identity and data.
- [ ] Node/npm versions match the lockfile and CI; use `npm ci`, not mutable dependency resolution.
- [ ] Build output and environment variables are reviewed; only public variables are exposed to browser bundles.
- [ ] Set exact production API base URL, ODID issuer/client/callback and allowed origins; preview credentials are isolated.
- [ ] Configure custom domain, DNS validation, HTTPS and canonical redirects.
- [ ] Verify deployment protection for previews and avoid exposing customer data in preview environments.
- [ ] Verify rollback to a known-good immutable deployment and compatibility with current API/database schema.
- [ ] Confirm platform functions are not being used as durable queues or untrusted-code workers.

Cloudflare Pages, Netlify or static object storage/CDN can serve the frontend if the build and routing requirements are met. The same checks apply.

### API: managed container host or cloud platform

Select one host that can run the FastAPI container as a persistent HTTPS service and supports the required network path to MongoDB and secret manager. Evaluate Render, Fly.io, Railway, DigitalOcean App Platform, AWS ECS/Fargate, Google Cloud Run and Azure Container Apps against:

- supported regions and data residency;
- private networking and outbound IP/network policy;
- long-running request/streaming behavior for SSE;
- request/response size, connection, idle and execution timeouts;
- graceful shutdown, autoscaling, minimum instances and cold starts;
- secret injection/workload identity;
- health checks, deploy rollback and logs/metrics;
- cost ceilings, quotas and support/SLA;
- compliance and data processing terms.

Do not select a platform solely because it can build a Dockerfile. Confirm its streaming and connection semantics for NEXUS SSE, background processing separation and MongoDB connectivity under production load.

### Bluehost / Namecheap hosting products

Do not deploy the API or execution runtime to generic shared hosting by assumption. If evaluating a VPS or dedicated server from either vendor:

- [ ] Verify supported OS/kernel, rootless OCI runtime, cgroups v2, namespaces, seccomp and AppArmor/SELinux.
- [ ] Verify persistent disk encryption, snapshots, private networking, firewall controls, static egress and backups.
- [ ] Verify unattended security patching, console recovery, monitoring, reboot behavior and support SLA.
- [ ] Verify that nested virtualization or microVM/Kata/gVisor requirements are actually supported; do not infer this from “VPS” marketing.
- [ ] Run the hostile-code isolation test suite on the exact instance class before accepting it.
- [ ] Keep the registrar account separate from server administration; use SSH keys, disable password/root login where supported, and restrict management ingress.
- [ ] Do not store production secrets in a hosting control panel unless its access controls, audit and secret handling meet the policy.

If those requirements cannot be met, use the vendor only for registration/DNS or a static website and host the API/workers elsewhere.

## 4. Database, storage and recovery

### MongoDB Atlas or managed/self-hosted MongoDB

- [ ] Select a replica-set or sharded topology with transaction support; standalone MongoDB is not ready for task/audit workflows.
- [ ] Select region and network model; use private endpoint/private peering where available, otherwise tightly restricted TLS access.
- [ ] Create separate application, migration, audit-writer, audit-reader and operations identities as needed.
- [ ] Restrict audit writer permissions to insert-only at the database level; separate audit read access.
- [ ] Create and validate indexes/migrations before traffic; use least privilege and schema compatibility.
- [ ] Configure automated backups/PITR and retention; restore to a clean cluster and measure RPO/RTO.
- [ ] Exercise failover, primary stepdown, network loss, pool exhaustion and transaction retries.
- [ ] Rotate any credential disclosed in prior project setup material; revoke the old one and inspect access logs.
- [ ] Monitor replication lag, connections, slow queries, storage, backup health and transaction aborts.

### Object storage and artifacts

- [ ] Use private buckets/containers, encryption at rest, TLS, workload identity and least-privilege bucket policies.
- [ ] Separate user artifacts, worker scratch data, logs and backups into distinct prefixes/buckets/accounts where practical.
- [ ] Block public access; issue short-lived signed URLs only after authorization and scope checks.
- [ ] Apply retention/lifecycle, malware/content scanning, size limits, checksum validation and orphan cleanup.
- [ ] Enable versioning/object lock for backup/audit use cases where appropriate; test restore and deletion obligations.
- [ ] Ensure artifacts are never executable by default and are not served from the application origin without safe content headers.

## 5. Secrets, identity and external integrations

- [ ] Choose a single primary secrets/KMS system for each environment; avoid copying production secrets into GitHub Actions when OIDC/workload identity can be used.
- [ ] Use separate credentials for CI, frontend, API, database migration, worker, MAC provider, email and observability.
- [ ] Define owners, rotation cadence, expiry alerting, emergency revocation and key recovery for each secret.
- [ ] Never place private credentials in Vercel public environment variables, frontend build output, container layers, source maps, logs or model context.
- [ ] Register production ODID issuer/client/redirect/scopes/audience and verify JWKS rotation and token lifecycle.
- [ ] Configure model provider budget, usage alerts, approved model, rate limits, retention and data-transfer consent.
- [ ] Configure email SPF/DKIM/DMARC and webhook signature/replay protection if email flows are enabled.
- [ ] Keep cloud/provider API credentials isolated by environment and capability; MAC provider allowlists must be deployment-owned and exact.

## 6. Environment and DNS layout

Use separate development, preview, staging and production accounts/projects where feasible, not merely different environment variable names in one shared production project.

| Environment | Frontend | API | Database | Identity | Credentials/data |
|---|---|---|---|---|---|
| Development | Local/dev host | Local API | Disposable DB | ODID dev tenant or test issuer | Synthetic data only |
| Preview | Protected preview URL | Isolated preview API | Disposable/isolated DB | Preview client | Per-PR, short-lived, no production secrets |
| Staging | Staging domain | Staging API + worker | Production-like replica set | Staging client/tenant | Synthetic or masked data |
| Production | Canonical app domain | Production API + dedicated workers | Production replica set/sharded cluster | Production issuer/client | Managed secrets, real customers only after GO |

## 7. Safe cutover sequence

1. Inventory current registrar, nameservers, DNS records, web hosting, API host, database, email and integrations. Export current DNS zone and capture current TTLs.
2. Select provider ownership boundaries and regions; complete threat model, cost estimate, data residency and vendor terms.
3. Provision isolated staging first: network, secret manager, MongoDB replica set, object storage, API, frontend, worker pool and observability.
4. Configure staging ODID and test all authenticated browser flows and tenant isolation.
5. Run database migration against a restored copy; validate indexes, audit permissions, backups and restore.
6. Build immutable artifacts from a reviewed commit; scan, generate SBOM/provenance, deploy to staging and run smoke/E2E/security/worker tests.
7. Test provider failure, database failover, worker crash, queue drain, cancellation, backup restore and rollback.
8. Obtain independent security/release approval; verify branch protection and required checks.
9. Lower DNS TTLs, add only the new verified records, validate certificates and health checks, then shift traffic gradually.
10. Monitor error rates, latency, authentication, queue depth, database, worker and provider health; abort on pre-agreed thresholds.
11. Keep prior infrastructure and DNS targets available through the rollback window. Roll back application traffic only after confirming schema compatibility.
12. Record final DNS state, artifact digests, migration, approvers, smoke results and recovery point.

## 8. Provider integration policy

No vendor API credentials or account access are present in the repository evidence for this assessment. Do not add provider API keys to source control or invent a “universal” adapter. Integrate one provider at a time behind typed interfaces with:

- explicit provider identity and capability declaration;
- exact allowlisted factory reference and schema validation;
- environment-scoped credentials supplied at runtime;
- idempotency keys and durable operation receipts;
- bounded timeouts, cancellation, retries with jitter and reconciliation;
- immutable audit events with actor, tenant, target, action and result;
- dry-run/plan output before destructive changes;
- explicit approval for DNS, registrar, production deploy, database deletion or credential rotation;
- contract tests against a sandbox account and documented provider API version.

Namecheap/Bluehost DNS automation must be a separate registrar/DNS integration from Vercel frontend deployment. Never let a frontend deploy silently mutate registrar nameservers or mail records.

## 9. Provider acceptance evidence register

Create one record per actual provider account and environment. Store only non-secret account/project identifiers, region, resource IDs, evidence URLs, owner and last verification date. Keep credentials in the approved secret manager.

| Provider/service | Account/project/resource | Evidence required | Status |
|---|---|---|---|
| Namecheap registrar | Actual domain/account | Domain ownership, MFA, renewal, transfer lock, nameserver/DS state | Not verified |
| Bluehost hosting/DNS (if used) | Actual plan/server/zone | Product capability proof, hardening, backups, monitoring, support | Not verified |
| Authoritative DNS | Actual zone | Export, DNSSEC/DS, CAA, TLS, SPF/DKIM/DMARC, tested rollback | Not verified |
| Vercel/frontend | Actual project/team/domain | Production branch, build, env review, domain/TLS, rollback | Not verified |
| API host | Actual service/region | Container deploy, private network, SSE, health, autoscale, rollback | Not verified |
| Worker host | Actual worker pool | Isolation, immutable images, egress controls, quotas, crash drills | Not verified |
| MongoDB | Actual cluster | Replica set/sharding, access controls, audit roles, backup/restore | Not verified |
| Object storage | Actual bucket/account | Private policy, encryption, lifecycle, signed URL and restore tests | Not verified |
| Secrets/KMS | Actual vault/project | Workload identity, rotation, revocation, audit, recovery | Not verified |
| ODID | Actual issuer/client | PKCE, claims, JWKS rotation, tenant/RBAC acceptance | Not verified |
| Model provider | Actual project | Secret handling, consent, retention, quotas and billing alerts | Not verified |
| Email provider (if used) | Actual sender/domain | SPF/DKIM/DMARC, webhook verification, deliverability | Not verified |
| Observability | Actual workspace | SLO dashboards, alert routing, retention, incident drill | Not verified |

## 10. Go/no-go rule

Production remains **NO-GO** until the required service choices are explicit, every used provider row has real account/resource evidence, the staging environment passes all acceptance tests, secrets/previously disclosed credentials are rotated, branch protection and independent approval are active, and rollback/restore/incident drills have been signed off.

Unused providers should be marked **Not selected / not applicable** with a rationale, not configured “just in case.” A Namecheap or Bluehost account is not a prerequisite if another registrar/DNS/host is selected; provider readiness means the chosen topology is secure and operational, not that every vendor is purchased.
