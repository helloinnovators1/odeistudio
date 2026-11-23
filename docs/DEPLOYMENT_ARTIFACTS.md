# Deployment Artifacts and Provider Setup

**Status:** the ODEI Studio frontend is deployed to Vercel and served at `https://zurios.vercel.app/odeistudio` through live host-project rewrites. Backend identity, database, secret, worker and operational production gates remain open.

## Web frontend — Vercel

Configure a Vercel project for this repository with:

- Framework preset: Vite
- Root directory: `apps/web`
- Install command: `npm ci`
- Build command: `npm run build`
- Output directory: `dist`

The checked-in `apps/web/vercel.json` records these build settings and the SPA fallback rewrite. Enable deployment previews only with non-production ODID and API resources.

Configure these Vite build-time variables in the Vercel project. Values are public and become part of the browser bundle; never put credentials in them.

| Variable | Required value |
|---|---|
| `VITE_ODEI_API_BASE_URL` | Exact HTTPS API origin only (for example, `https://api.example.com`); the browser transport appends `/api/v1` itself |
| `VITE_ODID_ISSUER` | Exact production ODID issuer |
| `VITE_ODID_CLIENT_ID` | Public browser client ID registered with ODID |
| `VITE_ODID_REDIRECT_URI` | Exact HTTPS callback URL registered with ODID |
| `VITE_ODID_API_RESOURCE` | Exact API resource/audience requested by the browser |
| `VITE_ODID_SCOPES` | Space- or comma-separated approved scopes |
| `VITE_BASE_PATH` | Optional asset base path; use `/` for a root deployment or `/odeistudio/` for a subpath deployment |

Do not guess the API URL path or ODID values. Confirm them against the deployed API routes and ODID application registration. Register the exact redirect URI and exact browser origin at the identity provider and API. `VITE_BASE_PATH` changes generated asset URLs only; a subpath mount also requires a route/rewrite on the owning Vercel project. The checked-in setting does not create that cross-project route.

### Required host routing for `https://zurios.vercel.app/odeistudio`

The ODEI frontend is a separate Vite project mounted below the existing Zurios domain. The live ODEI project is `odeistudio` (root `apps/web`, Vite, Node.js `22.x`) with `VITE_BASE_PATH=/odeistudio/`; its production origin is `https://odeistudio.vercel.app`. The existing `zurios` host project has already promoted and verified the two external rewrite rules below in equivalent regex form. The following `vercel.json` example is a reference for the same routing intent only; its placeholder must never be deployed:

```json
{
  "rewrites": [
    { "source": "/odeistudio", "destination": "https://<ODEI-PROJECT-DEPLOYMENT>/" },
    { "source": "/odeistudio/:path*", "destination": "https://<ODEI-PROJECT-DEPLOYMENT>/:path*" }
  ]
}
```

The host rewrite intentionally strips the public `/odeistudio` prefix when forwarding to the ODEI deployment root. Vite-generated browser asset URLs retain `/odeistudio/`, so subsequent asset requests pass through the same host rewrite and arrive at the upstream deployment's root-level `/assets/...` paths. Keep these specific rules ahead of the Zurios application's SPA fallback/catch-all. Preserve the existing root application, domain ownership, authentication/SSO and unrelated routes. Verify the root route, nested client-side routes, JS/CSS/assets, API calls, ODID callback and refresh/deep-link behavior on a preview before production promotion.

Live Vercel routing is managed on the existing host project and is intentionally separate from this repository's Vite build config. Do not replace the active host rules with the placeholder example. HTTP smoke checks currently return 200 for the Zuri OS root, ODEI root, `/odeistudio/nexus`, and the built JS/CSS assets; authenticated browser journeys and backend integration acceptance remain outstanding.

## API container — provider-neutral OCI image

Build from the API directory:

```sh
docker build --pull -t odei-api:release ./apps/api
```

The image:

- Installs the API package and its declared production dependencies from `pyproject.toml`.
- Runs as UID/GID 10001, not root.
- Uses a production environment by default, disabling FastAPI docs and ReDoc.
- Binds to `0.0.0.0` and honors the platform-provided `PORT` (default 8000).
- Does not trust forwarded headers by default. Configure trusted proxy handling only when the exact ingress topology and trusted proxy ranges are known.
- Exposes liveness separately from readiness; readiness remains HTTP 503 until a transaction-capable MongoDB topology is configured and reachable.

Recommended runtime controls, where supported:

- Read-only root filesystem, a small writable `/tmp`, dropped Linux capabilities, no-new-privileges, non-root UID, bounded memory/CPU/PIDs and graceful termination.
- Private network access to MongoDB and managed secret storage; no public database ingress.
- Exact HTTPS CORS origins only.
- Inject secrets at runtime from a managed secret manager. Never bake them into image layers, build arguments, Vite variables or CI logs.

Required API configuration includes `ENVIRONMENT=production`, `MONGODB_URI`, `MONGODB_DATABASE`, ODID verifier settings (`AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL`, `AUTH_ALLOWED_CLIENT_IDS`), exact `CORS_ALLOWED_ORIGINS`, and the approved model/secrets/signing configuration used by the enabled features. Confirm the exact release's settings model before deployment.

## Workers are separate workloads

Do not deploy the NEXUS execution worker in the API container. It needs a dedicated, hardened Linux worker host with an approved OCI runtime and a stronger hostile-code boundary (gVisor, Kata, microVM or equivalent). Never mount a general-purpose host Docker socket into an internet-facing API or worker. Do not start the MAC deployment worker until real provider and secret-resolver adapters have been implemented, allowlisted and independently reviewed.

## Database and migrations

Use MongoDB Atlas or another supported replica set/sharded cluster with TLS, private networking, least privilege, encrypted backups and point-in-time recovery. A standalone MongoDB deployment is not supported for task/audit transactions. Run migrations and index initialization in staging first; perform and record an isolated restore drill before production.

## Release gate

The container build/smoke workflow proves image construction, non-root execution, liveness and fail-closed readiness without a database. It does not prove production ODID, MongoDB, provider integration, worker isolation, backup restoration, domain/TLS, authenticated E2E or rollback acceptance. Keep production **NO-GO** until every gate in [Production Readiness](PRODUCTION_READINESS.md) is evidenced.
