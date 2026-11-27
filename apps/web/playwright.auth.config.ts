import { defineConfig, devices } from "@playwright/test";

// Set the test identity configuration in the Playwright process before the
// Vite server starts. Keeping this explicit also makes the values available
// when CI runners provide empty VITE_* placeholders in their environment.
const odidTestEnvironment = {
  VITE_ODID_ISSUER: "https://identity.example.test",
  VITE_ODID_CLIENT_ID: "odei-studio-e2e",
  VITE_ODID_REDIRECT_URI: "http://127.0.0.1:3004/auth/callback",
  VITE_ODID_API_RESOURCE: "https://api.example.test/",
  VITE_ODID_SCOPES: "studio.read projects.read",
  VITE_ODEI_API_BASE_URL: "https://api.example.test",
};
Object.assign(process.env, odidTestEnvironment);

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.auth.e2e.ts",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3004",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium-odid-auth", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npx vite --host 127.0.0.1 --port 3004 --strictPort",
    url: "http://127.0.0.1:3004",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { ...process.env, ...odidTestEnvironment },
  },
});
