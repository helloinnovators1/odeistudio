ODEI Studio web workspace preview

Run npm install and npm run dev in this directory. The dev server binds to 127.0.0.1:3002. Configure ODEI_COMPANION_ALLOWED_ORIGINS to exactly http://127.0.0.1:3002 (or the exact origin you use). Never use wildcard origins.

The client initiates loopback access only after a user click, queries Chrome loopback-network permission when available, uses targetAddressSpace=loopback, stores the pairing token only in React memory, and requests revocation on disconnect. It only lists and reads files; it does not write, execute commands, deploy or upload project files to the cloud. ODID tenant authorization and full IDE editing remain future work.
