#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID, createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import {validateProps} from './contract.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const require = createRequire(import.meta.url);
const HELP = `Investigation renderer (CPU, local assets)
node render.mjs video|still|cover|validate --props props.json --public-dir public --output output.mp4
  still: --frame 45                cover: --ratio 3:4|4:3
  --browser <chrome.exe> --concurrency 4 --scale 1 --gl swangle|angle --overwrite --with-audio
Times are integer frames at 30 fps; caption end is exclusive. Video is silent by default.
Cover produces an editorial layout, not an AI-generated image.`;

function parse(argv) {
  const [mode, ...args] = argv;
  if (!mode || ['--help', '-h'].includes(mode)) {console.log(HELP); process.exit(0);}
  if (!['video', 'still', 'cover', 'validate'].includes(mode)) throw new Error(`Unknown mode: ${mode}`);
  const options = {mode};
  const booleans = new Set(['overwrite', 'with-audio']);
  const values = new Set(['props', 'public-dir', 'output', 'frame', 'ratio', 'browser', 'concurrency', 'scale', 'gl']);
  for (let i = 0; i < args.length; i++) {
    const key = args[i].replace(/^--/, '');
    if (!args[i].startsWith('--')) throw new Error(`Expected option, got ${args[i]}`);
    if (booleans.has(key)) {options[key] = true; continue;}
    if (!values.has(key) || args[i+1] == null) throw new Error(`Unknown or incomplete option: --${key}`);
    options[key] = args[++i];
  }
  for (const key of ['props', 'public-dir', ...(mode === 'validate' ? [] : ['output'])]) {
    if (!options[key]) throw new Error(`Missing --${key}`);
  }
  return options;
}
function numeric(value, fallback, name, min, max, integral = false) {
  const n = value == null ? fallback : Number(value);
  if (!Number.isFinite(n) || n < min || n > max || (integral && !Number.isInteger(n))) throw new Error(`Invalid --${name}`);
  return n;
}
function browserPath(explicit) {
  if (explicit) return fs.realpathSync(explicit);
  const configured = process.env.INVESTIGATION_CHROME;
  if (configured) return fs.realpathSync(configured);
  process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.join(ROOT, 'cache/ms-playwright');
  try {
    const chromium = require(path.join(ROOT, 'apps/simon-skills/skills/whiteboard-video/node_modules/playwright')).chromium;
    const executable = chromium.executablePath();
    if (fs.existsSync(executable)) return executable;
  } catch { /* Try known cache directories below, never auto-download. */ }
  const cache = path.join(ROOT, 'cache/ms-playwright');
  if (fs.existsSync(cache)) for (const name of fs.readdirSync(cache).filter(n => /^chromium-\d+$/u.test(n)).reverse()) {
    const executable = path.join(cache, name, 'chrome-win64/chrome.exe');
    if (fs.existsSync(executable)) return executable;
  }
  throw new Error('No local Chromium found. Pass --browser; renderer will not download a browser automatically.');
}
function cleanupBundle(directory, cacheRoot) {
  const target = path.resolve(directory);
  if (target.startsWith(path.resolve(cacheRoot) + path.sep) && path.basename(target).startsWith('bundle-')) {
    fs.rmSync(target, {recursive: true, force: true});
  }
}

async function main() {
  const options = parse(process.argv.slice(2));
  const propsPath = fs.realpathSync(options.props);
  const publicDir = fs.realpathSync(options['public-dir']);
  const input = JSON.parse(fs.readFileSync(propsPath, 'utf8').replace(/^\uFEFF/u, ''));
  const props = validateProps(input, publicDir);
  props.withAudio = Boolean(options['with-audio']);
  props.coverRatio = options.ratio ?? '3:4';
  if (!['3:4', '4:3'].includes(props.coverRatio)) throw new Error('--ratio must be 3:4 or 4:3');
  if (props.withAudio && !props.narration) throw new Error('--with-audio requires narration');
  const scale = numeric(options.scale, 1, 'scale', .25, 2);
  const concurrency = numeric(options.concurrency, 4, 'concurrency', 1, 8, true);
  const gl = options.gl ?? 'swangle';
  if (!['swangle', 'angle'].includes(gl)) throw new Error('--gl must be swangle or angle');
  const frame = numeric(options.frame, 0, 'frame', 0, props.durationInFrames-1, true);
  const output = options.output ? path.resolve(options.output) : null;
  if (output && fs.existsSync(output) && !options.overwrite) throw new Error(`Output exists: ${output}; use --overwrite explicitly`);
  if (output) fs.mkdirSync(path.dirname(output), {recursive: true});
  const browserExecutable = browserPath(options.browser);
  const cacheRoot = path.join(HERE, '.cache');
  fs.mkdirSync(cacheRoot, {recursive: true});
  const bundleDir = fs.mkdtempSync(path.join(cacheRoot, 'bundle-'));
  const temporary = output ? path.join(path.dirname(output), `.${path.basename(output)}.${randomUUID()}.partial${options.mode === 'video' ? '.mp4' : '.png'}`) : null;
  const started = Date.now();
  try {
    console.log(JSON.stringify({stage: 'bundle', mode: options.mode, scenes: props.scenes.length}));
    const serveUrl = await bundle({entryPoint: path.join(HERE, 'src/index.jsx'), rootDir: HERE, publicDir,
      outDir: bundleDir, enableCaching: true, onSymlinkDetected: symlink => {throw new Error(`Public assets must be physical files: ${symlink}`);}});
    const bundledAt = Date.now();
    const shared = {serveUrl, browserExecutable, chromeMode: 'chrome-for-testing',
      chromiumOptions: {gl, headless: true}, timeoutInMilliseconds: 120000, logLevel: 'warn'};
    // Always select the film first: metadata checks every video duration, even
    // for a cover, so a cover cannot conceal an invalid movie project.
    const film = await selectComposition({...shared, id: 'Investigation', inputProps: props});
    if (options.mode === 'validate') {
      console.log(JSON.stringify({stage: 'validated', durationInFrames: film.durationInFrames, fps: film.fps}));
      return;
    }
    const composition = options.mode === 'cover'
      ? await selectComposition({...shared, id: 'InvestigationCover', inputProps: film.props}) : film;
    const renderingAt = Date.now();
    console.log(JSON.stringify({stage: 'render', frames: composition.durationInFrames,
      width: composition.width, height: composition.height}));
    if (options.mode === 'video') {
      let last = -1;
      await renderMedia({...shared, composition, inputProps: composition.props,
        outputLocation: temporary, codec: 'h264', crf: 18, x264Preset: 'fast', pixelFormat: 'yuv420p',
        hardwareAcceleration: 'disable', concurrency, scale, muted: !props.withAudio,
        onProgress: ({progress, renderedFrames}) => {
          const percent = Math.floor(progress*20)*5;
          if (percent !== last) {last = percent; console.log(JSON.stringify({stage: 'render', percent, renderedFrames}));}
        }});
    } else {
      await renderStill({...shared, composition, inputProps: composition.props, output: temporary,
        frame: options.mode === 'cover' ? 0 : frame, imageFormat: 'png', scale});
    }
    if (!fs.statSync(temporary).size) throw new Error('Renderer produced an empty output');
    fs.renameSync(temporary, output);
    const report = {renderer: 'investigation-renderer', remotion: '4.0.508', mode: options.mode,
      props: propsPath, propsSha256: createHash('sha256').update(fs.readFileSync(propsPath)).digest('hex'),
      publicDir, output, durationInFrames: composition.durationInFrames, fps: composition.fps,
      width: Math.round(composition.width*scale), height: Math.round(composition.height*scale),
      muted: !props.withAudio, cpuRendering: gl === 'swangle', gl, concurrency, browserExecutable,
      bundleSeconds: (bundledAt-started)/1000, setupSeconds: (renderingAt-bundledAt)/1000,
      renderSeconds: (Date.now()-renderingAt)/1000, elapsedSeconds: (Date.now()-started)/1000,
      coverKind: options.mode === 'cover' ? 'editorial-layout-not-ai-generated' : null};
    fs.writeFileSync(`${output}.render.json`, JSON.stringify(report, null, 2), 'utf8');
    console.log(JSON.stringify({stage: 'done', ...report}));
  } finally {
    if (temporary && fs.existsSync(temporary)) fs.rmSync(temporary, {force: true});
    cleanupBundle(bundleDir, cacheRoot);
  }
}
main().catch(error => {console.error(error.stack || error.message || error); process.exitCode = 1;});
