# ODEI Studio web workspace

Run `npm install` and `npm run dev` in this directory. The dev server binds to `127.0.0.1:3002`. Configure `ODEI_COMPANION_ALLOWED_ORIGINS` to the exact browser origin; never use wildcard origins.

## Current workspace

The React/TypeScript/Vite client uses Monaco for read-only source inspection. It includes a local companion connection/pairing flow, project explorer, multiple open tabs, a bottom status/output surface and the NEXUS chat panel. Command+I (macOS) or Ctrl+I (Windows/Linux) toggles NEXUS chat. Settings lets the user choose Left or Right; the preference is stored locally in this browser and defaults to Right.

The editor itself remains read-only: no direct Save, rename or delete action is exposed. An approved one-file proposal can be applied through the paired local companion only after project-owner approval, explicit local write opt-in, a fresh companion challenge and a valid short-lived API-signed capability. The companion independently rechecks the live file hash and reports whether directory-metadata durability was confirmed. This is not multi-file apply or rollback.

## NEXUS Chat

The panel is connected to the provider-neutral ODID Authorization Code + PKCE browser foundation, server-authorized organization/project selection, explicit per-request cloud consent, a working composer, streamed responses, cancellation, durable project-scoped conversation history and bounded read-only inspection of explicitly attached excerpts.

NEXUS can create persisted patch proposals and present diffs for project-owner approval. Read-only inspection tools can list/read/literal-search only the one-to-five excerpts attached by the user. They do not grant arbitrary workspace-root access or upload a full workspace automatically.

Actual ODID issuer/client/redirect/resource/scope configuration, production API issuer/JWKS/CORS settings, MongoDB deployment and model-provider credentials are environment prerequisites. The browser PKCE helper has not been validated against a real ODID staging issuer. The companion apply path has passed GitHub Windows/Ubuntu CI but has not been installed and tested on the user's Windows 10 build 18362 device.

## Explicit capability boundaries

| Capability | Current status |
|---|---|
| Local companion connect and one-time pairing | Implemented |
| Explicit workspace selection and bounded file listing/read/search | Implemented |
| Monaco source viewing | Implemented, read-only |
| Multiple open tabs | Implemented |
| NEXUS panel left/right preference and shortcut | Implemented |
| ODID PKCE browser foundation and callback | Implemented; real provider configuration/staging remains open |
| Authorized organization/project selection | Implemented |
| Composer, cloud consent and send interaction | Implemented |
| SSE streaming and browser cancellation | Implemented; upstream provider cancellation is best-effort |
| Durable owner-scoped conversation history | Implemented |
| Attached-excerpt NEXUS read-only tools | Implemented; no whole-workspace tools |
| Persisted patch proposals and owner decisions | Implemented |
| Signed one-file local companion apply | Implemented; explicit opt-in and matched signing configuration required |
| Multi-file atomic apply and durable rollback | Not implemented |
| Terminal, shell, isolated command/test execution | Not implemented |
| LSP diagnostics and test runner | Not connected |
| Agents Window, CLI, cloud/background agents | Not implemented |
| MAC/MAD execution and production deployment | Not implemented |

## Security and data handling

- Companion calls are loopback-only, origin/host checked and initiated by user action.
- Pairing credentials and API access tokens are held in memory; access tokens are not written to browser storage, cookies or URLs.
- The browser sends only explicitly attached bounded excerpts to NEXUS after affirmative cloud-model consent.
- The companion only accesses roots explicitly selected by the user. Local apply additionally requires the `patch:apply` capability, project-owner approval, a short-lived signed token, a fresh one-use challenge and a live base-hash match.
- No chat or companion route exposes shell execution or arbitrary network tools.
- Do not enable direct browser-side writes. Any future write capability must preserve handle-relative Windows and descriptor-relative POSIX protections, explicit review, authorization, audit and recovery.

## Remaining dependencies

1. Configure and staging-test the real ODID issuer/client/redirect/resource/scope and token lifecycle.
2. Configure production API issuer/JWKS/audience/client allowlist, CORS, MongoDB replica set and model credentials.
3. Install and validate the companion on the user's Windows 10 build 18362 environment; scan explicitly selected folders and test a real browser-to-companion apply flow.
4. Implement durable rollback/recovery and multi-file transactions.
5. Implement isolated command/test execution, then agent orchestration, CLI, background/cloud agents and MAC/MAD.
6. Complete production hosting, observability, backups, incident and deployment/rollback runbooks.
