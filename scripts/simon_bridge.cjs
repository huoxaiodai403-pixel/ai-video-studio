'use strict';

// Fixed, local bridge: narration and labels are JSON data, never executable JS.
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const SKILL = path.join(ROOT, 'apps', 'simon-skills', 'skills', 'whiteboard-video');

function units(text) {
  return [...text].reduce((n, char) => n + (/[^\x00-\xff]/u.test(char) ? 1 : 0.55), 0);
}

function wrap(text, width, size) {
  const max = width / size;
  const lines = [];
  for (const paragraph of String(text).split('\n')) {
    let line = '';
    for (const char of paragraph) {
      if (line && units(line + char) > max) { lines.push(line.trim()); line = ''; }
      line += char;
    }
    if (line.trim()) lines.push(line.trim());
  }
  return lines.join('\n');
}

function coverLines(text) {
  const title = text.replace(/\s+/g, '').trim();
  if (units(title) <= 8) return title;
  const chars = [...title];
  let best = 1, score = Infinity;
  for (let i = 1; i < chars.length; i++) {
    const left = units(chars.slice(0, i).join('')), right = units(chars.slice(i).join(''));
    const candidate = Math.abs(left - right) - (/[，。！？：；、,!?;:]/u.test(chars[i - 1]) && Math.min(left, right) >= 3 ? 4 : 0);
    if (candidate < score) { score = candidate; best = i; }
  }
  return chars.slice(0, best).join('').replace(/[，。！？：；、,!?;:]+$/u, '') + '\n' + chars.slice(best).join('');
}

function fit(s, x, y, text, width, height, options = {}) {
  let size = options.size || 48;
  let rendered = wrap(text, width, size);
  while (rendered.split('\n').length * size * 1.25 > height && size > 30) {
    size -= 2; rendered = wrap(text, width, size);
  }
  if (rendered.split('\n').length * size * 1.25 > height) {
    throw new Error(`白板文字过长，请缩短卡片：${String(text).slice(0, 40)}`);
  }
  return s.text(x, y, rendered, { ...options, size });
}

function build(projectDir) {
  const project = path.resolve(projectDir);
  process.env.SIMON_WB_CONFIG = path.join(project, 'simon-config.json');
  const { Scene, C, build: save } = require(path.join(SKILL, 'lib', 'scene-dsl')).use(project);
  const payload = JSON.parse(fs.readFileSync(path.join(project, 'simon-scenes.json'), 'utf8'));
  const colors = [C.brand, C.blue, C.orange];
  const fills = [C.fGreen, C.fBlue, C.fYellow];
  const scenes = [];

  payload.scenes.forEach((item, sceneIndex) => {
    if (!/^[A-Za-z0-9_-]{1,40}$/.test(item.id)) throw new Error('Unsafe scene id');
    const s = new Scene(item.id, item.beats.join('|'));
    const cards = item.cards;
    const cardBeat = cards.map((_, i) => Math.min(item.beats.length - 1, Math.floor(i * item.beats.length / cards.length)));
    const sticker = (i, cx, y, height) => {
      const name = (item.stickers || [])[i];
      if (!name) return false;
      if (!/^[A-Za-z0-9_-]{1,60}$/.test(name)) throw new Error('Unsafe sticker name');
      const file = path.join(project, 'assets', name + '.png');
      if (!fs.existsSync(file)) throw new Error(`缺少白板贴纸：${file}`);
      s.image(cx, y, name, { h: height, align: 'center' });
      return true;
    };
    for (let beat = 0; beat < item.beats.length; beat++) {
      s.nextBeat();
      if (beat === 0) {
        s.text(120, 66, String(sceneIndex + 1).padStart(2, '0'), { size: 38, color: C.gray });
        const heading = fit(s, 960, item.layout === 'opening' ? 135 : 145, item.title, 1420, 150,
          { size: item.layout === 'opening' ? 96 : 82, align: 'center', color: C.brand });
        const underlineY = heading.y + heading.height + 12;
        s.line([[450, underlineY], [960, underlineY + 10], [1470, underlineY]], { stroke: C.brand, strokeWidth: 6, roughness: 1.3 });
        if (item.layout === 'summary' && item.sticker) {
          s.image(1650, 470, item.sticker, { h: 270, align: 'center' });
        }
      }
      cards.forEach((text, i) => {
        if (cardBeat[i] !== beat) return;
        const n = cards.length;
        const cx = n === 1 ? 960 : n === 2 ? 510 + i * 900 : 360 + i * 600;
        const color = colors[i], fill = fills[i];
        if (item.layout === 'opening') {
          // Open composition: a numbered focal point, annotation and short accent line.
          s.ellipse(cx - 74, 405, 148, 148, { fill, stroke: color, strokeWidth: 3 });
          s.text(cx, 439, String(i + 1).padStart(2, '0'), { size: 58, color, align: 'center' });
          const hasSticker = sticker(i, cx, 568, 150);
          fit(s, cx, hasSticker ? 740 : 605, text, n === 3 ? 490 : 690, hasSticker ? 160 : 260,
            { size: 50, align: 'center' });
          if (i < n - 1) s.arrow([[cx + 120, 479], [cx + (n === 3 ? 480 : 780), 479]], { stroke: C.gray, strokeWidth: 3 });
        } else if (item.layout === 'compare' && i < 2) {
          const left = n === 1 ? 575 : 170 + i * 900;
          const center = left + 385;
          s.rect(left, 355, 770, n === 3 ? 405 : 495, { round: true, fill, stroke: color, strokeWidth: 3, roughness: 1.3 });
          s.text(left + 42, 389, String(i + 1).padStart(2, '0'), { size: 60, color });
          const hasSticker = sticker(i, center, 435, 150);
          fit(s, center, hasSticker ? 605 : 505, text, 670, n === 3 ? (hasSticker ? 130 : 220) : 310,
            { size: 52, align: 'center' });
        } else if (item.layout === 'compare') {
          s.highlight(245, 802, 1430, 95, { color: C.fYellow, opacity: 65 });
          fit(s, 960, 803, text, 1370, 100, { size: 42, align: 'center', color: C.ink });
        } else if (item.layout === 'summary') {
          // A handwritten checklist, keeping each conclusion close to its spoken beat.
          const top = n === 1 ? 495 : n === 2 ? 410 + i * 255 : 360 + i * 180;
          s.rect(280, top + 10, 58, 58, { round: true, fill, stroke: color, strokeWidth: 3 });
          s.line([[290, top + 39], [303, top + 54], [332, top + 18]], { stroke: color, strokeWidth: 5 });
          fit(s, 390, top, text, item.sticker ? 1040 : 1220, n === 3 ? 130 : 205, { size: 52, color: i === n - 1 ? C.brand : C.ink });
        } else {
          // Process diagram: connected milestones above concise action cards.
          s.ellipse(cx - 65, 365, 130, 130, { fill, stroke: color, strokeWidth: 3 });
          s.text(cx, 397, String(i + 1), { size: 60, align: 'center', color });
          if (i < n - 1) s.arrow([[cx + 100, 430], [cx + (n === 3 ? 500 : 800), 430]], { stroke: color, strokeWidth: 4 });
          const w = n === 3 ? 500 : 690;
          s.rect(cx - w / 2, 560, w, 300, { round: true, fill, stroke: color, strokeWidth: 2, roughness: 1.2 });
          const hasSticker = sticker(i, cx, 580, 120);
          fit(s, cx, hasSticker ? 728 : 630, text, w - 70, hasSticker ? 105 : 210, { size: 48, align: 'center' });
        }
      });
    }
    // Empty beat groups are intentional only when the narrator has more beats than cards.
    scenes.push(s);
  });

  const cover = (s, ratio) => {
    const portrait = ratio === '3:4';
    const title = payload.cover_title || payload.scenes[0].title;
    const coverTitle = coverLines(title);
    s.coverLayout({ ratio, title: coverTitle, tag: '白板讲解', sub: '', sticker: payload.cover_sticker });
    if (payload.cover_sticker) return;
    const cards = payload.scenes[0].cards;
    const top = portrait ? 730 : 620;
    const max = Math.min(3, cards.length);
    for (let i = 0; i < max; i++) {
      const x = portrait ? 165 : 125;
      s.rect(x, top + i * (portrait ? 145 : 95), portrait ? 750 : 1175, portrait ? 100 : 76,
        { round: true, fill: fills[i], stroke: colors[i], strokeWidth: 2 });
      fit(s, x + 30, top + 14 + i * (portrait ? 145 : 95), cards[i], portrait ? 690 : 1115,
        portrait ? 75 : 53, { size: portrait ? 34 : 36 });
    }
  };
  save(project, scenes, { cover });
  return scenes;
}

module.exports = { build };
if (require.main === module) {
  try { build(process.argv[2] || '.'); }
  catch (error) { console.error(error.stack || error); process.exitCode = 1; }
}
