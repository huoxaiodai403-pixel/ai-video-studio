/* Small single-purpose editors: local drafts and one stable current result. */
window.ToolWorkspace = (() => {
  'use strict';
  const el = id => document.getElementById(id);
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const names = {queued:'排队中', running:'正在生成', done:'已完成', error:'生成失败', interrupted:'任务已中断', cancelled:'已取消'};
  const created = job => Number(job.created) || Date.parse(job.created_at || '') / 1000 || 0;
  function reveal(node) {
    for (let parent = node.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
    node.focus();
  }
  document.addEventListener('invalid', event => reveal(event.target), true);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || event.defaultPrevented) return;
    const details = event.target.closest('main details[open]');
    if (details) { details.open = false; details.querySelector('summary').focus(); event.preventDefault(); }
  });
  function mediaURL(value) {
    try {
      const url = new URL(value, location.origin);
      return url.origin === location.origin && url.pathname.startsWith('/outputs/') ? url.href : '';
    } catch { return ''; }
  }
  function link(label, url, download) {
    const node = make('a', label); node.href = url;
    if (download !== undefined) node.download = download;
    return node;
  }
  function draft(name, capture, restore, partial = () => ({})) {
    const key = `ai-video-tool-${name}-v1-${document.documentElement.dataset.studioEdition || 'development'}`;
    const store = ToolDraftState.open(() => StudioStorage.local, key), state = store.state;
    let initialized = false, edited = false, restoring = false, loadingFailed = false, unsaved = false;
    let handoffKeys = [];
    const form = el('tool-form'), panel = make('section', '', 'draft-recovery');
    const title = make('strong', '草稿自动保存已暂停'), explanation = make('p');
    const actions = make('div', '', 'draft-recovery-actions');
    const original = make('button', '下载原草稿', 'quiet'), current = make('button', '下载当前编辑', 'quiet');
    const retry = make('button', '保留原稿并继续保存', 'secondary');
    const notice = make('p', '', 'draft-recovery-note'); notice.setAttribute('role', 'status');
    title.id = 'draft-recovery-title'; panel.setAttribute('aria-labelledby', title.id);
    for (const button of [original, current, retry]) button.type = 'button';
    actions.append(retry, original, current); panel.append(title, explanation, notice, actions);
    panel.hidden = true; form.before(panel);
    const backups = make('details', '', 'tool-details draft-backups'), backupSummary = make('summary');
    const backupInfo = make('p', '恢复时保留的原始内容与当时编辑，仅存于此浏览器。下载后可留存到电脑。', 'small');
    const exportBackups = make('button', '下载恢复备份', 'secondary'); exportBackups.type = 'button';
    backups.append(backupSummary, backupInfo, exportBackups); form.after(backups);
    function refreshBackups() {
      const count = store.backups().length;
      backups.hidden = !count; backupSummary.textContent = `已保留的草稿备份 · ${count} 份`;
    }
    refreshBackups();
    function status(message = '') {
      const issue = store.issue;
      panel.hidden = !issue;
      const label = issue ? '草稿尚未保存 · 当前输入仍可编辑' : message;
      if (el('draft-state').textContent !== label) el('draft-state').textContent = label;
      if (!issue) return;
      explanation.textContent = ({
        corrupt:'上次草稿无法读取，原内容仍保留。可先下载，再备份原稿并保存当前编辑。',
        restore:'上次草稿未能完整恢复，原内容仍保留。请检查当前输入，再备份原稿并保存。',
        conflict:'另一窗口更新了这份草稿，当前输入仍保留。继续保存会先备份两份内容。',
        read:'暂时无法读取浏览器草稿。当前输入仍可编辑，请先下载当前编辑，或稍后重试。',
        write:'浏览器未能保存草稿，可能是存储空间不足。请下载当前编辑，或稍后重试。',
        capture:'当前编辑暂时无法完整保存。请检查输入，并下载可保留的内容。'
      })[issue];
      original.hidden = !store.originals().length;
      retry.textContent = issue === 'write' ? '重试保存' : store.recoveryError === 'backup' ? '重试备份并保存' : '保留原稿并继续保存';
      const downloadFirst = issue === 'write' || Boolean(store.recoveryError);
      current.className = downloadFirst ? 'primary' : 'quiet';
      const first = downloadFirst ? current : retry;
      if (actions.firstElementChild !== first) {
        const focused = panel.contains(document.activeElement) ? document.activeElement : null;
        actions.prepend(first); focused?.focus({preventScroll:true});
      }
      notice.textContent = store.recoveryError === 'backup' ? '备份或保存失败，原草稿没有被覆盖。请先下载当前编辑。' :
        store.recoveryError === 'changed' ? '备份时另一窗口又更新了草稿，本次没有覆盖。请核对后重试。' : '';
    }
    function snapshot() {
      try {
        state.data = initialized ? capture() : {...state.data, ...partial()};
        state.saved_at = new Date().toISOString(); return true;
      } catch { store.block('capture'); status(); return false; }
    }
    function finishHandoff() {
      if (!handoffKeys.length || !initialized) return;
      const url = new URL(location.href);
      for (const key of handoffKeys) url.searchParams.delete(key);
      window.history.replaceState(null, '', url); handoffKeys = [];
    }
    function save() {
      if (restoring || !snapshot()) return;
      unsaved = !store.save();
      if (!unsaved) finishHandoff();
      status(initialized ? '草稿已保存在此浏览器' : loadingFailed ? '文本草稿已保存在此浏览器' : '文本草稿已保存，正在读取设置…');
    }
    function changed() {
      if (restoring) return;
      edited = true; unsaved = true; save();
      document.dispatchEvent(new Event('tool-draft-change'));
    }
    function download(raw, suffix, type = 'application/json') {
      const url = URL.createObjectURL(new Blob([raw], {type}));
      const anchor = link('', url, `${name}-${suffix}-${Date.now()}.${type === 'text/plain' ? 'txt' : 'json'}`);
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    original.onclick = () => {
      const rows = store.originals();
      if (rows.length === 1) download(rows[0], 'original', 'text/plain');
      else download(JSON.stringify({source:key, originals:rows}, null, 2), 'originals');
    };
    current.onclick = () => { if (snapshot()) download(JSON.stringify(state, null, 2), 'editing'); };
    exportBackups.onclick = () => download(JSON.stringify({source:key, backups:store.backups()}, null, 2), 'recovery-backups');
    retry.onclick = () => {
      if (!snapshot()) return;
      const backedUp = store.issue !== 'write';
      const succeeded = store.recover(); unsaved = !succeeded;
      if (succeeded) finishHandoff();
      refreshBackups();
      status(backedUp ? '原稿已保留，当前编辑已保存' : '当前编辑已保存');
      if (succeeded) [...form.querySelectorAll('textarea,input,select')].find(field => !field.disabled && field.getClientRects().length)?.focus({preventScroll:true});
    };
    form.addEventListener('input', changed); form.addEventListener('change', changed);
    for (const name of ['creation-settings-changed', 'creation-engine-changed', 'image-references-changed', 'speech-source-change', 'voices-updated']) document.addEventListener(name, () => { if (initialized) changed(); });
    window.addEventListener('storage', event => { if (StudioStorage.local.matches(event, key)) { store.inspect(); if (store.issue) status(); } });
    window.addEventListener('beforeunload', event => { if (unsaved) { event.preventDefault(); event.returnValue = ''; } });
    status('正在读取草稿…');
    return {
      state, changed, get protected() { return Boolean(store.issue); }, signature:() => JSON.stringify(capture()),
      acceptHandoff(keys) {
        // Imported choices become a normal editable draft only after a safe save.
        const url = new URL(location.href);
        handoffKeys = keys.filter(key => url.searchParams.has(key));
        if (handoffKeys.length && initialized) save();
      },
      unavailable() { loadingFailed = true; status('设置未完成载入；文本仍自动保留'); },
      initialize() {
        restoring = true;
        let failed = false;
        // Partial edits already live in state.data; merge them with saved settings.
        try { if (state.data) restore(state.data); }
        catch { failed = true; store.block('restore'); status(); }
        finally { restoring = false; initialized = true; }
        if (failed) return;
        // Keep empty first visits empty; a saved draft never changes global defaults.
        if (state.data || edited) save(); else status('输入后自动保存浏览器草稿');
      },
      remember(id, signature) {
        state.submitted = {...state.submitted, [id]:signature};
        state.submitted = Object.fromEntries(Object.entries(state.submitted).slice(-12));
        state.selected = id; save();
      },
      select(id) { state.selected = id; save(); }
    };
  }
  function jobs({kind, draft, render, empty, update = () => {}}) {
    const requested = new URLSearchParams(location.search).get('job');
    let rows = {}, selected = requested || draft.state.selected || '', busy = false, rendered = '', localPending = {};
    const history = el('job-history'), status = el('job-state'), media = el('job-media'), actions = el('job-actions');
    const matches = job => kind === 'image' ? !job.kind || job.kind === 'image' : job.kind === kind;
    const snapshot = () => { try { return draft.signature(); } catch { return ''; } };
    function origin() {
      const submitted = draft.state.submitted?.[selected];
      el('job-origin').textContent = !selected ? '' : !submitted ? '历史任务 · 当前输入保持独立' : submitted === snapshot() ? '本次提交 · 与当前输入一致' : '输入已更新 · 此任务仍使用提交时的内容';
    }
    function draw() {
      const job = rows[selected] || localPending[selected];
      history.value = selected;
      if (!job) {
        status.textContent = selected ? '未找到上次任务' : '等待生成';
        delete status.dataset.state; el('job-error').textContent = ''; el('job-note').textContent = '';
        el('job-id').textContent = '';
        el('job-empty').textContent = selected ? '上次任务暂不可用。可以选择其他近期结果，当前草稿仍保留。' : empty;
        el('job-empty').hidden = false;
        if (rendered) { media.replaceChildren(); actions.replaceChildren(); rendered = ''; }
        update('', {}); origin(); return;
      }
      status.textContent = names[job.status] || job.status || '等待状态';
      status.dataset.state = job.status;
      el('job-id').textContent = selected;
      el('job-error').textContent = job.error || '';
      const signature = JSON.stringify([selected, job.image, job.image_path, job.audio, job.audio_path, job.video, job.subtitle, job.transcript, job.metadata, job.voice_engine]);
      if (rendered !== signature) {
        // Polling a status must never recreate an audio player or restart playback.
        media.replaceChildren(); actions.replaceChildren(); el('job-note').textContent = '';
        render(selected, job, {media, actions, note:el('job-note')}); rendered = signature;
      }
      update(selected, job);
      el('job-empty').hidden = Boolean(media.childElementCount);
      el('job-empty').textContent = job.status === 'error' || job.status === 'interrupted' ? '本次没有生成结果。检查提示后可重新提交；输入和设置仍在编辑区。' : job.status === 'done' ? '任务已完成，但预览暂不可用。请到作品库查看输出文件。' : '任务处理中，可以继续调整下一次输入，或离开页面稍后回来。';
      origin();
    }
    function choices() {
      const sorted = Object.entries({...localPending, ...rows}).reverse().sort((a,b) => created(b[1]) - created(a[1]));
      const recent = sorted.slice(0, 20);
      if (selected && !recent.some(([id]) => id === selected) && rows[selected]) recent.push([selected, rows[selected]]);
      if (!selected && recent.length) selected = recent[0][0];
      const options = recent.map(([id, job]) => {
        let description = job.title || '';
        if (kind === 'speech') {
          try {
            const submitted = JSON.parse(draft.state.submitted?.[id] || '{}');
            description = [submitted.text?.trim().replace(/\s+/g, ' ').slice(0, 28), submitted.source?.voice_id].filter(Boolean).join(' · ') || description;
          } catch { /* Older task records can still be selected by time and ID. */ }
        }
        return [id, `${description ? description + ' · ' : ''}${created(job) ? new Date(created(job) * 1000).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '近期'} · ${names[job.status] || job.status} · ${id.slice(-6)}`];
      });
      if (selected && !options.some(([id]) => id === selected)) options.unshift([selected, '上次任务 · 暂不可用']);
      if (!options.length) options.push(['', '暂无近期任务']);
      const signature = JSON.stringify(options);
      if (history.dataset.options !== signature) { history.replaceChildren(...options.map(([value,label]) => new Option(label,value))); history.dataset.options = signature; }
      history.disabled = options.length === 1 && !options[0][0];
    }
    async function poll() {
      if (busy) return; busy = true;
      try {
        const data = await Creation.api('/api/jobs');
        rows = Object.fromEntries(Object.entries(data).filter(([,job]) => matches(job)));
        for (const id of Object.keys(localPending)) if (rows[id]) delete localPending[id];
        el('job-poll-status').textContent = ''; choices(); draw();
      } catch (error) { el('job-poll-status').textContent = '任务状态暂时无法刷新：' + error.message + '。稍后自动重试。'; }
      finally { busy = false; }
    }
    function consumeJob() {
      const url = new URL(location.href); if (!url.searchParams.has('job')) return;
      url.searchParams.delete('job'); window.history.replaceState(null, '', url);
    }
    history.onchange = () => { selected = history.value; draft.select(selected); consumeJob(); draw(); };
    document.addEventListener('tool-draft-change', origin);
    draw(); poll(); let timer = setInterval(poll, 5000);
    window.addEventListener('pagehide', () => { clearInterval(timer); timer = null; });
    window.addEventListener('pageshow', () => { if (!timer) { timer = setInterval(poll, 5000); poll(); } });
    return {
      poll,
      pending(signature) {
        return Object.entries({...localPending, ...rows}).some(([id, job]) =>
          ['queued', 'running'].includes(job.status) && (!signature || draft.state.submitted?.[id] === signature));
      },
      submitted(id, signature) {
        selected = id; localPending[id] = {kind, status:'queued', created:Date.now()/1000};
        consumeJob();
        draft.remember(id, signature); choices(); draw(); poll();
        el('current-result').focus({preventScroll:true});
        if (matchMedia('(max-width:1100px)').matches) el('current-result').scrollIntoView({block:'start'});
      }
    };
  }
  // A library response may arrive after the user edits a path; it only fills options.
  function sources({target, kinds, accept, onSelect = () => {}}) {
    let items = [], pending = false;
    const select = el('source-library'), status = el('source-status');
    const normalized = path => /^[A-Za-z]:[\\/]/.test(path) ? path.replace(/\\/g,'/').toLowerCase() : path;
    const current = () => items.find(row => normalized(row.absolute_path) === normalized(target.value.trim()));
    function sync() { select.value = current()?.id || ''; onSelect(current()); }
    async function refresh() {
      if (pending) return; pending = true; el('refresh-source').disabled = true;
      status.textContent = '正在读取素材…';
      try {
        const data = await Creation.api('/api/library?view=assets&status=done');
        items = (data.items || []).filter(row => row.absolute_path && kinds.includes(row.media_type) && (!accept || accept.test(row.absolute_path)));
        select.replaceChildren(new Option(items.length ? '选择一份已有素材' : '资源库暂无可用素材', ''), ...items.map(row => new Option(row.title, row.id)));
        status.textContent = items.length ? `可选 ${items.length} 份素材；也可直接填写本机路径。` : '可填写本机路径，或先在资源库导入素材。'; sync();
      } catch (error) { status.textContent = '素材列表读取失败：' + error.message + '。已填写的路径仍保留。'; }
      finally { pending = false; el('refresh-source').disabled = false; }
    }
    select.onchange = () => {
      const item = items.find(row => row.id === select.value); if (!item) return;
      target.value = item.absolute_path; target.dispatchEvent(new Event('input', {bubbles:true})); sync();
    };
    target.addEventListener('input', sync); el('refresh-source').onclick = refresh;
    refresh(); return {current, sync, refresh};
  }
  // A submitted snapshot owns its busy state; editing never locks a whole form.
  function updateSubmit(button, {ready = true, submitting = false, blocked = false, jobs, draft, label, pendingLabel = '当前内容正在生成', newLabel = '生成新任务', blockedLabel}) {
    const same = ready && jobs.pending(draft.signature());
    button.disabled = !ready || submitting || blocked || same;
    button.setAttribute('aria-busy', String(submitting || same));
    button.textContent = blocked && blockedLabel ? blockedLabel : submitting ? '正在提交…' : same ? pendingLabel : ready && jobs.pending() ? newLabel : label;
  }
  return {el, make, reveal, mediaURL, link, draft, jobs, sources, updateSubmit};
})();
