# NEXUS Project Discovery Transport

## Purpose

The browser client has a project-scoped NEXUS chat endpoint and a server-side project lifecycle API. This module supplies the typed browser transport for listing and creating projects after a trusted identity flow has provided an in-memory access token.

## Existing API contract

- List: `GET /api/v1/organizations/{organization_id}/projects`
- Create: `POST /api/v1/organizations/{organization_id}/projects`
- Both require the server's verified access token and active organization membership.
- Listing returns at most 100 active projects owned by or actively shared with the caller.
- Creating a project makes the authenticated creator its owner.
- The API applies tenant authorization and writes audit records; client-supplied role claims are not trusted.

## Browser transport guarantees

`apps/web/src/projects.ts` implements:

- HTTPS-only API origins, with HTTP permitted only for loopback development.
- URL credential, query and fragment rejection.
- Bearer token passed only in the Authorization header; no ambient cookies.
- `cache: no-store`, `credentials: omit`, and redirect rejection.
- Bounded identifiers, project name/description, response size and project count.
- Response contract validation, including organization binding, active status and duplicate project-ID rejection.
- Stable, sanitized error messages; provider response details are never reflected to the user.
- AbortSignal support for caller-controlled cancellation.

The module does not persist access tokens, discover organizations, implement OIDC login, or select a project in the UI. Those actions remain gated on the approved ODID issuer/discovery contract, public browser client ID, redirect URI, scopes and API audience. A caller must supply the authenticated organization ID and short-lived in-memory access token.

## Tests

`apps/web/src/projects.test.ts` covers authenticated listing, transport security, cross-organization response rejection, duplicate/oversized results, project creation, invalid inputs, sanitized authorization errors and malformed/oversized responses.

## Explicit limitations

This increment is a reusable API client, not an end-to-end sign-in or project-selection experience. It does not change API authorization, add roles, persist credentials, enable chat submission, or claim production readiness. The UI must not enable project-dependent chat until authentication, trusted organization discovery, consent and project selection are connected and verified.


## Organization discovery endpoint and browser selector — 2026-11-21

- Added `GET /api/v1/organizations` to list only active memberships for the verified identity, bounded to 100 and audited per returned organization.
- Added a strict typed browser transport and connected the NEXUS panel to organization discovery before project selection.
- This endpoint returns organization IDs and roles only; display names, invitations and membership administration remain separate concerns.
