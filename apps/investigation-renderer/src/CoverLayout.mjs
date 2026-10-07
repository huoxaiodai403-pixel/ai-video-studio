// Cover-only text/layout helpers. No scene, timeline, or media mutation.
export function coverPoints(scenes = []) {
  const scene = [...scenes].reverse().find(row => row.kind === 'diagram');
  const points = (scene?.points ?? []).map(point => {
    if (typeof point === 'string') {
      const at = point.search(/[｜|]/u);
      return at < 0 ? {title: point.trim(), text: ''}
        : {title: point.slice(0, at).trim(), text: point.slice(at + 1).trim()};
    }
    return {title: typeof point?.title === 'string' ? point.title.trim() : '',
      text: typeof point?.text === 'string' ? point.text.trim() : ''};
  }).filter(point => point.title || point.text).slice(0, 4);
  return {scene, points};
}

export function coverTitleTokens(value) {
  const text = String(value ?? '').replace(/\s+/gu, ' ').trim();
  if (!text) return [];
  // The bundled Chromium and Node support ICU word segmentation. Do not fall
  // back to per-character breaks: that recreates 是否 -> 是 / 否.
  if (!Intl.Segmenter) throw new Error('Cover title needs Intl.Segmenter for Chinese word boundaries.');
  const parts = [...new Intl.Segmenter('zh-CN', {granularity: 'word'}).segment(text)].map(item => item.segment);
  const tokens = [];
  let opening = '';
  for (const part of parts) {
    if (/^[（【《「『“‘(\[]+$/u.test(part)) {opening += part; continue;}
    if (/^[，。！？；：、）】》」』”’,.!?;:)\]\s]+$/u.test(part) && tokens.length && !opening) {
      tokens[tokens.length - 1] += part;
    } else {tokens.push(opening + part); opening = '';}
  }
  if (opening) tokens.push(opening);
  // Keep short question operators with their predicate, too: ending a line in
  // "是否" is technically word-safe but still makes a poor Chinese headline.
  for (let i = tokens.length - 2; i >= 0; i--) {
    if (/^(是否|能否|如何|为何)$/u.test(tokens[i])) tokens.splice(i, 2, tokens[i] + tokens[i + 1]);
  }
  return tokens;
}

export function fitCoverTitle(value, {width, height, measure, maxFont = 88, minFont = 36, lineHeight = 1.24}) {
  const tokens = coverTitleTokens(value);
  if (!tokens.length) return {lines: [], fontSize: maxFont, height: 0, lineHeight};
  for (let fontSize = maxFont; fontSize >= minFont; fontSize -= 2) {
    const ranges = new Map();
    const range = (start, end) => {
      const key = `${start}:${end}`;
      if (!ranges.has(key)) {
        const text = tokens.slice(start, end).join('').trim();
        // A colon commonly separates headline and subtitle. Keep that semantic
        // boundary instead of balancing half a subtitle onto the headline.
        const crossesSubtitle = tokens.slice(start, end - 1).some(token => /[：:]\s*$/u.test(token));
        ranges.set(key, {text, width: crossesSubtitle ? Infinity : measure(text, fontSize)});
      }
      return ranges.get(key);
    };
    // First find the fewest whole-word lines that fit. Then balance those lines
    // using measured Noto glyph widths instead of counting Chinese characters.
    let lineCount = 0, start = 0;
    while (start < tokens.length) {
      let end = start + 1;
      if (range(start, end).width > width) {lineCount = Infinity; break;}
      while (end < tokens.length && range(start, end + 1).width <= width) end++;
      start = end; lineCount++;
    }
    if (lineCount * fontSize * lineHeight > height) continue;
    const target = measure(tokens.join('').trim(), fontSize) / lineCount;
    const memo = new Map();
    const solve = (from, remaining) => {
      if (!remaining) return from === tokens.length ? {cost: 0, lines: []} : null;
      const key = `${from}:${remaining}`;
      if (memo.has(key)) return memo.get(key);
      let best = null;
      for (let end = from + 1; end <= tokens.length - remaining + 1; end++) {
        const row = range(from, end);
        if (row.width > width) break;
        if (!row.text) continue;
        const next = solve(end, remaining - 1);
        if (!next) continue;
        const cost = next.cost + (row.width - target) ** 2;
        if (!best || cost < best.cost) best = {cost, lines: [row.text, ...next.lines]};
      }
      memo.set(key, best); return best;
    };
    const fitted = solve(0, lineCount);
    if (fitted) return {lines: fitted.lines, fontSize, height: lineCount * fontSize * lineHeight, lineHeight};
  }
  throw new Error('Cover title cannot fit at a readable size without splitting words. Shorten the title.');
}
