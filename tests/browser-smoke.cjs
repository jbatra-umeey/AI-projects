// Start the Python server first; npm install; npm run test:browser.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await page.goto(process.env.AGENTLOOP_URL || "http://127.0.0.1:8080");
    await page.waitForSelector("#scenario option", { state: "attached" });
    await page.locator("#start").click();
    await page.locator("#play").click();
    await page.waitForFunction(
      () =>
        document.querySelector("#status").textContent === "awaiting approval",
    );
    assert.equal(await page.locator("#approval").isVisible(), true);
    await page.waitForFunction(() => !document.querySelector("#approve").disabled);
    await page.locator("#trace").evaluate((node) => { node.scrollTop = 0; });
    await page.screenshot({ path: "docs/dashboard.png", fullPage: true });
    await page.locator("#approve").click();
    await page.locator("#play").click();
    await page.waitForFunction(
      () => document.querySelector("#status").textContent === "completed",
    );
    assert.match(await page.locator("#result-summary").textContent(), /140.0%/);
    assert.equal(await page.locator(".check.fail").count(), 0);
    await page.waitForFunction(() => !document.querySelector("#start").disabled);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: "docs/dashboard-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1100 });
    const downloadEvent = page.waitForEvent("download");
    await page.locator("#export").click();
    const download = await downloadEvent;
    assert.match(download.suggestedFilename(), /^agentloop-.*\.json$/);
    await page.reload();
    await page.waitForFunction(
      () => document.querySelector("#status").textContent === "completed",
    );
    await page.locator("#start").click();
    await page.locator("#play").click();
    await page.waitForFunction(
      () =>
        document.querySelector("#status").textContent === "awaiting approval",
    );
    assert.ok(Number(await page.locator("#hint-count").textContent()) >= 1);
    await page.locator("#deny").click();
    await page.waitForFunction(
      () => document.querySelector("#status").textContent === "cancelled",
    );
    await page.locator("#scenario").selectOption("insufficient");
    await page.locator("#start").click();
    await page.locator("#play").click();
    await page.waitForFunction(
      () => document.querySelector("#status").textContent === "blocked",
    );
    assert.ok((await page.locator(".check.fail").count()) > 0);
    await page.locator("#scenario").selectOption("healthy");
    await page
      .locator("#goal")
      .fill('<img src=x onerror="window.injected=true">');
    await page.locator("#start").click();
    await page.locator("#play").click();
    await page.waitForFunction(
      () => document.querySelector("#status").textContent === "completed",
    );
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.deepEqual(errors, []);
    console.log(
      "Browser checks passed: approval, denial, evidence gate, memory, reload, export, XSS rendering, mobile layout.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
