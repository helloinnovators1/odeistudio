> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/EDGE_IP_AND_API_KEYS.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/EDGE_IP_AND_API_KEYS.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# How to get Edge IP and API keys

**Updated:** 2026-07-24  
**Also see:** `docs/GITHUB_HOSTING.md` · `docs/REGISTRAR_DNS_TLS.md` · `hosting/registrars/PLAYBOOK.md`

## Edge IP (`ODEI_EDGE_IP`)

That’s the **public IP of the machine/CDN that will serve your live sites** — not your laptop’s local IP (unless you deliberately expose it).

1. Rent a VPS (DigitalOcean, AWS Lightsail, Azure, Hetzner, etc.) or use a load balancer / Cloudflare origin.
2. Install/run the ODEI gateway (or Caddy) on that box so it answers HTTP/HTTPS.
3. Copy that server’s public IPv4 into `hosting/.env.registrar`:
   ```
   ODEI_EDGE_IP=203.0.113.10
   ```
   On Linux: `curl -4 ifconfig.me` · On the VPS dashboard: look for **Public IPv4**.

Until you have a public server, leave it unset and stay on `*.localhost:8080`.

### Via GitHub (recommended for production)

Store the same value as a repository secret `ODEI_EDGE_IP` (Settings → Secrets and variables → Actions).  
Workflows in `.github/workflows/` inject it when activating DNS or deploying the edge.

---

## API keys (per registrar)

You create these **inside the account that owns the domain**. Put them in `hosting/.env.registrar` (copy from `.env.registrar.example`), **or** as GitHub Actions secrets (never commit them).

| Provider | Where to get keys |
|----------|-------------------|
| **Namecheap** | Profile → Tools → **Namecheap API** → enable API, whitelist your public IP → copy API user/key. Docs: https://www.namecheap.com/support/api/intro/ |
| **GoDaddy** | https://developer.godaddy.com/ → create API key + secret (production vs OTE test) |
| **IONOS** | https://developer.hosting.ionos.com/ → create API key (prefix + secret) |
| **Cloudflare** (recommended) | Cloudflare dashboard → My Profile → **API Tokens** → create token with Zone DNS Edit; Zone ID is on the domain’s Overview page |

You only need keys for **one** DNS host (the place that actually controls DNS for `odeiafrica.com`). If the domain is at GoDaddy but you move nameservers to Cloudflare, use Cloudflare keys.

### GitHub secret names

See `hosting/github-secrets.example` for the full list (`GODADDY_API_KEY`, `NAMECHEAP_API_KEY`, `CLOUDFLARE_API_TOKEN`, etc.).

---

## Then (local)

```powershell
copy hosting\.env.registrar.example hosting\.env.registrar
# edit: ODEI_EDGE_IP + your provider keys
python hosting\activate_dns.py --provider godaddy   # or namecheap | ionos | cloudflare
```

Or skip APIs and paste records from `hosting/registrars/` into the registrar’s DNS UI by hand.

## Then (GitHub)

1. Push this repo to GitHub (`git init` at ecosystem root if needed).
2. Add secrets from `hosting/github-secrets.example`.
3. Actions → **ODEI DNS Activate** → Run workflow → pick provider.
4. Actions → **ODEI Deploy Edge** → Run workflow (after SSH secrets are set).
