# ODEI Studio web workspace

Run `npm install` and `npm run dev` in this directory. The dev server binds to `127.0.0.1:3002`. Configure `ODEI_COMPANION_ALLOWED_ORIGINS` to the exact browser origin; never use wildcard origins.

The current workspace shell uses Monaco for read-only source inspection. It includes a local companion connection/pairing flow, project explorer, multiple open tabs, a bottom status/output surface and the NEXUS chat panel shell. Command+I (macOS) or Ctrl+I (Windows/Linux) toggles NEXUS chat. Settings lets the user choose Left or Right; the preference is stored locally in this browser and defaults to Right.

The NEXUS panel is currently a UI shell only. Authenticated chat, streaming, repository-aware tool execution, patch review and isolated command execution are not connected. The editor is read-only: no Save, file write, rename, delete or terminal execution is exposed. The companion remains loopback-only and read-only; it only lists and reads folders explicitly selected by the user. Pairing tokens remain in memory and are revoked on disconnect where possible. Project files are not uploaded to a cloud model by this UI.

ODID tenant authorization and the complete MAC/MAD administration experience remain future work. This shell is not a native Code-OSS/Electron desktop IDE, and local scanning has not been validated on Windows 10 build 18362.
