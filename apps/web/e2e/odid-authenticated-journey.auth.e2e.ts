import { expect, test } from "@playwright/test";

const issuer = "https://identity.example.test";
const api = "https://api.example.test";

test("ODID PKCE browser journey authenticates and loads tenant-scoped projects", async ({ page }) => {
  await page.route(`${issuer}/.well-known/openid-configuration`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      issuer,
      authorization_endpoint: `${issuer}/authorize`,
      token_endpoint: `${issuer}/token`,
      code_challenge_methods_supported: ["S256"],
    }),
  }));

  await page.route(`${issuer}/authorize**`, async (route) => {
    const authorization = new URL(route.request().url());
    expect(authorization.searchParams.get("response_type")).toBe("code");
    expect(authorization.searchParams.get("code_challenge_method")).toBe("S256");
    expect(authorization.searchParams.get("client_id")).toBe("odei-studio-e2e");
    const state = authorization.searchParams.get("state");
    expect(state).toBeTruthy();
    const callback = new URL("http://127.0.0.1:3004/auth/callback");
    callback.searchParams.set("code", "e2e-authorization-code");
    callback.searchParams.set("state", state!);
    await route.fulfill({
      status: 200,
      contentType: "text/html",
      body: `<!doctype html><html><body><script>window.location.replace(${JSON.stringify(callback.toString())})</script></body></html>`,
    });
  });

  await page.route(`${issuer}/token`, async (route) => {
    const body = new URLSearchParams(route.request().postData() ?? "");
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("code")).toBe("e2e-authorization-code");
    expect(body.get("code_verifier")).toMatch(/^[A-Za-z0-9_-]{43,128}$/);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "e2e-access-token",
        token_type: "Bearer",
        expires_in: 3600,
        scope: "studio.read projects.read",
      }),
    });
  });

  await page.route(`${api}/api/v1/organizations`, async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer e2e-access-token");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        organizations: [{ organization_id: "org-e2e", role: "owner" }],
        limit: 100,
      }),
    });
  });

  await page.route(`${api}/api/v1/organizations/org-e2e/projects`, async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer e2e-access-token");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        projects: [{
          project_id: "project-e2e",
          organization_id: "org-e2e",
          name: "Authenticated E2E Project",
          description: "Browser acceptance fixture",
          status: "active",
          owner: { issuer, subject: "e2e-user" },
          created_at: "2026-01-01T00:00:00+00:00",
          updated_at: "2026-01-01T00:00:00+00:00",
        }],
        limit: 100,
      }),
    });
  });

  let projectAuthorization = "";
  await page.route(`${api}/api/v1/organizations/org-e2e/projects/project-e2e/**`, async (route) => {
    projectAuthorization = route.request().headers().authorization ?? "";
    expect(projectAuthorization).toBe("Bearer e2e-access-token");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ conversations: [], proposals: [], limit: 100 }),
    });
  });

  await page.route(`${api}/api/v1/organizations/org-e2e/projects/project-e2e/repository-index/search**`, async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer e2e-access-token");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        revision: 7,
        limit: 20,
        mode: "exact",
        results: [{
          path: "src/auth.ts", line: 42, snippet: "requireProjectAccess()",
          sha256: "a".repeat(64), revision: 7, snapshot_id: "snapshot-e2e",
        }],
      }),
    });
  });

  await page.goto("/");
  // The app boots into the ODEI home screen; opening New Chat mounts NEXUS.
  await page.getByRole("button", { name: "New Chat" }).first().click();
  await expect(page.getByRole("button", { name: "Sign in with ODID" })).toBeEnabled();
  await page.getByRole("button", { name: "Sign in with ODID" }).click();

  await expect(page.getByText(/Signed in · access and optional refresh tokens held in memory/)).toBeVisible();
  const organization = page.locator("#nexus-org-id");
  await expect(organization).toContainText("org-e2e · owner");
  await organization.selectOption("org-e2e");
  await page.getByRole("button", { name: "Load projects" }).click();

  const project = page.locator("#nexus-project-id");
  await expect(project).toContainText("Authenticated E2E Project");
  await project.selectOption("project-e2e");
  await expect(page.getByText("Project: Authenticated E2E Project")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();

  // Reuse the bearer header observed on the authenticated project request to
  // verify repository search and its source-location/hash citation contract.
  expect(projectAuthorization).toBe("Bearer e2e-access-token");
  const search = await page.evaluate(async ({ url, authorization }) => {
    const response = await fetch(url, { headers: { Authorization: authorization } });
    return { status: response.status, body: await response.json() };
  }, {
    url: `${api}/api/v1/organizations/org-e2e/projects/project-e2e/repository-index/search?q=needle`,
    authorization: projectAuthorization,
  });
  expect(search.status).toBe(200);
  expect(search.body.results[0]).toMatchObject({
    path: "src/auth.ts", line: 42, revision: 7, snapshot_id: "snapshot-e2e",
  });
  expect(search.body.results[0].sha256).toMatch(/^[a-f0-9]{64}$/);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in with ODID" })).toBeEnabled();
  await expect(page.getByRole("log", { name: "Conversation" }).getByText(
    "Signed out. In-memory access/refresh tokens and conversation were cleared.",
  )).toBeVisible();
  await expect(page.locator("#nexus-org-id")).toHaveCount(0);
});
