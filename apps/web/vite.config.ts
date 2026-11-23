import {defineConfig, loadEnv} from "vite";
import react from "@vitejs/plugin-react";

// Read deployment-time VITE_* values without depending on Node ambient types.
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, ".", "VITE_");
  // Preview deployments use their own root origin; production remains under the Zurios host rewrite.
  const vercelEnvironment = (globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  }).process?.env?.VERCEL_ENV;
  const configuredBase = vercelEnvironment === "preview"
    ? "/"
    : env.VITE_BASE_PATH?.trim() || (mode === "production" ? "/odeistudio/" : "/");
  const base = configuredBase === "/"
    ? "/"
    : `/${configuredBase.split("/").filter(Boolean).join("/")}/`;

  return {
    base,
    plugins: [react()],
  };
});
