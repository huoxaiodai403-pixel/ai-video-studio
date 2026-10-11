import fs from 'node:fs';
import path from 'node:path';

const kinds = new Set(['video', 'image', 'evidence', 'diagram']);
const text = (value, name, maximum, fallback = '') => {
  if (value == null) return fallback;
  if (typeof value !== 'string' || value.length > maximum || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value)) {
    throw new Error(`${name} must be text of at most ${maximum} characters`);
  }
  return value;
};
const integer = (value, name, low, high) => {
  if (!Number.isSafeInteger(value) || value < low || value > high) {
    throw new Error(`${name} must be an integer in [${low}, ${high}]`);
  }
  return value;
};

export function localAsset(value, publicDir) {
  if (typeof value !== 'string' || !value || value.includes('\\') || /[:?#\x00]/u.test(value)
      || value.startsWith('/') || value.split('/').some(p => !p || p === '.' || p === '..')) {
    throw new Error('Media must be a plain relative path inside public-dir');
  }
  const root = fs.realpathSync(publicDir);
  const actual = fs.realpathSync(path.join(root, value));
  const relative = path.relative(root, actual);
  if (relative.startsWith(`..${path.sep}`) || relative === '..' || path.isAbsolute(relative)
      || !fs.statSync(actual).isFile()) throw new Error(`Media escapes public-dir: ${value}`);
  return value;
}

export function validateProps(input, publicDir) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Props must be an object');
  const fps = integer(input.fps ?? 30, 'fps', 30, 30);
  const width = integer(input.width ?? 1920, 'width', 640, 3840);
  const height = integer(input.height ?? 1080, 'height', 360, 2160);
  if (width % 2 || height % 2 || width * 9 !== height * 16) throw new Error('Video must use an even 16:9 canvas');
  const durationInFrames = integer(input.durationInFrames, 'durationInFrames', 1, 108000);
  if (!Array.isArray(input.scenes) || !input.scenes.length || input.scenes.length > 1200) throw new Error('Expected 1–1200 scenes');
  let cursor = 0;
  const ids = new Set();
  const scenes = input.scenes.map((scene, i) => {
    const id = text(scene.id, `scene ${i} id`, 80);
    if (!id || ids.has(id)) throw new Error('Scene IDs must be present and unique');
    ids.add(id);
    const startFrame = integer(scene.startFrame, `${id} startFrame`, 0, durationInFrames - 1);
    const frames = integer(scene.durationInFrames, `${id} durationInFrames`, 1, durationInFrames);
    if (startFrame !== cursor || startFrame + frames > durationInFrames) throw new Error(`${id}: scenes must cover a continuous, non-overlapping timeline`);
    cursor += frames;
    if (!kinds.has(scene.kind)) throw new Error(`${id}: unknown scene kind`);
    const points = scene.points ?? [];
    if (!Array.isArray(points) || points.length > 6) throw new Error(`${id}: at most six diagram points`);
    const normalizedPoints = points.map((point, j) => {
      if (typeof point !== 'string') return {title: text(point?.title, `${id} point ${j} title`, 60), text: text(point?.text, `${id} point ${j} text`, 180)};
      const value = text(point, `${id} point ${j}`, 100);
      const separator = value.search(/[｜|]/u);
      return separator < 0 ? {title: value, text: ''}
        : {title: value.slice(0, separator).trim(), text: value.slice(separator + 1).trim()};
    });
    if (normalizedPoints.some(point => !(point.title + point.text).trim())) throw new Error(`${id}: diagram points cannot be empty`);
    if (scene.kind === 'diagram' && !normalizedPoints.length && !scene.text?.trim()) throw new Error(`${id}: diagram needs explicit points or text`);
    const media = scene.media ? localAsset(scene.media, publicDir) : null;
    if (['video', 'image'].includes(scene.kind) && !media) throw new Error(`${id}: ${scene.kind} requires media`);
    if (scene.kind === 'evidence' && !media && !scene.text?.trim()) throw new Error(`${id}: evidence requires media or verbatim text`);
    const layout = scene.layout ?? 'auto';
    if (!['auto', 'full', 'collage', 'portrait'].includes(layout)) throw new Error(`${id}: unsupported layout`);
    // Accept the original prototype field, but new pipeline props use diagramLayout.
    const legacyDiagram = scene.diagramStyle === 'list' ? 'checklist' : scene.diagramStyle;
    const diagramLayout = scene.diagramLayout ?? legacyDiagram ?? 'flow';
    if (!['flow', 'compare', 'timeline', 'checklist'].includes(diagramLayout)) throw new Error(`${id}: unsupported diagramLayout`);
    return {id, startFrame, durationInFrames: frames, kind: scene.kind, media,
      mediaStart: integer(scene.mediaStart ?? 0, `${id} mediaStart`, 0, 1080000), layout, diagramLayout,
      heading: text(scene.heading, `${id} heading`, 100), text: text(scene.text, `${id} text`, 1200),
      badge: text(scene.badge, `${id} badge`, 80), points: normalizedPoints,
      sourceLabel: text(scene.sourceLabel, `${id} sourceLabel`, 160),
      sourceDate: text(scene.sourceDate, `${id} sourceDate`, 100), speaker: text(scene.speaker, `${id} speaker`, 80)};
  });
  if (cursor !== durationInFrames) throw new Error('Scene coverage does not equal durationInFrames');
  if (!Array.isArray(input.captions ?? []) || (input.captions ?? []).length > 10000) throw new Error('Invalid captions');
  let captionEnd = 0;
  const captions = (input.captions ?? []).map((caption, i) => {
    const start = integer(caption.start, `caption ${i} start`, 0, durationInFrames - 1);
    const end = integer(caption.end, `caption ${i} end`, 1, durationInFrames);
    if (start < captionEnd || end <= start) throw new Error('Captions must be ordered, non-overlapping, and non-empty');
    captionEnd = end;
    const cue = text(caption.text, `caption ${i} text`, 120).replace(/\s+/gu, ' ').trim();
    if (!cue) throw new Error(`caption ${i} text cannot be empty`);
    return {start, end, text: cue};
  });
  const accent = input.brand?.accent ?? '#10C46F';
  if (!/^#[0-9a-f]{6}$/iu.test(accent)) throw new Error('brand.accent must be #RRGGBB');
  return {title: text(input.title, 'title', 140), brand: {signature: text(input.brand?.signature, 'brand.signature', 36, 'AI Video'), accent},
    durationInFrames, fps, width, height, scenes, captions,
    narration: input.narration ? localAsset(input.narration, publicDir) : null,
    coverSubtitle: text(input.coverSubtitle, 'coverSubtitle', 120)};
}
