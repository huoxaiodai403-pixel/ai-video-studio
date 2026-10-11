/* Short video, transcription and enhancement keep one input snapshot and result. */
(() => {
  'use strict';
  const {el, make, link, mediaURL, reveal, draft:localDraft, jobs:jobView, sources} = ToolWorkspace;
  const kind = document.body.dataset.tool, motion = kind === 'motion', asr = kind === 'subtitles';
  const friend = document.documentElement.dataset.studioEdition === 'friend';
  const sourceField = el(motion ? 'image' : asr ? 'audio' : 'source-path');
  const fields = motion ? ['motionPrompt','image','backend'] : asr ? ['audio','backend'] : ['source-path','sr','quality','factor','resolution','codec','bitrate','nr'];
  let initialized = !motion, submitting = false, previewKey = '', importedPreview = null, cancelJob = '', cancelPending = false;
  function values() { return Object.fromEntries(fields.map(id => [id,el(id).type === 'checkbox' ? el(id).checked : el(id).value])); }
  function capture() { return {...values(), ...(motion && initialized ? {motion:Creation.read().motion, preview:importedPreview} : {})}; }
  function restore(saved) {
    for (const id of fields) if (typeof saved[id] === 'string' || typeof saved[id] === 'boolean') {
      if (el(id).type === 'checkbox') el(id).checked = saved[id]; else el(id).value = saved[id];
    }
    if (motion && saved.motion) Creation.set({...Creation.read(),motion:{...Creation.read().motion,...saved.motion}});
    if (motion && saved.preview) importedPreview = saved.preview;
  }
  const draft = localDraft(kind,capture,restore,values);
  // Paths and text remain editable while model settings load.
  if (draft.state.data) for (const id of fields) if (typeof draft.state.data[id] === 'string' || typeof draft.state.data[id] === 'boolean') {
    if (el(id).type === 'checkbox') el(id).checked = draft.state.data[id]; else el(id).value = draft.state.data[id];
  }
  function feedback(text, error = false) { el('result').textContent = text; el('result').dataset.error = String(error); }
  function describe() {
    if (motion) {
      el('text-count').textContent = el('motionPrompt').value.length + ' / 5000 字';
      el('source-summary').textContent = sourceField.value.trim() ? '已选择首帧' : friend ? '可选 · 从资源库选择' : '可选 · A14B 必填';
      const local = el('backend').value === 'local'; el('motion-settings').hidden = !local || friend;
      if (initialized) { const m = Creation.read().motion; el('settings-summary').textContent = `${m.width} × ${m.height} · ${(m.frames/m.fps).toFixed(1)} 秒`; el('output-summary').textContent = local ? friend ? '请选择在线服务；原本地设置仍保留' : el('settings-summary').textContent : '请求 4 秒 · 按在线服务配置生成'; }
    }
    ToolWorkspace.updateSubmit(el('submit'), {ready:initialized, submitting, jobs, draft,
      blocked:friend && (!motion && !asr || el('backend').value === 'local'),
      label:motion?'生成短镜头':asr?'识别语音并生成字幕':'开始增强',
      pendingLabel:motion?'这个镜头正在生成':asr?'这份录音正在识别':'这段视频正在增强',
      newLabel:motion?'生成新镜头':asr?'识别新的录音':'增强新的视频'});
    if ((motion || asr) && friend && el('backend').value === 'local') feedback('草稿保留了本地引擎。请选择在线服务后提交，原参数仍保留。',true);
  }
  function sourcePreview(item) {
    const imported = importedPreview?.path === sourceField.value.trim() ? importedPreview.url : '';
    let url = mediaURL(item?.preview_url || imported);
    if (!url && imported) { try { const p = new URL(imported,location.origin); if (p.origin === location.origin && p.pathname === '/api/image-references/preview') url = p.href; } catch {} }
    const key = JSON.stringify([url,item?.media_type]);
    if (key !== previewKey) {
      previewKey = key; el('source-preview').replaceChildren();
      if (url) { const type = motion ? 'img' : item?.media_type === 'video' ? 'video' : 'audio'; const media = make(type); media.src = url; if (type === 'img') media.alt = '本次首帧'; else { media.controls = true; media.preload = 'metadata'; } el('source-preview').append(media); }
    }
    el('source-preview').hidden = !url;
    if (!motion && !asr) {
      const href = '/video-tools?' + new URLSearchParams({skill:'ffmpeg-skill', ...(item?.id ? {item:item.id} : sourceField.value.trim() ? {source:sourceField.value.trim()} : {})});
      el('edit-source').href = href; el('friend-edit').href = href;
    }
    describe();
  }
  const picker = sources({target:sourceField,kinds:motion ? ['image'] : asr ? ['audio','video'] : ['video'],
    accept:motion ? /\.(png|jpe?g|webp)$/i : asr ? /\.(wav|mp3|flac|m4a|mp4)$/i : /\.(mp4|mov|mkv|avi|webm)$/i,onSelect:sourcePreview});
  const jobs = jobView({kind:asr ? 'asr' : kind,draft,
    empty:motion ? '填写动作描述并生成，完成后在这里播放短镜头。' : asr ? '选择一段音视频，识别完成后在这里校对字幕。' : '选择原片并导出，完成后在这里对比播放。',
    render(id,job,view) {
      const video = mediaURL(job.video);
      if (video) { const player = make('video'); player.controls = true; player.preload = 'metadata'; player.src = video; player.setAttribute('aria-label','当前视频结果'); view.media.append(player); view.actions.append(link('下载视频',video,id+'.mp4')); }
      const subtitle = mediaURL(job.subtitle), transcript = mediaURL(job.transcript);
      if (subtitle) {
        const pre = make('pre','正在读取字幕…','subtitle-preview'); pre.tabIndex = 0; pre.setAttribute('aria-label','字幕内容预览'); view.media.append(pre);
        fetch(subtitle).then(async response => { if (!response.ok) throw Error('HTTP '+response.status); return (await response.text()).slice(0,200000); }).then(text => { if (pre.isConnected) pre.textContent = text || '字幕文件为空，请核对源音频后重试。'; }).catch(error => { if (pre.isConnected) pre.textContent = '字幕预览读取失败：'+error.message+'。可下载文件查看。'; });
        view.actions.append(link('下载字幕 SRT',subtitle,id+'.srt'));
      }
      if (transcript) view.actions.append(link('下载识别正文',transcript,id+'.json'));
    },
    update(id,job) {
      queueMicrotask(describe);
      if (motion || asr) return;
      if (cancelJob !== id) el('cancel-status').textContent = '';
      cancelJob = id; el('cancel-job').hidden = friend || job.status !== 'running'; el('cancel-job').disabled = cancelPending;
    }
  });
  el('tool-form').addEventListener('input',describe); el('tool-form').addEventListener('change',describe);
  el('tool-form').addEventListener('submit',async event => {
    event.preventDefault(); if (el('submit').disabled) return;
    submitting = true; describe(); el('action-help').hidden = true;
    try {
      let body;
      if (motion) {
        if (!el('motionPrompt').value.trim()) { reveal(el('motionPrompt')); throw Error('请填写动作描述。'); }
        const settings = Creation.read();
        if (el('backend').value === 'local' && settings.motion.engine === 'wan2.2-a14b' && !sourceField.value.trim()) { reveal(sourceField); throw Error('A14B 需要首帧图片，请从资源库选择或填写路径。'); }
        body = {backend:el('backend').value,prompt:el('motionPrompt').value,image:sourceField.value.trim(),settings};
      } else if (asr) body = {backend:el('backend').value,audio:sourceField.value.trim()};
      else body = {input:sourceField.value.trim(),sr:el('sr').value === 'on',quality:Number(el('quality').value),factor:Number(el('factor').value),resolution:el('resolution').value,codec:el('codec').value,bitrate:Number(el('bitrate').value),nr:el('nr').checked};
      const signature = draft.signature(); feedback('正在提交任务…');
      const result = await Creation.api(asr ? '/api/transcribe' : '/api/'+kind,body);
      feedback(''); jobs.submitted(result.job_id,signature);
    } catch (error) {
      feedback(error.message,true);
      if (motion || asr) { const online = el('backend').value === 'online'; el('action-help').replaceChildren(link(online ? '检查在线服务 →' : '检查本地模型 →',online ? '/settings?service='+(asr ? 'asr' : 'video') : '/models')); el('action-help').hidden = false; }
    } finally { submitting = false; describe(); }
  });
  if (motion) {
    el('tested-portrait').onclick = () => { const s = Creation.read(); Object.assign(s.motion,{width:480,height:640,frames:81,fps:16,steps:20}); Creation.set(s); draft.changed(); describe(); el('creation-status').textContent = '已填写本次参数，当前引擎与随机种子保留。'; };
    document.addEventListener('creation-settings-changed',describe); document.addEventListener('creation-engine-changed',describe);
    Creation.ready.then(() => {
      // Keep previously saved parameters even if the user typed during loading.
      if (draft.state.data?.motion) Creation.set({...Creation.read(),motion:{...Creation.read().motion,...draft.state.data.motion}});
      initialized = true; draft.initialize();
      const params = new URLSearchParams(location.search), image = params.get('image');
      const directed = StudioStorage.session.getItem('director-motion');
      if (directed) { el('motionPrompt').value = directed; StudioStorage.session.removeItem('director-motion'); feedback('已载入运镜描述，请核对首帧和生成参数。'); }
      if (image) {
        if (/^[A-Za-z]:[\\/]/.test(image)) { sourceField.value = image; importedPreview = {path:image,url:params.get('preview') || ''}; el('source-details').open = true; feedback('已载入首帧，请填写动作描述。'); }
        else feedback('首帧路径无效，请重新从图像或资源库选择。',true);
        const url = new URL(location.href); url.searchParams.delete('image'); url.searchParams.delete('preview'); history.replaceState(null,'',url);
      }
      if (image || directed) draft.changed(); picker.sync(); describe();
    }).catch(error => { draft.unavailable(); feedback('参数未完成载入：'+error.message+'。文本仍保留，刷新后重试。',true); });
  } else {
    draft.initialize(); picker.sync();
    if (!asr) {
      el('enhance-friend').hidden = !friend; el('enhance-local').hidden = friend;
      if (friend) document.querySelector('.tool-heading p').textContent = '选择已有视频，继续调整尺寸与画幅。';
      if (!friend) Creation.api('/api/enhance').then(state => { el('engine-status').textContent = state.message; }).catch(error => { el('engine-status').textContent = '无法检查增强引擎：'+error.message; });
      el('open-veyra').onclick = async () => { el('open-veyra').disabled = true; try { feedback((await Creation.api('/api/enhance/open',{input:sourceField.value.trim()})).message); } catch(error) { feedback(error.message,true); } finally { el('open-veyra').disabled = false; } };
      el('cancel-job').onclick = async () => { if (cancelPending) return; const id=cancelJob; cancelPending=true; el('cancel-job').disabled=true; try { const result=await Creation.api('/api/enhance/cancel',{job_id:id}); if (cancelJob===id) el('cancel-status').textContent=result.message; jobs.poll(); } catch(error) { el('cancel-status').textContent=error.message; } finally { cancelPending=false; el('cancel-job').disabled=false; } };
    }
  }
  describe();
})();
