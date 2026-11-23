import {defineConfig, loadEnv} from "vite";
import react from "@vitejs/plugin-react";

// Read deployment-time VITE_* values without depending on Node ambient types.
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    base: env.VITE_BASE_PATH ?? "/",
    plugins: [react()],
  };
});
