import { defineConfig, devices } from "@playwright/test";

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
    command: "npx vite --mode auth-test --host 127.0.0.1 --port 3004 --strictPort",
    url: "http://127.0.0.1:3004",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { ...process.env },
  },
});
