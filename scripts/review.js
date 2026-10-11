(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const player = $('review-player');
  const identity = new URLSearchParams(location.search).get('id');
  const draftKey = 'studio-review-draft:' + identity;
  const labels = {meaning:'内容与画面', type:'文字与字幕', motion:'动作与连续性', sound:'声音与同步', ending:'片尾与交付'};
  const hints = {meaning:'画面解释旁白；事实有出处，示意有标注。', type:'检查长句、数字、字幕遮挡与安全边距。', motion:'每镜一个主事件，动作有起止；循环接缝连贯。', sound:'整句试听，检查音画同步、停顿、爆音与抢声。', ending:'片尾不截音、不黑帧；画幅与交付要求一致。'};
  let documentData, review, savedSignature = '', loading = false, saving = false, editing = 0, request = 0;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const signature = value => JSON.stringify({checks:value.checks, notes:value.notes, verdict:value.verdict});
  const dirty = () => review && signature(review) !== savedSignature;
  function clock(value) {
    const ms = Math.round(Math.max(0, value || 0) * 1000);
    return String(Math.floor(ms / 60000)).padStart(2,'0') + ':' + String(Math.floor(ms / 1000) % 60).padStart(2,'0') + '.' + String(ms % 1000).padStart(3,'0');
  }
  async function api(data) {
    const response = await fetch('/api/review' + (data ? '' : '?id=' + encodeURIComponent(identity)), {
      cache:'no-store', ...(data ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)} : {})
    });
    const value = await response.json();
    if (!response.ok) { const error = new Error(value.error || '读取失败'); error.status = response.status; throw error; }
    return value;
  }
  function cacheDraft() {
    try { StudioStorage.session.setItem(draftKey, JSON.stringify({media_fingerprint:review.media_fingerprint, review})); }
    catch (_) { /* Storage restrictions never prevent a server save. */ }
  }
  function updateState() {
    $('check-progress').textContent = Object.values(review.checks).filter(v => v === 'pass' || v === 'na').length + ' / 5';
    $('note-count').textContent = review.notes.length;
    $('no-notes').hidden = !!review.notes.length;
    $('review-save-state').textContent = dirty() ? '有未保存的修改' : review.revision ? '已保存 · 版本 ' + review.revision : '尚未修改';
    $('review-save-state').classList.remove('is-error');
  }
  function change() { ++editing; cacheDraft(); updateState(); }
  function option(value, text) { const n = node('option', text); n.value = value; return n; }
  function renderChecks() {
    $('review-checks').replaceChildren(...Object.keys(labels).map(key => {
      const label = node('label', null, 'review-check');
      label.append(node('strong', labels[key]), node('span', hints[key]));
      const select = node('select'); select.setAttribute('aria-label', labels[key]);
      select.append(option('pending','待审看'), option('pass','✓ 通过'), option('issue','! 有问题'), option('na','不适用'));
      select.value = review.checks[key]; select.onchange = () => { review.checks[key] = select.value; change(); };
      label.append(select); return label;
    }));
    $('review-verdict').value = review.verdict;
  }
  function seek(seconds) { player.pause(); player.currentTime = Math.max(0, Math.min(player.duration || 0, seconds)); }
  function renderNote(note) {
    const row = node('li', null, 'review-note' + (note.resolved ? ' is-resolved' : ''));
    const heading = node('div', null, 'review-note-heading');
    const jump = node('button', clock(note.seconds)); jump.type = 'button'; jump.setAttribute('aria-label','跳到 ' + clock(note.seconds)); jump.onclick = () => seek(note.seconds);
    const category = node('select'); category.setAttribute('aria-label','标记分类');
    for (const [key, text] of Object.entries(labels)) category.append(option(key, text));
    category.value = note.category; category.onchange = () => { note.category = category.value; change(); };
    const resolved = node('label', '已处理'); const checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.checked = note.resolved;
    checkbox.onchange = () => { note.resolved = checkbox.checked; row.classList.toggle('is-resolved', note.resolved); change(); };
    resolved.prepend(checkbox); heading.append(jump, category, resolved);
    const input = node('textarea'); input.rows = 2; input.maxLength = 2000; input.value = note.text; input.placeholder = '哪里有问题？希望怎样改？例如：数字出现太快，延长停留并避开字幕。'; input.setAttribute('aria-label','返修说明 ' + clock(note.seconds));
    input.oninput = () => { note.text = input.value; change(); };
    const remove = node('button','移除此标记','review-remove quiet'); remove.type = 'button';
    remove.onclick = () => { const index = review.notes.findIndex(n => n.id === note.id); review.notes.splice(index,1); row.remove(); change(); $('mark-current').focus(); };
    row.append(heading,input,remove); return row;
  }
  function renderNotes() { $('review-notes').replaceChildren(...review.notes.map(renderNote)); }
  function preserveDraft() { if (review && dirty()) cacheDraft(); }
  function draftAction() {
    let value;
    try { value = JSON.parse(StudioStorage.session.getItem(draftKey) || 'null'); } catch (_) { return; }
    if (!value?.review || value.media_fingerprint !== review.media_fingerprint || signature(value.review) === signature(review)) return;
    let button = $('restore-review-draft');
    if (!button) { button = node('button','恢复本页暂存草稿','quiet'); button.id = 'restore-review-draft'; button.type = 'button'; $('review-save-state').after(button); }
    button.hidden = false;
    button.onclick = () => {
      review.checks = value.review.checks; review.notes = value.review.notes; review.verdict = value.review.verdict;
      renderChecks(); renderNotes(); change(); button.hidden = true;
      $('review-status').textContent = '已恢复本页草稿。请与刚读取的记录核对，再保存当前版本。';
    };
  }
  async function load() {
    if (loading || saving) return;
    if (!identity) { $('review-status').textContent = '从作品库选择样片或成片开始。'; $('review-empty').hidden = false; $('retry-load').hidden = true; return; }
    preserveDraft(); loading = true; const sequence = ++request, generation = editing;
    $('review-status').textContent = '正在读取视频与审片记录…'; $('review-status').classList.remove('is-error');
    try {
      const data = await api();
      if (sequence !== request || editing !== generation) return;
      documentData = data; review = structuredClone(data.review); savedSignature = signature(review);
      $('review-title').textContent = data.item.title || '审片与返修';
      let returnUrl=new URL('/library',location.origin);
      try { const requested=new URL(new URLSearchParams(location.search).get('from')||'/library',location.origin); if(requested.origin===location.origin&&['/library','/gallery','/audio-library'].includes(requested.pathname))returnUrl=requested; } catch (_) { /* Invalid return links stay in the library. */ }
      returnUrl.searchParams.set('item',identity);$('back-to-work').href=returnUrl.pathname+returnUrl.search;
      const source = data.item.preview_url;
      if (!source || !source.startsWith('/outputs/') || source.startsWith('//')) throw new Error('作品播放地址无效');
      if (player.dataset.source !== source || player.dataset.fingerprint !== review.media_fingerprint) { player.pause(); player.src = source + '?review=' + review.media_fingerprint; player.dataset.source = source; player.dataset.fingerprint = review.media_fingerprint; }
      $('review-metadata').textContent = [data.item.status === 'preview' ? '样片' : '视频文件', '实际 ' + data.media.duration.toFixed(2) + ' 秒', data.media.width + ' × ' + data.media.height, data.media.fps ? data.media.fps.toFixed(2) + ' fps' : '帧率未知', data.media.has_audio ? '含音轨，请试听' : '无音轨'].join(' · ');
      $('previous-frame').disabled = $('next-frame').disabled = !data.media.fps;
      $('media-changed').hidden = !data.stale;
      if (data.stale) $('previous-review').textContent = JSON.stringify(data.previous_review, null, 2);
      renderChecks(); renderNotes(); updateState(); draftAction();
      $('review-workspace').hidden = false; $('review-empty').hidden = true; $('reload-review').hidden = true;
      $('review-status').textContent = data.stale ? '新文件尚未审看，上一版记录保留在上方。' : '当前检查与这份视频文件绑定，保存不会修改视频或重新生成。';
    } catch (error) {
      $('review-status').textContent = '读取失败：' + error.message + (review ? '。保留当前草稿。' : ''); $('review-status').classList.add('is-error');
      if (!review) $('review-empty').hidden = false;
    } finally { loading = false; }
  }
  $('mark-current').onclick = () => {
    if (!review || !Number.isFinite(player.duration)) return;
    if (review.notes.length >= 200) { $('review-status').textContent = '标记已达 200 条，请先整理已有记录。'; return; }
    player.pause(); const note = {id:crypto.randomUUID().replaceAll('-',''),seconds:Math.round(player.currentTime*1000)/1000, category:'meaning',text:'',resolved:false};
    review.notes.push(note); const row = renderNote(note); $('review-notes').append(row); change(); row.querySelector('textarea').focus();
  };
  $('previous-frame').onclick = () => seek(player.currentTime - 1 / documentData.media.fps);
  $('next-frame').onclick = () => seek(player.currentTime + 1 / documentData.media.fps);
  player.addEventListener('timeupdate', () => { $('review-clock').textContent = clock(player.currentTime); });
  player.addEventListener('error', () => { $('review-status').textContent = '视频暂时无法播放，请检查文件或重试读取。审片草稿仍保留。'; $('review-status').classList.add('is-error'); });
  $('playback-speed').onchange = () => { player.playbackRate = Number($('playback-speed').value); };
  $('review-verdict').onchange = () => { review.verdict = $('review-verdict').value; change(); };
  $('save-review').onclick = async () => {
    if (saving || loading || !review) return;
    const empty = [...$('review-notes').querySelectorAll('textarea')].find(n => !n.value.trim());
    if (empty) { $('review-save-state').textContent = '请写明标记的具体问题。'; empty.focus(); return; }
    saving = true; $('save-review').disabled = true; $('save-review').textContent = '保存中…';
    const snapshot = {id:identity, ...structuredClone(review)}; delete snapshot.updated_at;
    const sentSignature = signature(snapshot);
    try {
      const data = await api(snapshot);
      review.revision = data.review.revision; review.updated_at = data.review.updated_at; savedSignature = sentSignature;
      // Edits made during POST remain on screen and stay dirty.
      ++editing; updateState(); cacheDraft(); $('reload-review').hidden = true;
    } catch (error) {
      cacheDraft(); $('review-save-state').textContent = '保存失败：' + error.message; $('review-save-state').classList.add('is-error');
      $('reload-review').hidden = error.status !== 409;
    } finally { saving = false; $('save-review').disabled = false; $('save-review').textContent = '保存审片记录'; }
  };
  $('copy-review').onclick = async () => {
    const text = ['作品：' + documentData.item.title, '文件版本：' + review.media_fingerprint, '结论：' + ({pending:'待审看','needs-fix':'需要返修',approved:'审看通过'})[review.verdict],
      ...Object.entries(review.checks).map(([key,value]) => labels[key] + '：' + ({pending:'待审看',pass:'通过',issue:'有问题',na:'不适用'})[value]),
      ...review.notes.map(n => '[' + clock(n.seconds) + '] ' + labels[n.category] + ' / ' + (n.resolved ? '已处理' : '待处理') + '：' + n.text),
      '只修改标记涉及的内容，保留角色、声音和无关镜头；生成新版后重新审看。'].join('\n');
    try { await navigator.clipboard.writeText(text); $('review-status').textContent = '返修说明已复制，可以交给 Codex 或剪辑人员。'; }
    catch (_) { $('review-status').textContent = '无法访问剪贴板，请从下方选择返修文字复制。'; let field = $('review-copy-text'); if (!field) { field = node('textarea'); field.id = 'review-copy-text'; field.setAttribute('aria-label','可复制的返修说明'); $('review-notes').after(field); } field.value = text; field.focus(); field.select(); }
  };
  $('reload-review').onclick = load; $('retry-load').onclick = load;
  window.addEventListener('beforeunload', event => { if (dirty()) { cacheDraft(); event.preventDefault(); event.returnValue = ''; } });
  load();
})();
