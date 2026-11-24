import { expect, test } from "@playwright/test";

const viewports = [
  { name: "mobile-320", width: 320, height: 800 },
  { name: "mobile-360", width: 360, height: 800 },
  { name: "mobile-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1024", width: 1024, height: 900 },
  { name: "desktop-1440", width: 1440, height: 1000 },
];

test("visible interactive controls have programmatic accessible names", async ({ page }) => {
  await page.goto("/");
  const unnamed = await page.locator(
    'button:visible, input:visible:not([type="hidden"]), textarea:visible, select:visible, [role="button"]:visible, [role="tab"]:visible, [role="menuitem"]:visible',
  ).evaluateAll((elements) => elements.filter((node) => {
    const element = node as HTMLElement & { labels?: NodeListOf<HTMLLabelElement> | null };
    const labelledBy = element.getAttribute("aria-labelledby");
    const referencedLabel = labelledBy
      ? labelledBy.split(/\\s+/).some((id) => Boolean(document.getElementById(id)?.textContent?.trim()))
      : false;
    const explicitLabel = element.getAttribute("aria-label")?.trim();
    const nativeLabels = element.labels && Array.from(element.labels).some((label) => label.textContent?.trim());
    const content = element.innerText?.trim();
    const title = element.getAttribute("title")?.trim();
    const placeholder = element.getAttribute("placeholder")?.trim();
    return !(explicitLabel || referencedLabel || nativeLabels || content || title || placeholder);
  }).map((element) => ({
    tag: element.tagName,
    role: element.getAttribute("role"),
    type: element.getAttribute("type"),
    id: element.id,
  })));
  expect(unnamed, JSON.stringify(unnamed)).toEqual([]);
});

test("dialogs expose an accessible name and modal state when opened", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open settings" }).click();
  const dialog = page.getByRole("dialog", { name: "WORKSPACE SETTINGS" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  const accessibleNameSource = await dialog.evaluate((element) => ({
    label: element.getAttribute("aria-label"),
    labelledBy: element.getAttribute("aria-labelledby"),
  }));
  expect(Boolean(accessibleNameSource.label || accessibleNameSource.labelledBy)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("responsive visual evidence has no horizontal overflow at supported breakpoints", async ({ page }, testInfo) => {
  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/");
    await expect(page.getByRole("region", { name: "ODEI Studio Window" })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
    }));
    expect(dimensions.document, `document overflow at ${viewport.name}: ${JSON.stringify(dimensions)}`)
      .toBeLessThanOrEqual(dimensions.viewport);
    expect(dimensions.body, `body overflow at ${viewport.name}: ${JSON.stringify(dimensions)}`)
      .toBeLessThanOrEqual(dimensions.viewport);
    await testInfo.attach(`odei-home-${viewport.name}`, {
      body: await page.screenshot({ fullPage: true, animations: "disabled" }),
      contentType: "image/png",
    });
  }
});

test("home screen has a coherent heading outline and no duplicate element IDs", async ({ page }) => {
  await page.goto("/");
  const structure = await page.evaluate(() => {
    const headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"))
      .filter((element) => element.getClientRects().length > 0)
      .map((element) => ({ level: Number(element.tagName.slice(1)), text: element.textContent?.trim() || "" }));
    const ids = Array.from(document.querySelectorAll("[id]")).map((element) => element.id);
    return {
      headings,
      duplicateIds: ids.filter((id, index) => ids.indexOf(id) !== index),
    };
  });
  expect(structure.headings.some((heading) => heading.level === 1 && heading.text.length > 0)).toBe(true);
  expect(structure.duplicateIds).toEqual([]);
  for (let index = 1; index < structure.headings.length; index += 1) {
    expect(
      structure.headings[index].level - structure.headings[index - 1].level,
      `heading hierarchy skips a level near "${structure.headings[index].text}"`,
    ).toBeLessThanOrEqual(1);
  }
});
