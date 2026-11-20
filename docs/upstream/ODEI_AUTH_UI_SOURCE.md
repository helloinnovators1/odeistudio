> Historical source snapshot imported from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_AUTH_UI.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/main/docs/ecosystem/ODEI_AUTH_UI.md). Source tree inspected at `b9878e8dcc34942ec10fa5fddea34028a5456b42`. This is reference material, not proof of current implementation in this repository. See [the reconciled alignment guide](../UPSTREAM_ECOSYSTEM_ALIGNMENT.md).

---

# ODEI reusable auth UI

**Updated:** 2026-07-24

## Features
- Login · Create account · Reset password
- Show / hide password
- Live password progress: min 8 · capital letter · special character
- Success message + toast on successful login (and register / reset)

## Use on any product
```powershell
python _enable_odei_auth_pages.py
```
Or copy `odei-auth.css` / `odei-auth.js` and the three HTML patterns from a product that already has auth.

## Wallet / DEX / Exchange
| Product | Login | Member destination |
|---------|-------|--------------------|
| Wallet `:5220` | `/login.html` | **`/app/`** (Universal Account) |
| DEX `:5208` | `/login.html` | **`/app/`** (Trading shell) |
| Exchange `:5210` | `/login.html` | **`/app/`** (OEXC custodial shell) |

Operator / Admin → `/admin/` (MAC) on each product.

Optional: `/dashboard/` remains a member ops hub (KPIs from the same product store).

Maps: [`ODEI_WALLET_UNIVERSAL_ACCOUNT.md`](ODEI_WALLET_UNIVERSAL_ACCOUNT.md) · [`ODEI_DEX_TRADING_SHELL.md`](ODEI_DEX_TRADING_SHELL.md) · [`ODEI_EXCHANGE_CUSTODIAL_SHELL.md`](ODEI_EXCHANGE_CUSTODIAL_SHELL.md) · Roles: [`PRODUCTION_ROLES.md`](PRODUCTION_ROLES.md)
