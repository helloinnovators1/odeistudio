import { expect, test } from "@playwright/test";

test("ODEI Studio Window is the first screen and opens the workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("ODEI Studio Window");
  await expect(page.getByRole("region", { name: "ODEI Studio Window" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What are we building today?" })).toBeVisible();
  await page.getByRole("button", { name: "Automations" }).click();
  const automations = page.getByRole("dialog", { name: "Automations" });
  await expect(automations).toBeVisible();
  await expect(automations).toContainText("Live scheduling and background execution require the automation service to be configured.");
  await automations.getByLabel("Automation name").fill("Review open pull requests");
  await automations.getByRole("button", { name: "Save automation draft" }).click();
  await expect(page.getByRole("status")).toContainText("Automation draft saved locally; live scheduling is not configured.");
  await automations.getByRole("button").first().click();
  const popupPromise = page.context().waitForEvent("page");
  await page.getByRole("button", { name: "Open IDE in independent window" }).click();
  const ide = await popupPromise;
  await ide.waitForLoadState("domcontentloaded");
  await expect(ide.locator(".ide-titlebar")).toBeVisible();
  const panel = ide.locator('aside[aria-label="NEXUS AI chat panel"]');
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("button", { name: "Exit demo" })).toBeVisible();
  await expect(panel.getByRole("textbox", { name: "NEXUS message" })).toBeVisible();
  await expect(panel).toContainText("Local UI test · no API calls");
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

test("NEXUS opens a local-only chat harness without calling authenticated services", async ({ page }) => {
  const apiRequests: string[] = [];
  await page.goto("/");
  await page.locator(".studio-quick-actions button").nth(1).click();
  // The Multitask quick action already opens NEXUS; do not toggle it closed again.

  const panel = page.getByRole("complementary", { name: "NEXUS AI chat panel" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("button", { name: "Exit demo" })).toBeVisible();
  await expect(panel).toContainText("Local UI test · no API calls");
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.includes("/api/")) apiRequests.push(request.url());
  });

  const consent = panel.getByRole("checkbox", { name: /local UI test/i });
  await consent.check();
  await expect(consent).toBeChecked();
  // The Multitask launcher opens NEXUS in Plan mode; select Ask so this test
  // verifies the local chat fixture rather than the intentionally disabled planner.
  await panel.getByRole("combobox", { name: "NEXUS mode" }).selectOption("ask");
  const composer = panel.getByRole("textbox", { name: "NEXUS message" });
  await expect(composer).toBeEnabled();
  await composer.fill("Test the local NEXUS chat");
  const send = panel.getByRole("button", { name: "Send" });
  await expect(send).toBeEnabled();
  await send.click();
  await expect(panel).toContainText("Test the local NEXUS chat");
  await expect(panel).toContainText("Local chat interface test completed.");
  expect(apiRequests).toEqual([]);
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


test("ODEI title bar exposes IDE, app launcher, overflow menu and window controls", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Open IDE in independent window" })).toBeVisible();
  const apps = page.getByRole("button", { name: "Show apps" });
  await apps.click();
  await expect(page.getByRole("dialog", { name: "Apps" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Apps" }).getByRole("button", { name: /NEXUS/ })).toBeVisible();
  await apps.click();
  const more = page.getByRole("button", { name: "More options" });
  await more.click();
  await expect(page.getByRole("menu", { name: "IDE options" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Minimize window" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Maximize window" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Close ODEI Studio" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Minimize ODEI Studio" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Maximize ODEI Studio" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Close ODEI Studio" })).toBeVisible();
});


test("IDE opens the full workbench in a separate independent window", async ({ page, context }) => {
  await page.goto("/");
  const popupPromise = context.waitForEvent("page");
  await page.getByRole("button", { name: "Open IDE in independent window" }).click();
  const ideWindow = await popupPromise;
  await ideWindow.waitForLoadState("domcontentloaded");
  await expect(ideWindow).toHaveURL(/window=ide/);
  await expect(ideWindow.locator(".ide-titlebar")).toBeVisible();
  await expect(ideWindow.locator(".explorer-pane")).toBeVisible();
  await expect(ideWindow.locator(".editor-column")).toBeVisible();
  await expect(ideWindow.getByRole("complementary", { name: "NEXUS AI chat panel" })).toBeVisible();
  await expect(page.getByRole("region", { name: "ODEI Studio Window" })).toBeVisible();
  await ideWindow.close();
});


test("all application menus expose actionable commands and Help opens shortcuts", async ({ page }) => {
  await page.goto("/");
  for (const menu of ["File", "Edit", "Selection", "View", "Go", "Run", "Terminal", "Help"]) {
    await page.getByRole("button", { name: menu, exact: true }).click();
    await expect(page.getByRole("menu", { name: `${menu} menu` })).toBeVisible();
    await expect(page.getByRole("menuitem").first()).toBeVisible();
    await page.getByRole("button", { name: menu, exact: true }).click();
  }
  await page.getByRole("button", { name: "Help", exact: true }).click();
  await page.getByRole("menuitem", { name: "Keyboard Shortcuts" }).click();
  await expect(page.getByRole("dialog", { name: "KEYBOARD SHORTCUTS" })).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();
});


test("IDE workbench activity rail controls open their matching panels", async ({ page }) => {
  await page.goto("/?window=ide");
  await expect(page.locator(".ide-titlebar")).toBeVisible();
  await page.locator('.activity-rail button[aria-label="Search workspace files"]').click();
  await expect(page.locator('.ide-explorer-toolbar button[aria-label="Search view"]')).toHaveAttribute("aria-pressed", "true");
  await page.locator('.activity-rail button[aria-label="Source control status"]').click();
  await expect(page.locator('.ide-explorer-toolbar button[aria-label="Source Control view"]')).toHaveAttribute("aria-pressed", "true");
  await page.locator('.activity-rail button[aria-label="Open Agents and NEXUS"]').click();
  await expect(page.getByRole("complementary", { name: "NEXUS AI chat panel" })).toBeVisible();
});

test("reference IDE browser tab supports navigation, history, reload and external open", async ({ page }) => {
  await page.goto("/?window=ide");
  await expect(page.getByRole("tab", { name: "◎ Browser Tab" })).toBeVisible();
  await page.getByRole("textbox", { name: "Browser address" }).fill("https://example.com");
  await page.getByRole("button", { name: "Navigate browser" }).click();
  await expect(page.locator(".browser-frame")).toHaveAttribute("src", "https://example.com/");
  await expect(page.getByRole("button", { name: "Browser back" })).toBeEnabled();
  await page.getByRole("button", { name: "Browser back" }).click();
  await expect(page.locator(".browser-frame")).toHaveAttribute("src", "http://127.0.0.1:3003");
  await page.getByRole("button", { name: "Reload browser" }).click();
  await page.getByRole("button", { name: "Browser developer tools information" }).click();
  await expect(page.locator(".browser-tools-note")).toContainText("Press F12");
  await expect(page.getByRole("button", { name: "Minimize IDE window" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Maximize IDE window" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Close IDE window" })).toBeVisible();
  await page.getByRole("button", { name: "Minimize IDE window" }).click();
  await expect(page.getByText("OIPTECH Core is minimized")).toBeVisible();
  await page.getByRole("button", { name: "Restore window" }).click();
  await expect(page.getByRole("tab", { name: "◎ Browser Tab" })).toBeVisible();
});

test("OIPTECH Core Explorer view toolbar switches views and offers working guidance", async ({ page }) => {
  await page.goto("/?window=ide");
  await page.getByRole("button", { name: "Source Control view" }).click();
  await expect(page.getByText("Actual Git status, staging, diffs and commits require the native ODEI desktop host.")).toBeVisible();
  await page.getByRole("button", { name: "Extensions view" }).click();
  await expect(page.getByText("Extensions are not installed into this browser workspace.")).toBeVisible();
  await page.getByRole("button", { name: "Explorer view", exact: true }).click();
  await expect(page.getByText("Connect the companion to see your selected folders.")).toBeVisible();
  await page.getByRole("button", { name: "Terminal", exact: true }).click();
  await page.getByRole("menuitem", { name: "Show Terminal Panel" }).click();
  await expect(page.getByRole("button", { name: "Open NEXUS execution console" })).toBeVisible();
});


test("compact workspace navigation switches focused surfaces without stacking panels", async ({ page }) => {
  for (const width of [320, 360, 390, 768, 900]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/?window=ide");
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
    const dimensions = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth }));
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  }
});

test("NEXUS shortcut toggles the panel and mobile focus view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/?window=ide");
  await page.keyboard.press("Control+i");
  await expect(page.locator(".workbench")).toHaveClass(/mobile-nexus/);
  await expect(page.locator('aside[aria-label="NEXUS AI chat panel"]')).toBeVisible();
  await page.keyboard.press("Control+i");
  await expect(page.locator(".workbench")).toHaveClass(/mobile-editor/);
  await expect(page.locator('aside[aria-label="NEXUS AI chat panel"]')).toBeHidden();
});