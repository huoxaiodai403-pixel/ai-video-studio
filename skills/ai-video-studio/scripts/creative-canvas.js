/* Shared film timing and caption helpers. Not part of the workbench UI theme. */
window.Film = {
  clamp: (x, a = 0, b = 1) => Math.max(a, Math.min(b, x)),
  ease(x) { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); },
  shot(time) {
    const rows = CREATIVE_FILM.scenes;
    const index = Math.max(0, rows.findLastIndex(s => time >= s.start));
    const scene = rows[index];
    return { ...scene, index, local: Math.max(0, time - scene.start), progress: this.clamp((time - scene.start) / scene.duration) };
  },
  asset(id) { return document.getElementById('film-asset-' + id); },
  atlas(ctx, id, panel, x, y, width, height, zoom = 1, pan = 0) {
    const img = this.asset(id), cellW = img.naturalWidth / 2, cellH = img.naturalHeight / 2;
    const innerW = cellW - 8, innerH = cellH - 8;
    const ratio = width / height;
    const cropW = Math.min(innerW, innerH * ratio) / zoom, cropH = cropW / ratio;
    const sx = (panel % 2) * cellW + 4 + (innerW - cropW) * this.clamp(.5 + pan, 0, 1);
    const sy = Math.floor(panel / 2) * cellH + 4 + (innerH - cropH) / 2;
    ctx.drawImage(img, sx, sy, cropW, cropH, x, y, width, height);
  },
  text(ctx, value, x, y, size = 38, color = '#1d2122', align = 'left', weight = 600) {
    ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = 'middle';
    ctx.font = `${weight} ${size}px "Microsoft YaHei",sans-serif`; ctx.fillText(value, x, y);
  },
  captionLines(ctx, value, width) {
    const text = value.trim();
    if (ctx.measureText(text).width <= width) return [text];
    const parts = Array.from(new Intl.Segmenter('zh', { granularity: 'word' }).segment(text), x => x.segment);
    let best = null;
    for (let i = 1; i < parts.length; i++) {
      const left = parts.slice(0, i).join(''), right = parts.slice(i).join('');
      if (/^[，。！？；：、,.!?;:]/u.test(right)) continue;
      if (right.replace(/[^\p{L}\p{N}]/gu, '').length < 4) continue;
      const a = ctx.measureText(left).width, b = ctx.measureText(right).width;
      if (a > width || b > width) continue;
      const score = Math.abs(a - b) - (/[，。！？；：、,.!?;:]$/u.test(left) ? width * .12 : 0);
      if (!best || score < best.score) best = { score, lines: [left, right] };
    }
    if (best) return best.lines;
    const lines = []; let line = '';
    for (const part of parts) {
      if (line && ctx.measureText(line + part).width > width && !/^[，。！？；：、,.!?;:]/u.test(part)) {
        lines.push(line); line = '';
      }
      line += part;
    }
    if (line) lines.push(line);
    return lines;
  },
  caption(ctx, time, width, height, dark = false) {
    const row = CREATIVE_FILM.captions.find(c => time >= c.start && time < c.end);
    if (!row) return;
    ctx.save();
    const size = Math.round(Math.min(width / 22, height / 22));
    ctx.font = `500 ${size}px "Microsoft YaHei",sans-serif`;
    const lines = this.captionLines(ctx, row.text, width * .84);
    const bottom = height * .945, lineHeight = size * 1.4;
    lines.forEach((line, i) => {
      const y = bottom - (lines.length - 1 - i) * lineHeight;
      const length = ctx.measureText(line).width;
      ctx.fillStyle = dark ? 'rgba(16,23,25,.92)' : 'rgba(248,246,239,.96)';
      ctx.fillRect((width - length) / 2 - 15, y - size * .75, length + 30, size * 1.5);
      this.text(ctx, line, width / 2, y, size, dark ? '#fffaf0' : '#202425', 'center', 500);
    });
    ctx.restore();
  }
};
