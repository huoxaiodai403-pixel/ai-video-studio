/* Shared source picker: local and online choices remain separate groups. */
(()=>{
 'use strict';
 const make=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n};
 async function api(path,data){const r=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}),value=await r.json();if(!r.ok)throw Error(value.error||'请求失败');return value}
 const hints={windows:'Windows 离线基础音色：不联网、不下载模型，CPU 即可。字幕来自本次合成的发声起点，词尾取下一词起点。',edge:'Edge 在线语音：无需密钥与显卡，文字发送到微软在线语音服务；音频与词级时间戳一起返回。',volc:'火山引擎：使用已保存的账号和音色，按服务商计费。音频与字幕时间戳来自同一次合成。',online:'OpenAI 兼容语音接口：按服务商计费。需要字幕时，还需配置支持逐词时间戳的识别接口。',local:'使用独立安装的本地模型。角色预设、声音设计和参考克隆参数在下方设置。'};
 function picker(host,existing){let settings={},choice={backend:'windows',voice_id:''},ready=false;
  const box=make('div');box.className='lightweight-voice';const grid=make('div');grid.className='speech-source-grid';const backend=existing||make('select');backend.replaceChildren();
  for(const [name,rows] of [['本地运行',[['windows','Windows 系统语音 · CPU'],['local','本地语音模型 · 高级声线']]],['在线服务',[['edge','Edge · 免密钥联网'],['volc','火山引擎 · 豆包'],['online','OpenAI 兼容语音接口']]]]){const group=make('optgroup');group.label=name;for(const [v,t]of rows)group.append(new Option(t,v));backend.append(group)}
  if(!existing){const label=make('label','配音来源');label.append(backend);grid.append(label)}const voiceHost=make('label','音色');grid.append(voiceHost);const note=make('p');note.className='speech-source-note';const links=make('div');links.className='speech-source-links';for(const [label,url]of [['管理本地模型','/models'],['配置在线语音','/settings?service=tts']]){const a=make('a',label);a.href=url;links.append(a)}box.append(grid,note,links);host.append(box);
  function refresh(){backend.value=choice.backend;note.textContent=hints[choice.backend];voiceHost.replaceChildren(make('span','音色'));voiceHost.hidden=choice.backend==='local';const list=settings.options?.[choice.backend]?.voices;
   let voice;if(list){voice=make('select');voice.setAttribute('aria-label','配音音色');for(const item of list)voice.append(new Option(item.label,item.id));if(!list.some(v=>v.id===choice.voice_id))choice.voice_id=settings.options[choice.backend].default_voice||'';voice.value=choice.voice_id;}else{voice=make('input');voice.setAttribute('aria-label','配音音色');voice.maxLength=200;voice.placeholder='跟随已保存的服务音色';voice.value=choice.voice_id||''}
   voice.oninput=()=>{choice.voice_id=voice.value};voiceHost.append(voice);document.querySelectorAll('.voice-setup,.scene-voice-grid,#local-voice-presets,[data-creation="voice"]').forEach(e=>{e.hidden=choice.backend!=='local'});document.dispatchEvent(new CustomEvent('speech-source-change',{detail:choice.backend}));
  }
  backend.onchange=()=>{choice={backend:backend.value,voice_id:''};refresh()};
  const promise=Promise.all([api('/api/speech/options'),api('/api/providers'),api('/api/volc-speech')]).then(([options,providers,volc])=>{settings={options,providers,volc};ready=true;refresh()}).catch(error=>{note.textContent='无法读取语音设置：'+error.message;throw error});
  refresh();return {ready:promise,value(){if(!ready)throw Error('正在读取语音配置，请稍候。');return {...choice}},peek:()=>({...choice}),set(value){choice={backend:value?.backend||'windows',voice_id:value?.voice_id||''};refresh()},refresh};
 }
 if(location.pathname==='/whiteboard'){
  const target=document.querySelector('.voice-setup');if(!target)return;const box=make('div');target.before(box);window.WhiteboardSpeech=picker(box);window.WhiteboardSpeech.ready.catch(()=>{});
 }
 if(location.pathname==='/speech'){
  const backend=document.getElementById('backend'),submit=document.getElementById('submit');if(!backend)return;const oldSubmit=submit.onclick,box=make('div');backend.parentElement.after(box);const choice=picker(box,backend);const params=new URLSearchParams(location.search);choice.set({backend:params.get('engine')||params.get('preset')?'local':params.get('backend')||'windows'});
  const extra=make('div');extra.className='speech-source-grid';const speedLabel=make('label','语速'),speed=make('select');speed.setAttribute('aria-label','轻量配音语速');for(const [v,t]of [['0.9','0.9 × 舒缓'],['1','1.0 × 自然'],['1.1','1.1 × 紧凑'],['1.2','1.2 × 轻快']])speed.append(new Option(t,v));speed.value='1';speedLabel.append(speed);const checkLabel=make('label','同时生成字幕'),check=make('input');check.type='checkbox';check.checked=true;check.style.width='auto';checkLabel.prepend(check);extra.append(speedLabel,checkLabel);box.append(extra);
  document.addEventListener('speech-source-change',e=>{extra.hidden=e.detail==='local';submit.textContent=e.detail==='local'?'按所选音色生成配音':'生成配音'+(check.checked?'与字幕':'')});check.onchange=()=>{submit.textContent='生成配音'+(check.checked?'与字幕':'')};
  submit.onclick=async()=>{if(backend.value==='local')return oldSubmit();submit.disabled=true;try{await choice.ready;const c=choice.value(),r=await api('/api/speech',{backend:c.backend,voice_id:c.voice_id,text:document.getElementById('text').value,speed:Number(speed.value),subtitles:check.checked});document.getElementById('result').textContent='已提交配音任务：'+r.job_id;if(typeof poll==='function')poll()}catch(error){document.getElementById('result').textContent=error.message}finally{submit.disabled=false}};
  choice.ready.then(()=>choice.refresh()).catch(()=>{});
 }
})();
