'use strict';
// Exercise the installed browser, rather than treating a downloaded file as ready.
const path = require('path');
const { createRequire } = require('module');
const root = path.resolve(__dirname, '..');
const whiteboard = createRequire(path.join(root, 'apps/simon-skills/skills/whiteboard-video/package.json'));
(async () => {
  whiteboard('roughjs');
  whiteboard('lz-string');
  const browser = await whiteboard('playwright').chromium.launch();
  try {
    const page = await browser.newPage();
    await page.setContent('<title>Studio renderer check</title>');
    if (await page.title() !== 'Studio renderer check') throw new Error('Browser page check failed');
    console.log(JSON.stringify({ ready: true, node: process.version, chromium: browser.version() }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
