'use strict';
// A fixed worker. User JavaScript runs only inside an offline sandboxed Chromium
// page, never in Node, vm, eval, require, or a server-origin browser page.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { createRequire } = require('module');
const { spawn } = require('child_process');
const root = path.resolve(__dirname, '..');
const localRequire = createRequire(path.join(root, 'apps/simon-skills/skills/whiteboard-video/package.json'));

const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
  "img-src data: blob:; font-src data:; connect-src 'none'; media-src 'none'; " +
  "frame-src 'none'; child-src 'none'; worker-src 'none'; object-src 'none'; " +
  "base-uri 'none'; form-action 'none';";

function deadline(promise, ms, label) {
  let timer;
  return Promise.race([promise, new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out`)), ms);
  })]).finally(() => clearTimeout(timer));
}

function command(executable, args, options = {}) {
  const child = spawn(executable, args, { windowsHide: true, ...options });
  let stderr = '', stdout = '';
  child.stderr?.on('data', data => { stderr = (stderr + data).slice(-12000); });
  child.stdout?.on('data', data => { stdout = (stdout + data).slice(-12000); });
  const done = new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve({ stdout, stderr }) :
      reject(new Error(`FFmpeg exited ${code}: ${stderr.slice(-2500)}`)));
  });
  // Streaming failures may happen before the frame loop next awaits done.
  done.catch(() => {});
  child.stdin?.on('error', () => {});
  return { child, done };
}

async function main() {
  const requestPath = path.resolve(process.argv[2] || 'request.json');
  const work = path.dirname(requestPath);
  const spec = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
  if (![spec.width, spec.height, spec.fps, spec.frames].every(Number.isInteger) ||
      spec.frames < 1 || spec.frames > 1800 || spec.width < 256 || spec.height < 256 ||
      spec.width > 1920 || spec.height > 1920 || spec.width * spec.height > 2073600 ||
      spec.width % 2 || spec.height % 2 || spec.fps < 1 || spec.fps > 30 ||
      !['video.mp4', 'sample.mp4'].includes(spec.video)) throw new Error('Invalid worker request');
  const html = fs.readFileSync(path.join(work, 'scene.html'), 'utf8');
  if (Buffer.byteLength(html) > 2000000) throw new Error('HTML exceeds worker size limit');
  const { chromium } = localRequire('playwright');
  let browser, encoder;
  try {
    browser = await chromium.launch({ headless: true, chromiumSandbox: true, timeout: 20000,
      args: ['--disable-gpu', '--disable-webgl', '--disable-background-networking',
        '--disable-features=WebRtcHideLocalIpsWithMdns',
        '--force-webrtc-ip-handling-policy=disable_non_proxied_udp'] });
    const context = await browser.newContext({ viewport: { width: spec.width, height: spec.height },
      deviceScaleFactor: 1, offline: true, serviceWorkers: 'block', acceptDownloads: false,
      permissions: [], reducedMotion: 'reduce', colorScheme: 'light' });
    let blockedRequests = 0;
    await context.route('**/*', route => { blockedRequests++; return route.abort('blockedbyclient'); });
    if (context.routeWebSocket) await context.routeWebSocket(/.*/, socket => {
      blockedRequests++; socket.close();
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => {
      if (errors.length < 10) errors.push(`${error.name || 'Error'}: ${String(error.message).slice(0, 500)}`);
    });
    page.on('dialog', dialog => { errors.push('Dialogs are not supported'); dialog.dismiss().catch(() => {}); });
    context.on('page', popup => { if (popup !== page) popup.close().catch(() => {}); });
    // Install a deterministic clock and refuse background execution. The only
    // bridge is a page-local setter; no exposed function calls back into Node.
    await page.evaluate(() => {
      let time = 0;
      const policyErrors = [];
      document.addEventListener('securitypolicyviolation', event => {
        if (policyErrors.length < 10) policyErrors.push(event.violatedDirective);
      });
      Object.defineProperty(window, '__studioPolicyErrors', { get: () => [...policyErrors] });
      Object.defineProperty(window, '__studioSetTime', { value: value => { time = value; } });
      const NativeDate = Date;
      class FrameDate extends NativeDate {
        constructor(...args) { super(...(args.length ? args : [time * 1000])); }
        static now() { return time * 1000; }
      }
      Object.defineProperty(window, 'Date', { value: FrameDate, writable: false, configurable: false });
      Object.defineProperty(performance, 'now', { value: () => time * 1000 });
      Object.defineProperty(Math, 'random', { value: () => 0.5 });
      const denied = () => { throw new Error('Use renderFrame(timeSeconds); timers, network and workers are disabled'); };
      for (const name of ['setTimeout', 'setInterval', 'requestAnimationFrame', 'requestIdleCallback',
        'fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'Worker', 'SharedWorker',
        'RTCPeerConnection', 'webkitRTCPeerConnection', 'open', 'showOpenFilePicker',
        'showSaveFilePicker', 'showDirectoryPicker']) {
        Object.defineProperty(window, name, { value: denied, configurable: false, writable: false });
      }
      Object.defineProperty(navigator, 'sendBeacon', { value: denied });
    });
    const secureDocument = `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}">` +
      '<style>html,body{margin:0;padding:0;overflow:hidden}*,*::before,*::after{animation:none!important;transition:none!important}</style>' + html;
    await deadline(page.setContent(secureDocument, { waitUntil: 'load', timeout: 10000 }), 12000, 'HTML initialization');
    // Initialization syntax errors and forbidden timers can prevent assignment
    // of renderFrame. Report the real page exception before the missing-contract
    // check masks it. stderr is retained by the parent job's failure record.
    if (errors.length) throw new Error('Page script initialization failed: ' + errors.join('; '));
    await deadline(page.evaluate(async () => {
      if (typeof window.renderFrame !== 'function') throw new Error('Define window.renderFrame(timeSeconds)');
      if (document.querySelectorAll('*').length > 5000) throw new Error('Too many DOM elements');
      await document.fonts.ready;
      await Promise.all([...document.images].map(image => image.decode()));
    }), 8000, 'Asset loading');
    if (errors.length) throw new Error(errors.join('; '));
    const silent = path.join(work, 'silent.mp4');
    encoder = command(spec.ffmpeg, ['-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
      '-f', 'image2pipe', '-vcodec', 'png', '-framerate', String(spec.fps), '-i', 'pipe:0',
      '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-pix_fmt', 'yuv420p',
      '-threads', '2', '-movflags', '+faststart', silent], { stdio: ['pipe', 'ignore', 'pipe'] });
    const hashes = [];
    let coverSaved = false;
    for (let frame = 0; frame < spec.frames; frame++) {
      await deadline(page.evaluate(async t => {
        window.__studioSetTime(t);
        await window.renderFrame(t);
        if (document.querySelectorAll('*').length > 5000) throw new Error('Too many generated DOM elements');
        const pixels = [...document.querySelectorAll('canvas')].reduce((sum, canvas) => sum + canvas.width * canvas.height, 0);
        if (pixels > 16777216) throw new Error('Canvas allocation exceeds 16 megapixels');
        if (window.__studioPolicyErrors.length) throw new Error('Blocked external resource: ' + window.__studioPolicyErrors.join(', '));
        for (const svg of document.querySelectorAll('svg')) {
          svg.pauseAnimations(); svg.setCurrentTime(t);
        }
        for (const animation of document.getAnimations()) {
          if (animation.playState === 'running') throw new Error('Animations must be manually controlled by renderFrame');
        }
      }, frame / spec.fps), 4000, `Frame ${frame}`);
      if (errors.length) throw new Error(errors.join('; '));
      const png = await page.screenshot({ type: 'png', timeout: 8000, caret: 'hide' });
      if (frame === 0 || frame === Math.floor(spec.frames / 2) || frame === spec.frames - 1) {
        hashes.push({ frame, time: frame / spec.fps, sha256: crypto.createHash('sha256').update(png).digest('hex') });
      }
      if (!coverSaved && frame === Math.floor(spec.frames / 2)) {
        fs.writeFileSync(path.join(work, 'cover.png'), png); coverSaved = true;
      }
      await deadline(new Promise((resolve, reject) => encoder.child.stdin.write(png,
        error => error ? reject(error) : resolve())), 10000, 'Frame encoding');
    }
    encoder.child.stdin.end();
    await deadline(encoder.done, 30000, 'Video encoding');
    const output = path.join(work, spec.video);
    if (spec.audio_path) {
      const audio = path.resolve(spec.audio_path);
      if (path.dirname(audio) !== work || !path.basename(audio).startsWith('audio-input.')) throw new Error('Invalid audio staging path');
      // FFmpeg must decode an actual audio stream. An image/video masquerading
      // as audio, a corrupt file, or a URL playlist fails rather than disappearing.
      encoder = command(spec.ffmpeg, ['-hide_banner', '-loglevel', 'error', '-xerror', '-nostdin', '-y',
        '-i', silent, '-protocol_whitelist', 'file,pipe', '-i', audio,
        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-af', 'apad',
        '-t', String(spec.frames / spec.fps), '-c:a', 'aac', '-ar', '48000', '-ac', '2',
        '-movflags', '+faststart', output], { stdio: ['ignore', 'ignore', 'pipe'] });
      await deadline(encoder.done, 45000, 'Audio validation and mux');
    } else fs.renameSync(silent, output);
    encoder = command(spec.ffmpeg, ['-hide_banner', '-loglevel', 'error', '-xerror', '-nostdin',
      '-i', output, '-map', '0:v:0', ...(spec.audio_path ? ['-map', '0:a:0'] : []),
      '-progress', 'pipe:1', '-f', 'null', '-'], { stdio: ['ignore', 'pipe', 'pipe'] });
    const decoded = await deadline(encoder.done, 45000, 'Full media decode');
    const frameCounts = [...decoded.stdout.matchAll(/^frame=(\d+)\s*$/gm)].map(match => Number(match[1]));
    if (frameCounts.at(-1) !== spec.frames) throw new Error('Decoded frame count does not match request');
    if (blockedRequests) throw new Error('Document attempted an external request');
    fs.writeFileSync(path.join(work, 'worker-result.json'), JSON.stringify({
      frames: spec.frames, duration: spec.frames / spec.fps, decoded: true,
      explicit_frame_clock: true, networking: 'blocked', sandbox: 'chromium',
      audio_stream_decoded: Boolean(spec.audio_path), chromium: browser.version(),
      frame_samples: hashes, visual_review: 'pending', audio_review: spec.audio_path ? 'pending' : 'not_applicable'
    }, null, 2));
  } finally {
    if (encoder?.child && encoder.child.exitCode === null) encoder.child.kill();
    if (browser) await deadline(browser.close(), 5000, 'Browser shutdown').catch(() => {});
  }
}

main().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
