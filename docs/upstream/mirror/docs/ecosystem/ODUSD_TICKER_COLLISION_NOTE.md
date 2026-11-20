> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODUSD_TICKER_COLLISION_NOTE.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODUSD_TICKER_COLLISION_NOTE.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODUSD ticker note (2026-07-31)

ODEI’s product stablecoin ticker is **ODUSD** (display name **ODEI USD (ODUSD)**).

It was renamed from the earlier internal label **OUSD** to avoid collision with another company’s ticker that already uses OUSD. ODEI product surfaces (Exchange, Wallet, Pay, DEX, CoinCore, Membership, Earn, DeFi, and strategy docs) must use **ODUSD** only.

Browser local stores migrate legacy `OUSD` / `ousd` / `rail-ousd` keys to `ODUSD` / `odusd` / `rail-odusd` on load so existing simulation balances are preserved.
