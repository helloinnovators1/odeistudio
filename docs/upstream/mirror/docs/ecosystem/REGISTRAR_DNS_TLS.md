> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/REGISTRAR_DNS_TLS.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/REGISTRAR_DNS_TLS.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# What “Public DNS/TLS needs your registrar” means

**Updated:** 2026-07-24

## Plain language

| Term | Meaning |
|------|---------|
| **Registrar** | Company that sells/controls the domain name (Namecheap, GoDaddy, IONOS, …) |
| **DNS** | Public phonebook: `pay.odeiafrica.com` → IP address of your server/CDN |
| **TLS** | HTTPS certificate so browsers show the padlock for that hostname |

Our repo **hosts and routes** every product (ports + gateway).  
The **public internet** only learns those names after **you** (or our API scripts with your keys) publish DNS at the registrar/DNS host.

```
User browser
   → DNS lookup pay.odeiafrica.com     ← registrar / Cloudflare
   → Your edge IP (VPS / CDN)
   → ODEI gateway / Caddy (Host header)
   → Product upstream (Pay :5215, etc.)
   → TLS terminated at edge (Let's Encrypt / Cloudflare)
```

## What we automated

1. Local independent domains (`*.localhost:8080`) — **no registrar**  
2. Registrar payloads for Namecheap / GoDaddy / IONOS / Cloudflare  
3. `hosting/activate_dns.py` — pushes records when API keys exist  
4. `hosting/verify_domains.py` — verifies gateway + public resolution  

## What only you can do

1. Buy/own `odeiafrica.com` (or your apex) at a registrar  
2. Put API keys / edge IP in `hosting/.env.registrar` (from `.env.registrar.example`)  
3. Point DNS (script or UI) and wait for propagation  

## Supported providers

- https://www.namecheap.com — `registrars/namecheap-hosts.csv` + API  
- https://www.godaddy.com — `registrars/godaddy-records.json` + API  
- https://www.ionos.com — `registrars/ionos-records.json` + API  
- Cloudflare (DNS/TLS) — recommended even if domain bought elsewhere  

See `hosting/registrars/PLAYBOOK.md`.
