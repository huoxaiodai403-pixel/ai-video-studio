/* Music requests and stable task players; no model calls occur during status checks. */
(() => {
  const el = id => document.getElementById(id);
  const templates = {
    calm: { bpm: 72, prompt: 'Calm narration background music, soft felt piano, warm ambient pads, restrained steady rhythm, spacious arrangement, subtle dynamics, leave space for clear spoken narration.' },
    suspense: { bpm: 68, prompt: 'Restrained investigative documentary background music, subtle low synth pulses, muted piano notes, slow measured tension, sparse arrangement, no sudden stingers or dramatic crescendos, leave space for spoken narration.' },
    science: { bpm: 96, prompt: 'Light and curious science explainer background music, gentle plucked strings, soft mallets, clean understated percussion, warm and playful but not distracting, consistent dynamics, leave space for spoken narration.' },
    transition: { sfx: true, duration: 3, prompt: 'A single soft airy whoosh for a gentle scene transition, short smooth rise and a clean quiet tail, close and detailed, no speech, no music.' },
    paper: { sfx: true, duration: 5, prompt: 'Close-up sound of one paper page being turned by hand, delicate dry paper rustling and a soft touch as the page settles, quiet room, no speech, no music.' },
    ambience: { sfx: true, duration: 10, prompt: 'Quiet outdoor ambience, a gentle breeze rustling tree leaves with a few distant birds, steady natural background texture, no people, no speech, no music.' }
  };
  const instrumental = 'Instrumental only. No vocals, no singing, no lyrics.';
  const MUSIC = 'ace-step-1.5', SFX = 'stable-audio-3-sfx', draftKey = 'ai-video-audio-drafts-v2';
  const drafts = { [MUSIC]: { prompt: templates.calm.prompt, duration: '30', bpm: '72', seed: '42' }, [SFX]: { prompt: templates.paper.prompt, duration: '5', seed: '42' } };
  let activeEngine = MUSIC;
  let engines = [], checking = false, submitting = false, polling = false;
  const rows = new Map();

  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let data; try { data = await response.json(); } catch (_) { throw Error('服务没有返回可识别的数据，请稍后重新检查。'); }
    if (!response.ok) throw Error(data.error || '请求失败');
    return data;
  }
  function persist() { drafts[activeEngine] = { prompt: el('prompt').value, duration: el(activeEngine === SFX ? 'sfx-duration' : 'duration').value, seed: el('seed').value }; if (activeEngine === MUSIC) drafts[MUSIC].bpm = el('bpm').value; try { localStorage.setItem(draftKey, JSON.stringify({ engine: activeEngine, drafts })); } catch (_) {} }
  function restoreEngine(engine) { activeEngine = engine; const draft = drafts[engine]; el('prompt').value = draft.prompt; el(engine === SFX ? 'sfx-duration' : 'duration').value = draft.duration; el('seed').value = draft.seed; if (engine === MUSIC) el('bpm').value = draft.bpm; renderMode(); }
  function renderMode() { const sfx = activeEngine === SFX; el('prompt').maxLength = sfx ? 1000 : 1900; el('music-heading').textContent = sfx ? '生成 CPU 本地短音效' : '生成无歌词纯音乐'; el('mode-note').textContent = sfx ? '描述一种声音的来源、动作与环境。音效不使用 BPM，不会自动附加配乐提示。生成后先试听确认。' : '配乐模式为无歌词纯音乐，提交时会加入无歌声要求。生成结果仍需试听，确认不会干扰旁白。'; el('music-templates').hidden = sfx; el('sfx-templates').hidden = !sfx; el('music-duration-label').hidden = sfx; el('sfx-duration-label').hidden = !sfx; el('bpm-label').hidden = sfx; el('prompt-label').textContent = sfx ? '音效描述' : '音乐描述'; el('template-note').textContent = sfx ? '点击音效模板会填入描述和建议秒数，可编辑为 1–15 秒。' : '点击模板会填入音乐描述和节拍速度，可继续编辑。'; el('generate').textContent = sfx ? '生成 CPU 音效' : '生成本地配乐'; }
  function applyTemplate(name) { const template = templates[name]; if (!template || Boolean(template.sfx) !== (activeEngine === SFX)) return; el('prompt').value = template.prompt; if (template.sfx) el('sfx-duration').value = template.duration; else el('bpm').value = template.bpm; persist(); el('result').textContent = template.sfx ? '已载入音效描述与时长，可编辑后生成。' : '已载入模板描述与 BPM，可编辑后生成。'; }
  function changeEngine() { const next = el('engine').value; if (![MUSIC, SFX].includes(next)) return; if (next !== activeEngine) { persist(); restoreEngine(next); persist(); } updateEngine(); }
  function updateEngine() {
    const current = engines.find(engine => engine.id === el('engine').value);
    el('engine-status').textContent = current ? current.ready ? '本地引擎检查通过，可以提交试生成。' : '引擎尚未就绪，请完成安装后重新检查。' : '当前服务尚未提供所选引擎，请完成后端更新后重新检查。';
    el('engine-details').replaceChildren();
    for (const text of current?.details || []) { const item = document.createElement('li'); item.textContent = text; el('engine-details').append(item); }
    el('generate').disabled = !current?.ready || submitting || checking;
  }
  async function checkEngine() {
    if (checking) return; checking = true; el('refresh-engine').disabled = true; el('generate').disabled = true;
    el('engine-status').textContent = '正在检查本地引擎…';
    try { const data = await api('/api/music'); engines = (data.engines || []).filter(engine => [MUSIC, SFX].includes(engine.id)); el('engine').replaceChildren(); for (const engine of engines) el('engine').append(new Option(engine.name, engine.id)); if (!engines.some(engine => engine.id === activeEngine)) el('engine').append(new Option((activeEngine === SFX ? 'Stable Audio 3 · CPU 音效' : 'ACE-Step 1.5 · 配乐') + ' · 当前服务未提供', activeEngine)); el('engine').value = activeEngine; el('engine').disabled = !engines.length; if (!engines.length) el('engine-status').textContent = '当前服务没有提供音频引擎，请完成后端更新后重新检查。'; }
    catch (error) { engines = []; el('engine-details').replaceChildren(); el('engine').disabled = true; el('engine-status').textContent = '引擎检查失败：' + error.message; }
    finally { checking = false; el('refresh-engine').disabled = false; if (engines.length) updateEngine(); else el('generate').disabled = true; }
  }
  function request() {
    const engine = engines.find(item => item.id === el('engine').value);
    if (!engine?.ready) throw Error('所选音频引擎尚未就绪，请先重新检查。');
    const sfx = engine.id === SFX, prompt = el('prompt').value.trim(), duration_seconds = Number(el(sfx ? 'sfx-duration' : 'duration').value), bpm = Number(el('bpm').value), seed = Number(el('seed').value);
    const promptLimit = sfx ? 1000 : 1900;
    if (prompt.length < 5 || prompt.length > promptLimit || prompt.includes('\u0000')) throw Error('请填写 5–'+promptLimit+' 字的声音描述，不可包含空字符，或选择一个模板。');
    if (sfx ? !Number.isInteger(duration_seconds) || duration_seconds < 1 || duration_seconds > 15 : ![30, 45, 60].includes(duration_seconds)) throw Error(sfx ? '音效时长必须是 1–15 秒的整数。' : '请选择 30、45 或 60 秒。');
    if (!sfx && (!Number.isInteger(bpm) || bpm < 40 || bpm > 180)) throw Error('BPM 必须是 40–180 的整数。');
    if (!el('seed').value.trim() || !Number.isInteger(seed) || seed < 0 || seed > 2147483647) throw Error('随机种子必须是 0–2147483647 的整数。');
    return sfx ? { engine: engine.id, prompt, duration_seconds, seed } : { engine: engine.id, prompt: prompt + '\n' + instrumental, duration_seconds, bpm, seed };
  }
  async function submit() {
    if (submitting) return;
    try { const body = request(); submitting = true; updateEngine(); persist(); el('result').textContent = '正在提交音频任务…'; const data = await api('/api/music', body); el('result').textContent = '已提交：' + data.job_id + '。实际进度见下方任务卡。'; await poll(); }
    catch (error) { el('result').textContent = error.message; }
    finally { submitting = false; updateEngine(); }
  }
  function outputUrl(value) { if (!value) return ''; try { const url = new URL(value, location.origin); return url.origin === location.origin && url.pathname.startsWith('/outputs/') ? url.href : ''; } catch (_) { return ''; } }
  function makeRow(id) {
    const box = document.createElement('article'), title = document.createElement('h3'), status = document.createElement('p'), error = document.createElement('p'), media = document.createElement('div'), actions = document.createElement('div'), pathLabel = document.createElement('label'), path = document.createElement('input'), copy = document.createElement('button'), note = document.createElement('p');
    box.className = 'music-job'; box.dataset.jobId = id; title.textContent = id; status.className = 'job-status'; error.className = 'job-error'; actions.className = 'music-actions'; pathLabel.textContent = '音频文件完整路径'; path.readOnly = true; path.setAttribute('aria-label', id + ' 音频文件完整路径'); pathLabel.append(path); pathLabel.hidden = true; copy.type = 'button'; copy.className = 'secondary'; copy.textContent = '复制音频路径'; copy.hidden = true; note.className = 'small'; note.setAttribute('role', 'status');
    copy.onclick = async () => { try { if (!navigator.clipboard?.writeText) throw Error('clipboard unavailable'); await navigator.clipboard.writeText(path.value); note.textContent = '已复制。在长片素材登记中选择“音频”并导入此路径。'; } catch (_) { path.focus(); path.select(); note.textContent = '浏览器未允许自动复制，路径已选中，请按 Ctrl+C。'; } };
    actions.append(copy); box.append(title, status, error, media, actions, pathLabel, note);
    return { box, status, error, media, actions, pathLabel, path, copy, note, audioUrl: '', metadataUrl: '' };
  }
  function updateRow(row, id, job) {
    const names = { queued: '排队中', running: '生成中', done: '已完成', error: '失败' };
    const seconds = Number(job.duration_seconds), duration = Number.isFinite(seconds) && seconds > 0 ? ` · ${Number(seconds.toFixed(2))} 秒` : '';
    row.status.textContent = (job.engine === SFX ? 'CPU 音效 · ' : '本地配乐 · ') + (names[job.status] || job.status) + (job.phase ? ' · ' + job.phase : '') + duration;
    row.error.textContent = job.error || ''; row.error.hidden = !job.error;
    const audioUrl = outputUrl(job.audio);
    if (audioUrl && row.audioUrl !== audioUrl) {
      if (!row.audio) { row.audio = document.createElement('audio'); row.audio.controls = true; row.audio.preload = 'metadata'; row.audio.setAttribute('aria-label', id + ' 音频试听'); row.media.append(row.audio); }
      row.audio.src = audioUrl; row.audioUrl = audioUrl;
      if (!row.download) { row.download = document.createElement('a'); row.download.textContent = job.engine === SFX ? '下载音效 WAV' : '下载配乐 WAV'; row.actions.append(row.download); }
      row.download.href = audioUrl; row.download.download = id + '.wav';
    }
    const metadataUrl = outputUrl(job.metadata);
    if (metadataUrl && row.metadataUrl !== metadataUrl) { if (!row.metadata) { row.metadata = document.createElement('a'); row.metadata.textContent = '下载生成参数'; row.actions.append(row.metadata); } row.metadata.href = metadataUrl; row.metadata.download = id + '.json'; row.metadataUrl = metadataUrl; }
    if (job.audio_path) { row.path.value = job.audio_path; row.pathLabel.hidden = false; row.copy.hidden = false; }
  }
  async function poll() {
    if (polling) return; polling = true;
    try {
      const data = await api('/api/jobs'), jobs = Object.entries(data).filter(([, job]) => job.kind === 'music').sort((a, b) => (b[1].created || 0) - (a[1].created || 0));
      if (jobs.length) el('jobs-empty').hidden = true;
      for (let index = 0; index < jobs.length; index++) { const [id, job] = jobs[index]; let row = rows.get(id); if (!row) { row = makeRow(id); rows.set(id, row); const next = jobs.slice(index + 1).find(([nextId]) => rows.has(nextId)); el('jobs').insertBefore(row.box, next ? rows.get(next[0]).box : null); } updateRow(row, id, job); }
      el('jobs-status').textContent = '';
    } catch (error) { el('jobs-status').textContent = '任务刷新失败：' + error.message + '。已有试听继续保留。'; }
    finally { polling = false; }
  }
  async function services() { try { const data = await api('/api/services'); el('services').textContent = `千问生图：${data.comfyui.ready ? '就绪' : '未启动'} · 配音：${data.tts.ready ? '就绪' : data.tts.starting ? '正在加载' : '未启动'}`; } catch (_) { el('services').textContent = '暂时无法连接服务状态'; } }

  try { const saved = JSON.parse(localStorage.getItem(draftKey) || 'null'); if (saved?.drafts) { for (const engine of [MUSIC, SFX]) { const draft = saved.drafts[engine]; if (draft && typeof draft.prompt === 'string') for (const key of ['prompt', 'duration', 'bpm', 'seed']) if (typeof draft[key] === 'string' || typeof draft[key] === 'number') drafts[engine][key] = String(draft[key]); } if ([MUSIC, SFX].includes(saved.engine)) activeEngine = saved.engine; } else { const legacy = JSON.parse(localStorage.getItem('ai-video-music-draft-v1') || 'null'); if (legacy && typeof legacy.prompt === 'string') for (const key of ['prompt', 'duration', 'bpm', 'seed']) if (typeof legacy[key] === 'string' || typeof legacy[key] === 'number') drafts[MUSIC][key] = String(legacy[key]); } } catch (_) {}
  restoreEngine(activeEngine);
  el('result').textContent = '';
  for (const button of document.querySelectorAll('[data-template]')) button.onclick = () => applyTemplate(button.dataset.template);
  for (const id of ['prompt', 'duration', 'sfx-duration', 'bpm', 'seed']) el(id).addEventListener('input', persist);
  el('generate').onclick = submit; el('refresh-engine').onclick = checkEngine; el('engine').onchange = changeEngine;
  checkEngine(); poll(); services(); setInterval(poll, 6000); setInterval(services, 15000);
})();
