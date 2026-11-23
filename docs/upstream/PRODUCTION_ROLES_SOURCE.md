> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/PRODUCTION_ROLES.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ecosystem/PRODUCTION_ROLES.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# Production roles (autonomous) — ODEI Multi-Ecosystem

**Updated:** 2026-07-24  
**Status:** Implemented on product auth surfaces (local Identity stand-in)

> **Security boundary:** this is a browser-local UX simulation, not production
> authorization. Roles, sessions, demo invite codes, and master-admin policy are
> delivered to/stored in the browser. Admin pages use client-side redirects;
> protected server routes and APIs do not yet validate trusted ODID claims.
> Do not expose owner/operator data publicly until server-side `401/403`
> enforcement exists. See
> [`ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md`](ENVIRONMENT_AUDIENCE_AND_STUDIO_MEDIA_AUDIT.md).

## Why the Role dropdown was removed

Production roles are **not picked on Login**. They are **assigned autonomously** by:

1. **Default policy** — Create account → always **Member**
2. **Staff invite** — codes / signed invites → **Operator** or **Admin**
3. **Future ODEI Identity (ODID)** — JWT / ODID claims replace the local registry

## What happens now

| Action | Role assignment | After auth |
|--------|-----------------|------------|
| Create account (no invite) | `member` | `/dashboard/` (**Wallet / DEX / Exchange:** `/app/`) |
| Login (known member) | resolved from registry | `/dashboard/` (**Wallet / DEX / Exchange:** `/app/`) |
| Login/signup + invite `ODEI-OPERATOR` | `operator` (+ member) | `/admin/` |
| Login/signup + invite `ODEI-ADMIN` / `ODEI-MAC` | `admin` (+ member) | `/admin/` |
| Direct `/admin/` without staff claim | blocked → login or dashboard | — |

**Wallet / DEX / Exchange exception:** `destinationForRole` sends members to **`/app/`** for `wallet`, `dex`, and `exchange`. See [`ODEI_WALLET_UNIVERSAL_ACCOUNT.md`](ODEI_WALLET_UNIVERSAL_ACCOUNT.md) · [`ODEI_DEX_TRADING_SHELL.md`](ODEI_DEX_TRADING_SHELL.md) · [`ODEI_EXCHANGE_CUSTODIAL_SHELL.md`](ODEI_EXCHANGE_CUSTODIAL_SHELL.md).

## Pages

- `/login.html` — no Role select; optional staff invite field  
- `/create-account.html` — Member by default; optional invite  
- `/staff-invite.html` — elevate an email with a code  
- `/dashboard/` — member surface (session required)  
- `/app/` — **Wallet / DEX / Exchange:** member product apps  
- `/admin/` — MAC (staff claim required)

## Demo invite codes (replace with Identity)

- `ODEI-OPERATOR` → operator  
- `ODEI-ADMIN` → admin  
- `ODEI-MAC` → admin  

## Storage (local stand-in for Identity)

`localStorage.odei_identity_roles_{productId}` maps email → `{ roles, primary, source }`.

## Regenerate

```powershell
python _enable_odei_auth_pages.py
```

See also: `docs/ODEI_AUTH_UI.md`
