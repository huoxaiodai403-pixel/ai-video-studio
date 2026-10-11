/* Per-engine drafts and one stable audio player. */
(() => {
  'use strict';
  const templates = {
    calm: { bpm: 72, prompt: 'Calm narration background music, soft felt piano, warm ambient pads, restrained steady rhythm, spacious arrangement, subtle dynamics, leave space for clear spoken narration.' },
    suspense: { bpm: 68, prompt: 'Restrained investigative documentary background music, subtle low synth pulses, muted piano notes, slow measured tension, sparse arrangement, no sudden stingers or dramatic crescendos, leave space for spoken narration.' },
    science: { bpm: 96, prompt: 'Light and curious science explainer background music, gentle plucked strings, soft mallets, clean understated percussion, warm and playful but not distracting, consistent dynamics, leave space for spoken narration.' },
    transition: { sfx: true, duration: 3, prompt: 'A single soft airy whoosh for a gentle scene transition, short smooth rise and a clean quiet tail, close and detailed, no speech, no music.' },
    paper: { sfx: true, duration: 5, prompt: 'Close-up sound of one paper page being turned by hand, delicate dry paper rustling and a soft touch as the page settles, quiet room, no speech, no music.' },
    ambience: { sfx: true, duration: 10, prompt: 'Quiet outdoor ambience, a gentle breeze rustling tree leaves with a few distant birds, steady natural background texture, no people, no speech, no music.' }
  };

  const MUSIC='ace-step-1.5', SFX='stable-audio-3-sfx';
  const {el,make,link,mediaURL,draft:localDraft,jobs:jobView,sources,reveal}=ToolWorkspace;
  let reuse=true;
  let activeEngine=MUSIC, engines=[],checking=false,submitting=false;
  const drafts={ [MUSIC]:{prompt:templates.calm.prompt,duration:'30',bpm:'72',seed:'42'},[SFX]:{prompt:templates.paper.prompt,duration:'5',seed:'42'} };
  function stash(){ drafts[activeEngine]={prompt:el('prompt').value,duration:el(activeEngine===SFX?'sfx-duration':'duration').value,seed:el('seed').value,...(activeEngine===MUSIC?{bpm:el('bpm').value}:{})}; }
  function capture(){stash();return {mode:reuse?'reuse':'generate',engine:activeEngine,drafts:structuredClone(drafts),audio:el('audio-path').value};}
  function mode(){document.querySelector('.tool-heading p').textContent=reuse?'选择已有配乐或音效，试听后用于你的影片。':'制作纯音乐或短音效，试听后用于你的影片。';
    const sfx=activeEngine===SFX;el('prompt').maxLength=sfx?1000:1900;
    el('input-heading').textContent=reuse?'复用音频素材':sfx?'音效描述':'音乐描述';
    el('prompt-label').textContent=sfx?'音效描述':'音乐描述';el('mode-note').textContent=sfx?'描述一种声音的来源、动作与环境':'纯音乐 · 生成后先试听';
    el('music-templates').hidden=sfx;el('sfx-templates').hidden=!sfx;el('music-duration-label').hidden=sfx;el('sfx-duration-label').hidden=!sfx;el('bpm-label').hidden=sfx;el('bpm').disabled=sfx;el('sfx-duration').disabled=!sfx;
    queueMicrotask(submitState);
    el('template-note').textContent='模板会替换当前描述，可在生成前继续编辑。';
    el('text-count').textContent=el('prompt').value.length+' / '+(sfx?1000:1900)+' 字';
  }
  function restoreEngine(engine){activeEngine=engine;const d=drafts[engine];el('engine').value=engine;el('prompt').value=d.prompt;el(engine===SFX?'sfx-duration':'duration').value=d.duration;el('seed').value=d.seed;if(engine===MUSIC)el('bpm').value=d.bpm;mode();}
  function restore(saved){reuse=saved?.mode?saved.mode==='reuse':!saved?.drafts;el('audio-mode').value=reuse?'reuse':'generate';
    if(saved?.drafts)for(const engine of [MUSIC,SFX]){const d=saved.drafts[engine];if(d&&typeof d.prompt==='string')for(const key of ['prompt','duration','bpm','seed'])if(typeof d[key]==='string'||typeof d[key]==='number')drafts[engine][key]=String(d[key]);}
    restoreEngine([MUSIC,SFX].includes(saved?.engine)?saved.engine:MUSIC);if(typeof saved?.audio==='string')el('audio-path').value=saved.audio;
  }
  const draft=localDraft('music',capture,restore);
  restoreEngine(MUSIC);
  if(!draft.protected&&!draft.state.data){try{const old=JSON.parse(StudioStorage.local.getItem('ai-video-audio-drafts-v2')||'null');if(old?.drafts)draft.state.data=old;else{const legacy=JSON.parse(StudioStorage.local.getItem('ai-video-music-draft-v1')||'null');if(legacy?.prompt)draft.state.data={engine:MUSIC,drafts:{[MUSIC]:legacy}};}}catch{}}
  draft.initialize();
  function engineState(){
    const selected=engines.find(e=>e.id===activeEngine);submitState();
    el('output-summary').textContent=selected?.ready?'就绪 · '+(activeEngine===SFX?'本地 CPU 音效':'本地配乐'):'引擎未就绪 · 展开“引擎状态”查看';
    el('engine-status').textContent=selected?selected.ready?'组件文件检查通过，可以提交试生成。':'所选引擎尚未就绪，请完成安装后重新检查。':'当前服务未提供所选音频引擎。';
    el('engine-details').replaceChildren(...(selected?.details||[]).map(text=>make('li',text)));
  }
  function submitState(){ToolWorkspace.updateSubmit(el('generate'),{ready:!checking,submitting,blocked:reuse||!engines.find(e=>e.id===activeEngine)?.ready,jobs,draft,label:activeEngine===SFX?'生成 CPU 音效':'生成配乐',pendingLabel:'这段音频正在生成',newLabel:'生成新的音频'});}
  async function check(){if(checking||reuse)return;checking=true;el('refresh-engine').disabled=true;el('generate').disabled=true;el('output-summary').textContent='正在检查音频引擎…';try{const data=await Creation.api('/api/music');engines=data.engines||[];engineState();}catch(error){engines=[];engineState();el('engine-status').textContent='引擎检查失败：'+error.message;}finally{checking=false;el('refresh-engine').disabled=false;submitState();}}
  const jobs=jobView({kind:'music',draft,empty:reuse?'复用已有音频，或从近期任务中选择一份结果试听。':'描述想要的声音并生成，完成后在这里试听。',render(id,job,view){
    const audio=mediaURL(job.audio),metadata=mediaURL(job.metadata);if(audio){const title=make('p',job.engine===SFX?'听听这段音效':'听听这段配乐','audio-title'),player=make('audio');player.controls=true;player.preload='metadata';player.src=audio;player.setAttribute('aria-label','当前音频试听');view.media.append(title,player);view.actions.append(link('下载 WAV',audio,id+'.wav'));}
    if(metadata)view.actions.append(link('下载生成参数',metadata,id+'.json'));
    if(job.audio_path){const label=make('label','音频完整路径'),path=make('input'),copy=make('button','复制音频路径','secondary');path.value=job.audio_path;path.readOnly=true;label.className='result-path';label.append(path);copy.type='button';copy.onclick=async()=>{try{await navigator.clipboard.writeText(job.audio_path);view.note.textContent='已复制，可在调查长片的素材登记中导入。';}catch{path.focus();path.select();view.note.textContent='路径已选中，请按 Ctrl+C 复制。';}};view.media.append(label);view.actions.append(copy);}
  },update(id,job){el('job-state').title=job.phase||'';queueMicrotask(submitState);}});
  for(const button of document.querySelectorAll('[data-template]'))button.onclick=()=>{const t=templates[button.dataset.template];if(!t||Boolean(t.sfx)!==(activeEngine===SFX))return;el('prompt').value=t.prompt;if(t.sfx)el('sfx-duration').value=t.duration;else el('bpm').value=t.bpm;draft.changed();mode();el('result').textContent='已填入模板，可编辑后生成。';};
  el('engine').onchange=()=>{stash();restoreEngine(el('engine').value);draft.changed();engineState();};
  el('tool-form').addEventListener('input',mode);el('refresh-engine').onclick=check;
  el('tool-form').addEventListener('submit',async event=>{
    event.preventDefault();if(reuse||submitting||el('generate').disabled)return;
    try{
      const sfx=activeEngine===SFX,prompt=el('prompt').value.trim();if(prompt.length<5||prompt.length>(sfx?1000:1900)||prompt.includes('\0')){reveal(el('prompt'));throw Error('请填写 5–'+(sfx?1000:1900)+' 字的有效声音描述。');}
      const body={engine:activeEngine,prompt:sfx?prompt:prompt+'\nInstrumental only. No vocals, no singing, no lyrics.',duration_seconds:Number(el(sfx?'sfx-duration':'duration').value),seed:Number(el('seed').value)};if(!sfx)body.bpm=Number(el('bpm').value);
      const signature=draft.signature();submitting=true;engineState();el('result').dataset.error='false';el('result').textContent='正在提交音频任务…';
      const result=await Creation.api('/api/music',body);jobs.submitted(result.job_id,signature);el('result').textContent='';
    }catch(error){el('result').textContent=error.message;el('result').dataset.error='true';}finally{submitting=false;engineState();}
  });
  function showSource(){el('music-friend').hidden=!reuse;el('music-local').hidden=reuse;for(const field of el('music-local').querySelectorAll('input,select,textarea'))field.disabled=reuse;mode();if(!reuse){el('sfx-duration').disabled=activeEngine!==SFX;check()}}
  el('audio-mode').onchange=()=>{reuse=el('audio-mode').value==='reuse';showSource();draft.changed()};
  {
    document.querySelector('.tool-heading p').textContent='选择已有配乐或音效，试听后用于你的影片。';
    let previous='';sources({target:el('audio-path'),kinds:['audio'],onSelect:item=>{const url=mediaURL(item?.preview_url);if(previous===url)return;previous=url;el('source-preview').replaceChildren();el('source-preview').hidden=!url;if(url){const player=make('audio');player.src=url;player.controls=true;player.preload='metadata';el('source-preview').append(player);}}});
    el('copy-source').onclick=async()=>{const path=el('audio-path').value.trim();if(!path){el('friend-status').textContent='先选择音频或填写完整路径。';el('audio-path').focus();return;}try{await navigator.clipboard.writeText(path);el('friend-status').textContent='路径已复制，可到调查长片的素材登记中导入。';}catch{el('audio-path').focus();el('audio-path').select();el('friend-status').textContent='路径已选中，请按 Ctrl+C。';}};
  }
  showSource();
  mode();
})();
