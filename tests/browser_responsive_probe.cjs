// Browser regression only: generated test HTML, no live account/session.
const fs = require('node:fs');
const { chromium } = require(process.env.WECHAT_TEST_PLAYWRIGHT || 'playwright');
const measure = require('../scripts/measure_wechat_viewport.js');
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const browser = await chromium.launch({headless: true, ...(process.env.WECHAT_TEST_BROWSER_CHANNEL ? {channel: process.env.WECHAT_TEST_BROWSER_CHANNEL} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1200, height: 900}});
    await page.setContent(input.html);
    const samples = [];
    for (const width of [320, 390, 430]) {
      await page.locator('#fixture').evaluate((root, width) => { root.style.width = width + 'px'; }, width);
      samples.push(await page.locator('#fixture').evaluate(measure));
    }
    process.stdout.write(JSON.stringify(samples));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
