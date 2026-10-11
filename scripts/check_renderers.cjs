'use strict';
// Exercise the installed browser, rather than treating a downloaded file as ready.
const path = require('path');
const fs = require('fs');
const { createRequire } = require('module');
const root = path.resolve(__dirname, '..');
const whiteboard = createRequire(path.join(root, 'apps/simon-skills/skills/whiteboard-video/package.json'));
(async () => {
  if (!process.argv.includes('--animation')) {
    whiteboard('roughjs');
    whiteboard('lz-string');
  }
  const chromium = whiteboard('playwright').chromium;
  const executable = chromium.executablePath();
  if (!fs.existsSync(executable)) throw new Error('Chromium is missing; check installation or antivirus quarantine.');
  if (process.argv.includes('--inspect')) {
    console.log(JSON.stringify({ready: true, node: process.version, executable}));
    return;
  }
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.setContent('<title>Studio renderer check</title>');
    if (await page.title() !== 'Studio renderer check') throw new Error('Browser page check failed');
    console.log(JSON.stringify({ ready: true, node: process.version, chromium: browser.version() }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
