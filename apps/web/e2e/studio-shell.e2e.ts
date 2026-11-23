import { expect, test } from "@playwright/test";

test("IDE shell opens the authenticated NEXUS entry state", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByText("ODEI STUDIO", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "NEXUS ⌘ / Ctrl + I" }).click();
  const panel = page.locator('aside[aria-label="NEXUS AI chat panel"]');
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("button", { name: "Sign in with ODID" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Sign in with ODID" })).toBeDisabled();
});

test("NEXUS keyboard shortcut opens the chat panel", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Control+i");
  await expect(page.locator('aside[aria-label="NEXUS AI chat panel"]')).toBeVisible();
  await page.keyboard.press("Control+i");
  await expect(page.locator('aside[aria-label="NEXUS AI chat panel"]')).toBeHidden();
});

test("the workspace shell has no horizontal overflow at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/");
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
});

test("NEXUS exposes a named panel and a safe unauthenticated configuration state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "NEXUS ⌘ / Ctrl + I" }).click();

  const panel = page.getByRole("complementary", { name: "NEXUS AI chat panel" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Connect NEXUS" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Sign in with ODID" })).toBeDisabled();
  await expect(panel.getByRole("status")).toContainText("Authentication is safely disabled");
});

test("workspace and NEXUS remain within common narrow and desktop viewports", async ({ page }) => {
  for (const width of [320, 360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await page.getByRole("button", { name: "NEXUS ⌘ / Ctrl + I" }).click();
    await expect(page.getByRole("complementary", { name: "NEXUS AI chat panel" })).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth,
    }));
    expect(dimensions.document, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(dimensions.viewport);
  }
});


test("compact workspace navigation switches between Explorer, Editor and NEXUS without stacking panels", async ({ page }) => {
  for (const width of [320, 360, 390, 768, 900]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Workspace views" });
    await expect(nav).toBeVisible();
    await nav.getByRole("button", { name: "Explorer" }).click();
    await expect(page.locator(".explorer-pane")).toBeVisible();
    await expect(page.locator(".editor-column")).toBeHidden();
    await nav.getByRole("button", { name: "Editor" }).click();
    await expect(page.locator(".editor-column")).toBeVisible();
    await expect(page.locator(".explorer-pane")).toBeHidden();
    await nav.getByRole("button", { name: "NEXUS" }).click();
    await expect(page.getByRole("complementary", { name: "NEXUS AI chat panel" })).toBeVisible();
    await expect(page.locator(".editor-column")).toBeHidden();
    const dimensions = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth, height: document.documentElement.clientHeight, bodyHeight: document.documentElement.scrollHeight }));
    expect(dimensions.document, "horizontal overflow at " + width + "px").toBeLessThanOrEqual(dimensions.viewport);
    expect(dimensions.bodyHeight, "unexpected document vertical overflow at " + width + "px").toBeLessThanOrEqual(dimensions.height);
  }
});

test("desktop keeps the full editor layout and hides compact navigation", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Workspace views" })).toBeHidden();
  await expect(page.locator(".explorer-pane")).toBeVisible();
  await expect(page.locator(".editor-column")).toBeVisible();
});
