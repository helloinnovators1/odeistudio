import { expect, test } from "@playwright/test";

test("ODEI Studio Window is the first screen and opens the workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("ODEI Studio Window");
  await expect(page.getByRole("region", { name: "ODEI Studio Window" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What are we building today?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Automations Coming soon" })).toBeDisabled();
  await page.locator(".studio-quick-actions button").nth(1).click();
  await expect(page.getByRole("heading", { name: "ODEI NEXUS Workspace" })).toBeVisible();
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
  await page.locator(".studio-quick-actions button").nth(1).click();
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
    await page.locator(".studio-quick-actions button").nth(1).click();
    await page.getByRole("button", { name: "NEXUS ⌘ / Ctrl + I" }).click();
    await expect(page.getByRole("complementary", { name: "NEXUS AI chat panel" })).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth,
    }));
    expect(dimensions.document, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(dimensions.viewport);
  }
});

test("settings dialog manages keyboard focus and restores its opener", async ({ page }) => {
  await page.goto("/");
  await page.locator(".studio-quick-actions button").nth(1).click();
  const opener = page.getByRole("button", { name: "Open settings" });
  await opener.focus();
  await page.keyboard.press("Enter");

  const dialog = page.getByRole("dialog", { name: "WORKSPACE SETTINGS" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close settings" })).toBeFocused();

  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Done" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Close settings" })).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});

test("all enabled top-level controls expose accessible names", async ({ page }) => {
  await page.goto("/");
  const unnamed = await page.locator("button:not([disabled])").evaluateAll((buttons) =>
    buttons.filter((button) => {
      const element = button as HTMLButtonElement;
      return !(
        element.getAttribute("aria-label")?.trim() ||
        element.getAttribute("aria-labelledby")?.trim() ||
        element.innerText.trim() ||
        element.getAttribute("title")?.trim()
      );
    }).length,
  );
  expect(unnamed).toBe(0);
});
