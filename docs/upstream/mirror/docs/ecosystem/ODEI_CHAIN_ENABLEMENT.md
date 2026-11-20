> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_CHAIN_ENABLEMENT.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_CHAIN_ENABLEMENT.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Chain local enablement

ODEI Chain is enabled as an embedded OPMS PoA/BFT runtime for the local multi-ecosystem. It produces blocks, exposes JSON-RPC, and indexes into Chain OS on the same machine. It is **not** a public, decentralized, or production mainnet.

## Start locally

1. Copy `ODEI Pre-Sale Management System (OPMS)/backend/.env.example` to `.env` if no local environment exists.
2. Keep `ENVIRONMENT=local`, `ODEI_CHAIN_LIVE_ENABLED=true`, and `ODEI_CHAIN_ID=odei-local-1`.
3. From the repository root, start OPMS:

   ```powershell
   npm run dev:opms-api
   ```

4. In another terminal, start product sites if they are not already running:

   ```powershell
   npm run dev
   ```

The Chain website is at `http://localhost:5204`. Its Network, Validators, Explorers, Status pages and MAC query OPMS at `http://127.0.0.1:8002`. They show a degraded, explicit state if OPMS is unavailable.

## Verify

```powershell
Invoke-RestMethod http://127.0.0.1:8002/api/v1/odei-chain/status
Invoke-RestMethod http://127.0.0.1:8002/api/v1/chain-os/multi-chain-status
Invoke-RestMethod http://127.0.0.1:8002/api/v1/odei-chain/rpc
Invoke-RestMethod -Method Post http://127.0.0.1:8002/api/v1/odei-chain/rpc `
  -ContentType 'application/json' `
  -Body '{"jsonrpc":"2.0","id":1,"method":"odei_getStatus","params":[]}'
```

Useful public read endpoints:

- `GET /api/v1/odei-chain/status`
- `GET /api/v1/odei-chain/discovery`
- `GET /api/v1/odei-chain/rpc` for RPC method help
- `POST /api/v1/odei-chain/rpc` for JSON-RPC
- `GET /api/v1/chain-os/multi-chain-status`
- `GET /api/v1/chain-os/explorer/blocks?network=odei-chain`
- `GET /api/v1/chain-os/explorer/validators?network=odei-chain`

## Production caution

Do not carry the local `.env` values into production unchanged. The runtime has no claim of public-mainnet decentralization or production consensus hardening. Production requires an explicit deployment design, protected secrets, reviewed networking and validator operations, CORS restricted to deployed origins, and a conscious choice to enable the runtime.
