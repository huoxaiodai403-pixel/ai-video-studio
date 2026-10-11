(() => {
  'use strict';
  const {el, make, link, mediaURL, draft:localDraft, jobs:jobView} = ToolWorkspace;
  const fields = ['prompt','subject','style','composition','palette','reference','library','query'];
  const friend = document.documentElement.dataset.studioEdition === 'friend';
  const navigation = new URLSearchParams(location.search);
  const explicitSource = navigation.has('reference') || navigation.has('engine');
  const referencesReady = () => ImageReferences.ready.catch(error => { if (explicitSource) throw error; });
  let caseId = null, spec = {}, previousPrompt, selectedCase = null, pendingSettings = null, searchVersion = 0, initialized = false, submitting = false;
  const feedback = (text, error = false) => { el('message').textContent = text; el('message').dataset.error = String(error); };
  function capture() {
    return {fields:Object.fromEntries(fields.map(id => [id,el(id).value])), backend:el('backend').value, settings:Creation.read().image, references:ImageReferences.peek(), selectedCase};
  }
  function showCase(row) {
    selectedCase = row; caseId = el('library').value === 'image' ? row?.id || null : null;
    el('caseTitle').textContent = row?.title || '尚未选择案例'; el('original').value = row?.promptFull || row?.prompt || '';
    let url; try { const candidate = new URL(row?.sourceUrl || row?.githubUrl); if (['https:','http:'].includes(candidate.protocol)) url = candidate.href; } catch {}
    el('source').hidden = !url; if (url) el('source').href = url; else el('source').removeAttribute('href');
  }
  for (const event of ['input','change']) el('tool-form').addEventListener(event, event => {
    if (!initialized && event.target?.dataset?.group === 'image') pendingSettings = structuredClone(Creation.read().image);
  });
  const draft = localDraft('image', capture, saved => {
    for (const id of fields) if (typeof saved.fields?.[id] === 'string') el(id).value = saved.fields[id];
    if (!navigation.has('reference') && !navigation.has('engine')) {
      if (saved.settings && typeof saved.settings === 'object') Creation.set({...Creation.read(), image:{...Creation.read().image,...saved.settings}});
      el('backend').value = friend ? 'online' : saved.backend === 'online' ? 'online' : 'local';
      el('backend').dispatchEvent(new Event('change', {bubbles:true}));
    }
    if (saved.selectedCase) showCase(saved.selectedCase);
  }, () => ({fields:Object.fromEntries(fields.map(id => [id,el(id).value])),backend:el('backend').value,selectedCase,...(pendingSettings ? {settings:pendingSettings} : {})}));
  for (const id of fields) if (typeof draft.state.data?.fields?.[id] === 'string') el(id).value = draft.state.data.fields[id];
  if (!explicitSource && draft.state.data?.backend) el('backend').value = friend ? 'online' : draft.state.data.backend === 'online' ? 'online' : 'local';
  if (draft.state.data?.selectedCase) showCase(draft.state.data.selectedCase);
  const jobs = jobView({kind:'image', draft, empty:'写下画面描述并生成。完成的图像会出现在这里，也可以继续查看近期作品。', render(id, job, view) {
    const url = mediaURL(job.image); if (!url) return;
    const image = make('img'); image.src = url; image.alt = '任务 ' + id + ' 的生成图像'; view.media.append(image);
    const save = make('button', '存入参考图库', 'secondary'); save.type = 'button';
    save.onclick = async () => { save.disabled = true; try { await ImageReferences.saveJob(id); view.note.textContent = '已存入参考图库，可重复用于角色与场景。'; } catch (error) { view.note.textContent = error.message; } finally { save.disabled = false; } };
    const motion = link('用于短镜头', '#');
    if (job.image_path) motion.href = '/motion?' + new URLSearchParams({image:job.image_path,preview:url});
    else motion.onclick = async event => { event.preventDefault(); try { const ref = await ImageReferences.saveJob(id); location.assign('/motion?' + new URLSearchParams({image:ref.path, preview:ref.preview_url})); } catch (error) { view.note.textContent = error.message; } };
    view.actions.append(link('下载原图',url,id+'.png'),save,motion);
  }, update() { queueMicrotask(describe); }});
  function describe() {
    ToolWorkspace.updateSubmit(el('generate'), {ready:initialized, submitting, jobs, draft, label:'生成图像', pendingLabel:'这幅画面正在生成', newLabel:'生成新图像'});
    el('text-count').textContent = el('prompt').value.length + ' 字';
    if (!Creation.inventory?.settings) return;
    const settings = Creation.read().image;
    const engine = Creation.inventory?.image_engines?.find(row => row.id === settings.engine);
    const size = `${settings.width} × ${settings.height}`;
    el('settings-summary').textContent = size;
    el('output-summary').textContent = el('backend').value === 'online' ? size + ' · 按服务商计费' : size + ' · ' + (engine?.label || engine?.name || settings.engine);
  }
  async function find() {
    const version = ++searchVersion, library = el('library').value;
    el('count').textContent = '正在读取案例…';
    try {
      const data = await Creation.api('/api/cases?q=' + encodeURIComponent(el('query').value) + '&library=' + encodeURIComponent(library));
      if (version !== searchVersion) return;
      el('count').textContent = `已接入 ${data.total} 条案例 · 本次找到 ${data.cases.length} 条`;
      el('list').replaceChildren(...data.cases.map(row => {
        const button = make('button', row.title, 'case'); button.type = 'button';
        button.onclick = () => { showCase(row); draft.changed(); }; return button;
      }));
      if (!data.cases.length) el('list').textContent = '没有匹配案例，试试更短的关键词。';
    } catch (error) { if (version === searchVersion) el('count').textContent = '案例读取失败：' + error.message; }
  }
  el('case-browser').addEventListener('toggle', () => { if (el('case-browser').open && !el('list').childElementCount) find(); });
  el('search').onclick = find;
  el('library').onchange = () => { showCase(null); find(); };
  el('query').onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); find(); } };
  el('compile').onclick = async () => {
    if (!el('subject').value.trim()) { el('subject').focus(); el('compile-status').textContent = '先填写画面内容，再组合提示词。'; return; }
    const request = {subject:el('subject').value,style:el('style').value,composition:el('composition').value,palette:el('palette').value,case_id:caseId,reference_text:el('reference').value};
    const before = draft.signature(); el('compile').disabled = true;
    try {
      const response = await Creation.api('/api/compile', request);
      if (before !== draft.signature()) { el('compile-status').textContent = '输入在组合期间发生变化，已保留你的新内容。请再次组合。'; return; }
      previousPrompt = el('prompt').value; spec = response; el('prompt').value = response.prompt;
      el('undo-compile').hidden = false; el('compile-status').textContent = '已替换画面描述，可继续修改或撤回。'; draft.changed(); describe(); el('prompt').focus();
    } catch (error) { el('compile-status').textContent = error.message; }
    finally { el('compile').disabled = false; }
  };
  el('undo-compile').onclick = () => { if (previousPrompt !== undefined) { el('prompt').value = previousPrompt; previousPrompt = undefined; spec = {}; el('undo-compile').hidden = true; draft.changed(); describe(); el('prompt').focus(); el('compile-status').textContent = '已恢复替换前的画面描述。'; } };
  el('tool-form').addEventListener('submit', async event => {
    event.preventDefault(); if (el('generate').disabled) return;
    submitting = true; describe(); el('action-help').hidden = true;
    try {
      await Creation.ready;
      await referencesReady(); // Unused reference libraries need not block text-only generation.
      if (!el('prompt').value.trim()) { el('prompt').focus(); throw Error('请填写画面描述。'); }
      const settings = Creation.read(), reference_ids = ImageReferences.referenceIds();
      const profile = Creation.inventory.image_engines?.find(row => row.id === settings.image.engine);
      if (el('backend').value === 'local' && profile && !profile.ready) throw Error('所选图像引擎的模型组件尚未齐全，请到“本地模型”查看。');
      const signature = draft.signature();
      const result = await Creation.api('/api/generate', {...spec, backend:el('backend').value, prompt:el('prompt').value, settings, reference_ids});
      feedback(''); jobs.submitted(result.job_id, signature);
    } catch (error) {
      feedback(error.message, true);
      const online = el('backend').value === 'online';
      el('action-help').replaceChildren(link(online ? '检查在线图像服务 →' : '查看本地模型 →', online ? '/settings?service=image' : '/models'));
      el('action-help').hidden = false;
      if (/参考图/.test(error.message)) el('reference-panel').open = true;
    } finally { submitting = false; describe(); }
  });
  el('tool-form').addEventListener('input', describe); el('tool-form').addEventListener('change', describe);
  document.addEventListener('creation-settings-changed', describe);
  document.addEventListener('creation-engine-changed', describe);
  for (const event of ['creation-settings-changed','creation-engine-changed']) document.addEventListener(event, () => {
    if (!initialized) { pendingSettings = structuredClone(Creation.read().image); draft.changed(); }
  });
  describe();
  Creation.ready.then(async () => {
    await referencesReady();
    draft.initialize(); initialized = true; describe();
    draft.acceptHandoff(['reference','engine','backend']);
    document.dispatchEvent(new Event('tool-draft-change'));
  }).catch(error => {
    draft.unavailable(); describe();
    feedback('无法完成载入：' + error.message.replace(/[。.!！]+$/,'') + '。画面描述仍保留。',true);
    if (explicitSource) { el('action-help').replaceChildren(link('返回图像，重新选择来源 →','/image')); el('action-help').hidden=false; }
  });
})();
