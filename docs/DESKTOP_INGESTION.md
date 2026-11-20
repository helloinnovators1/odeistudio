# Desktop Project Ingestion — Safe Local Folder Scanning

## Goal

Let a user authorize ODEI Studio to inspect selected local project folders without manually packaging the folders into ZIP files. Access must be explicit, read-only by default, bounded, revocable and visible to the user.

A normal browser page or the ChatGPT Chrome extension cannot silently enumerate arbitrary Windows folders. The local companion described here is a separate ODEI Studio component; it does not grant this ChatGPT conversation access to the user's computer.

## Implemented scanner foundation

- The project-files service lists eligible files, reads bounded UTF-8 text and performs literal search.
- Windows file reads and recursive enumeration use native handle-relative operations. Enumeration uses GetFileInformationByHandleEx(FileIdBothDirectoryInfo); child directories are opened relative to held parent handles, and reparse points are rejected/skipped.
- POSIX listing uses os.fwalk with descriptor-relative metadata/open operations, O_NOFOLLOW and O_NONBLOCK. .gitignore files are read relative to the active directory descriptor.
- Both paths enforce path traversal checks, regular-file checks, common secret/dependency exclusions, root/nested .gitignore, maximum file counts and aggregate byte budgets.
- WorkspaceHandleRegistry retains the selected root OS handle/descriptor, performs list/read relative to that retained root, serializes operations and supports revocation/close. Tests verify that replacing the visible path after registration does not redirect the retained handle.

## Local companion prototype

The API package provides an odei-companion console command. It is a developer prototype, not a finished desktop product.

Current behavior:
1. Checks that ODEI_COMPANION_ALLOWED_ORIGINS contains at least one exact trusted ODEI Studio web origin.
2. Opens an OS folder-selection dialog.
3. Registers the selected root in WorkspaceHandleRegistry.
4. Prints a one-time pairing code in the local console.
5. Starts a FastAPI service bound to 127.0.0.1 only (default port 8765).
6. Allows a browser client from an exact configured Origin to exchange the pairing code for a one-hour read-only bearer session.
7. Serves a bounded file manifest and individual bounded UTF-8 file reads; supports session revocation. The workspace listing returns each selected folder's basename only, never its absolute path.
8. Closes the retained root handle when the companion exits.

### Developer setup

From a Python 3.10+ environment with Tk support:

    cd apps/api
    python -m pip install .
    $env:ODEI_COMPANION_ALLOWED_ORIGINS = "https://YOUR-ODEI-STUDIO-ORIGIN"
    odei-companion

Replace the placeholder with the exact ODEI Studio frontend origin (scheme and host only; no path or wildcard). ODEI_COMPANION_PORT can override the default port. The companion listens on 127.0.0.1, not the LAN. The folder picker can be repeated in one companion process: after each selection, the console asks whether another project folder should be selected. This supports separate roots such as the ODEI Studio project and the Cursor product interface gallery. The pairing code appears in the local console, expires after five minutes and must not be shared.

An initial frontend pairing client is now available in `apps/web`. It requests Chrome loopback-network permission only after a user click, exchanges the one-time code, keeps the bearer token in memory, lists selected workspace labels and reads individual files. It is read-only and does not yet provide editing, ODID identity binding, tenant ownership or audit history.

## Chrome Local Network Access (LNA) requirements

For a public ODEI Studio HTTPS origin connecting to http://127.0.0.1:8765, Chrome's current protection is the Local Network Access permission model. Chrome 142 introduced the LNA permission prompt; Chrome 145 added the granular loopback-network permission. The user's reported Chrome 157 version is in this newer model.

The future frontend must:
- Be served from a secure HTTPS origin.
- Explain why loopback access is needed.
- Query navigator.permissions for loopback-network where supported.
- If permission is prompt, initiate the first request only from a clear user gesture (for example, clicking “Connect local companion”); never trigger it automatically on page load or from a service worker.
- If permission is denied, show instructions for the browser's site settings.
- Use targetAddressSpace: "loopback" in the request so Chrome can apply address-space and mixed-content checks.
- Handle permission and connection errors without trying to bypass browser controls.

Illustrative frontend code (the function must be called from a user-click handler):

    async function connectLocalCompanionFromUserClick() {
      let permission = "prompt";
      try {
        const status = await navigator.permissions.query({
          name: "loopback-network"
        });
        permission = status.state;
      } catch {
        // Browser does not expose this permission name; still require a user click.
      }

      if (permission === "denied") {
        throw new Error("Allow loopback access for this site in browser settings.");
      }

      const request = new Request("http://127.0.0.1:8765/health", {
        method: "GET",
        mode: "cors",
        targetAddressSpace: "loopback"
      });
      const response = await fetch(request);
      if (!response.ok) throw new Error("Local companion is unavailable.");
      return response.json();
    }

The companion enforces standard CORS and exact server-side Origin/Host checks. Do not rely on the deprecated Private Network Access preflight header Access-Control-Allow-Private-Network; Chrome LNA is a browser permission gate, not a server-side authorization substitute.

## Local companion API

The local API is separate from the cloud /api/v1 API:

| Method | Route | Purpose |
|---|---|---|
| GET | /health | Local process health only |
| POST | /v1/pair | Exchange one-time pairing code for read-only bearer session |
| GET | /v1/workspaces | Return selected workspace IDs and folder-basename labels only (never absolute paths) |
| GET | /v1/workspaces/{id}/files | Return one selected root's bounded relative path/size manifest |
| GET | /v1/workspaces/{id}/file?path=... | Return one bounded UTF-8 text file from that root |
| GET | /v1/workspace, /v1/workspace/files, /v1/workspace/file | Single-root compatibility routes; return 409 when multiple roots are selected |
| POST | /v1/session/revoke | Revoke the current bearer session |

The service accepts only configured exact browser origins and expected loopback Host headers. Pairing codes are one-time and expire after five minutes; bearer sessions expire after one hour. Responses are marked non-cacheable. There is no write, shell, terminal, deployment or arbitrary root-registration HTTP route.

## Not yet complete / release gates

- Frontend pairing UI/client, user-gesture LNA permission flow and user-facing permission-denial guidance.
- ODID user/tenant binding for local sessions and workspace IDs.
- Explicit root consent/review UI, audit trail and pause/revoke controls in the Studio UI.
- Signed Windows installer, update/uninstall lifecycle and startup UX.
- Validate the native picker-to-handle boundary and run tests on the user's exact Windows 10 build 18362; current Windows CI uses windows-latest, not that historical OS build.
- Add resource/rate limits and operational audit for repeated local reads.
- Connect approved file previews to the NEXUS context pipeline only after the user explicitly approves what may be sent to a model/cloud service.

No local Desktop folders have been scanned by this development session. The prototype does not give ChatGPT's Chrome extension arbitrary filesystem access.
