import { expect, test } from "@playwright/test";

test("window minimize and restore controls preserve the ODEI home", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Minimize ODEI Studio" }).click();
  await expect(page.getByText("ODEI Studio is minimized")).toBeVisible();
  await page.getByRole("button", { name: "Restore ODEI Studio" }).click();
  await expect(page.getByRole("region", { name: "ODEI Studio Window" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What are we building today?" })).toBeVisible();
});

test("workspace context picker offers only real files and explains unavailable sources", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Add context" }).click();
  const picker = page.locator(".studio-context-picker");
  await expect(picker).toBeVisible();
  await expect(picker).toContainText("Connect the local companion and open a workspace");
  await expect(picker).toContainText("Terminal, Git and browser context are not connected");
  await expect(picker.getByRole("button")).toHaveCount(0);
});

test("automation draft clearly reports local-only persistence", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Automations/ }).click();
  const dialog = page.getByRole("dialog", { name: "Automations" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Automation name").fill("Review open pull requests");
  await dialog.getByLabel("Schedule").selectOption("Weekly");
  await dialog.getByRole("button", { name: "Save automation draft" }).click();
  await expect(page.getByRole("status")).toContainText("Automation draft saved locally");
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("odei-automation-drafts") || "[]"));
  expect(saved).toContain("Review open pull requests · Weekly");
});

test("GitHub connection never implies an unconfigured integration is connected", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Connect GitHub/ }).click();
  const dialog = page.getByRole("dialog", { name: "Connect GitHub" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("has not supplied that connection");
  await expect(dialog).toContainText("no repository permissions are requested");
});

test("composer exposes all four explicit interaction modes", async ({ page }) => {
  await page.goto("/");
  const mode = page.getByRole("combobox", { name: "Agent mode" });
  await expect(mode).toBeVisible();
  await expect(mode.locator("option")).toHaveText(["Ask", "Plan", "Build", "Debug"]);
  await mode.selectOption("plan");
  await expect(mode).toHaveValue("plan");
  await mode.selectOption("agent");
  await expect(mode).toHaveValue("agent");
  await mode.selectOption("debug");
  await expect(mode).toHaveValue("debug");
});


test("home dialogs trap keyboard focus and restore it when dismissed", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: /Automations/ });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Automations" });
  const close = dialog.getByRole("button", { name: "Close automations" });
  await expect(dialog).toBeVisible();
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Save automation draft" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});
