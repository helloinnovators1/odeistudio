import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

// The production mount point is configured by the deployment environment.
// Keep previews and local development rooted at "/" unless explicitly overridden.
const base = process.env.VITE_BASE_PATH ?? "/";

export default defineConfig({
  base,
  plugins: [react()],
});
