# NEXUS local chat UI testing mode

When the browser build does not contain a complete ODID/API configuration, the NEXUS panel opens a local-only demo chat so the composer and transcript can be exercised without identity-provider setup.

## Safety boundary

- The demo creates no user identity, access token, refresh token, organization, project or authenticated session.
- Messages and fixture replies exist only in React component memory and disappear on reload or when the demo is exited.
- Demo submission does not call the NEXUS API, an AI provider, a model gateway, the local companion, or any external service.
- Ask mode returns a static UI fixture. Plan, Agent and Debug modes explicitly state that real planning, file inspection, tools and command execution are unavailable in demo mode.
- File attachment controls and task planning are unavailable in demo mode. Authenticated workspace, patch and execution capabilities remain behind the existing ODID and server authorization gates.
- The demo banner identifies this as a local UI test. It must never be presented as a connected AI assistant or as proof that backend chat is operational.

## Enabling real NEXUS

Configure all six public browser settings for the target environment: `VITE_ODID_ISSUER`, `VITE_ODID_CLIENT_ID`, `VITE_ODID_REDIRECT_URI`, `VITE_ODID_API_RESOURCE`, `VITE_ODID_SCOPES`, and `VITE_ODEI_API_BASE_URL`. The API must independently be configured with its trusted issuer, audience, JWKS endpoint, allowed client IDs, tenant membership store, and model-provider integration. Do not bypass server authentication to make the browser composer appear connected.

## Verification scope

Unit tests cover the static fixture text for Ask, Plan, Agent and Debug modes. Browser-level end-to-end testing is still required to verify that no network requests occur during local demo submission and that authenticated mode continues to use the existing ODID flow.
