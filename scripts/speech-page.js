(() => {
  'use strict';
  const {el, make, link, mediaURL, draft:localDraft, jobs:jobView} = ToolWorkspace;
  const params = new URLSearchParams(location.search);
  const explicitSource = ['engine','preset','backend','voice_id'].some(key => params.has(key));
  const source = window.SpeechSource;
  let initialized = false, submitting = false;
  function capture() { return {text:el('text').value, source:source.peek(), options:source.options(), voice:Creation.read().voice}; }
  const draft = localDraft('speech', capture, saved => {
    if (typeof saved.text === 'string') el('text').value = saved.text;
    if (!explicitSource) {
      if (saved.voice && typeof saved.voice === 'object') Creation.set({...Creation.read(),voice:{...Creation.read().voice,...saved.voice}});
      source.set(saved.source); source.setOptions(saved.options);
    }
  }, () => ({text:el('text').value}));
  // Text can be restored before Windows finishes enumerating installed voices.
  if (typeof draft.state.data?.text === 'string') el('text').value = draft.state.data.text;
  const jobs = jobView({kind:'speech', draft, empty:'输入一小段台词并生成，完成后在这里试听、下载配音和同步字幕。', render(id, job, view) {
    const url = mediaURL(job.audio); if (!url) return;
    const title = make('p', '听听这段声音', 'audio-title'), caption = make('p', '检查发音、语气与停顿', 'audio-caption');
    const audio = make('audio'); audio.controls = true; audio.preload = 'metadata'; audio.src = url; audio.setAttribute('aria-label','当前配音试听');
    view.media.append(title,caption,audio); view.actions.append(link('下载配音',url,id+'.wav'));
    const subtitle = mediaURL(job.subtitle); if (subtitle) view.actions.append(link('下载字幕 SRT',subtitle,id+'.srt'));
    if (job.voice_engine === 'qwen3-design') view.actions.append(link('保存为角色音色','/voices?fromJob='+encodeURIComponent(id)));
  }, update() { queueMicrotask(describe); }});
  function describe() {
    el('text-count').textContent = el('text').value.length + ' / 4000 字';
    const local = source.peek().backend === 'local' && document.documentElement.dataset.studioEdition !== 'friend';
    const unavailable = !['windows','edge','volc','online','local'].includes(source.peek().backend) || source.peek().backend === 'local' && !local;
    el('voice-settings').hidden = !local;
    el('voice-fields').disabled = !local || !initialized;
    for (const field of document.querySelectorAll('.lightweight-voice input,.lightweight-voice select')) field.disabled = !initialized;
    ToolWorkspace.updateSubmit(el('submit'), {ready:initialized, submitting, blocked:unavailable, jobs, draft,
      blockedLabel:'请先选择可用的配音来源', label:source.options().subtitles ? '生成配音与字幕' : '生成配音', pendingLabel:'这段配音正在生成', newLabel:'生成新配音'});
    el('output-summary').textContent = unavailable ? '原音色不会自动替换' : local ? '使用本次本地音色参数' : source.options().subtitles ? '声音 + 同步字幕' : '仅生成声音';
  }
  el('tool-form').addEventListener('submit', async event => {
    event.preventDefault(); if (el('submit').disabled) return;
    submitting = true; el('submit').disabled = true; el('action-help').hidden = true;
    try {
      await Promise.all([Creation.ready,source.ready]);
      const text = el('text').value;
      if (!text.trim()) { el('text').focus(); throw Error('请填写配音文本。'); }
      const choice = source.value(), signature = draft.signature();
      const payload = choice.backend === 'local' ? {text,backend:'local',settings:Creation.read()} : {text,...choice,...source.options()};
      const result = await Creation.api('/api/speech',payload);
      el('result').dataset.error = 'false'; el('result').textContent = ''; jobs.submitted(result.job_id,signature);
    } catch (error) {
      el('result').dataset.error = 'true'; el('result').textContent = error.message;
      const backend = source.peek().backend;
      if (['online','volc','local'].includes(backend)) {
        const unavailable = backend === 'local' && document.documentElement.dataset.studioEdition === 'friend';
        el('action-help').replaceChildren(link(unavailable ? '选择可用音色 →' : backend === 'local' ? '检查本地模型 →' : '检查语音服务与字幕配置 →',unavailable ? '/voices' : backend === 'local' ? '/models' : '/settings?service=tts'));
        el('action-help').hidden = false;
      }
    } finally { submitting = false; describe(); }
  });
  el('tool-form').addEventListener('input',describe); el('tool-form').addEventListener('change',describe);
  document.addEventListener('speech-source-change',describe);
  describe();
  Promise.all([Creation.ready,source.ready,window.SpeechPresetsReady]).then(() => {
    draft.initialize(); initialized = true; source.refresh(); describe();
    draft.acceptHandoff(['engine','preset','backend','voice_id']);
    document.dispatchEvent(new Event('tool-draft-change'));
  }).catch(error => {
    draft.unavailable(); describe();
    el('result').textContent = '无法完成载入：'+error.message.replace(/[。.!！]+$/,'')+'。文本仍保留。'; el('result').dataset.error='true';
    if (explicitSource) { el('action-help').replaceChildren(link('返回配音，重新选择来源 →','/speech')); el('action-help').hidden=false; }
  });
})();
