import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

// Set VITE_BASE_PATH=/odeistudio/ for the production subpath mount.
// Local development and standalone previews continue to use the root path.
const base = process.env.VITE_BASE_PATH ?? "/";

export default defineConfig({
  base,
  plugins: [react()],
});
