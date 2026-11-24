import {defineConfig, loadEnv} from "vite";
import react from "@vitejs/plugin-react";

// Vercel preview deployments are served from their own domain root. Production
// is mounted at /odeistudio on the Zuri OS host, so keep the two bases distinct.
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, ".", "VITE_");
  const runtime = globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  };
  const isVercelPreview = runtime.process?.env?.VERCEL_ENV === "preview";
  const configuredBase = isVercelPreview
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
