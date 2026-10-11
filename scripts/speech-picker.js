/* Shared voice source picker. Local and online settings remain independent. */
(() => {
  'use strict';
  const make = (tag,text) => { const node=document.createElement(tag); if(text)node.textContent=text; return node; };
  const friend=document.documentElement.dataset.studioEdition==='friend';
  const managed=document.body.dataset.speechWorkspace==='true';
  const hints={
    windows:'使用电脑已安装的基础音色，离线生成旁白与字幕，无需下载模型。',
    edge:'免密钥联网；文字发送到微软语音服务，同时生成旁白与字幕。',
    volc:'使用已保存的账号和音色，按服务商计费。',
    online:'按服务商计费；生成字幕还需配置支持逐词时间戳的识别接口。',
    local:'使用独立安装的本地模型，在下方设置角色预设、声音设计或参考克隆。'
  };
  async function api(path,data) {
    const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const value=await response.json(); if(!response.ok)throw Error(value.error||'请求失败'); return value;
  }
  function picker(host,existing) {
    let settings={},choice={backend:'windows',voice_id:''},ready=false;
    const remembered={};
    const box=make('div');box.className='lightweight-voice';
    const grid=make('div');grid.className='speech-source-grid';
    const backend=existing||make('select');backend.replaceChildren();
    for(const [name,rows] of [['本地运行',[['windows','Windows 系统语音 · CPU'],['local','本地语音模型 · 高级声线']]],['在线服务',[['edge','Edge · 免密钥联网'],['volc','火山引擎 · 豆包'],['online','OpenAI 兼容语音接口']]]]) {
      const group=make('optgroup');group.label=name;
      for(const [value,label]of rows) {const option=new Option(label,value);if(value==='local'&&friend){option.disabled=true;option.textContent+=' · 完整版';}group.append(option);}
      backend.append(group);
    }
    if(!existing){const label=make('label','配音来源');label.append(backend);grid.append(label);}
    else if(managed)grid.append(existing.closest('label'));
    const voiceHost=make('label','音色');grid.append(voiceHost);
    const note=make('p');note.className='speech-source-note';
    const links=make('div');links.className='speech-source-links';
    for(const [label,url]of [friend?['管理音色','/voices']:['管理本地模型','/models'],['配置在线语音','/settings?service=tts']]){const a=make('a',label);a.href=url;links.append(a);}
    box.append(grid,note,links);host.append(box);
    function refresh() {
      backend.value=choice.backend;
      const unavailable=!Object.hasOwn(hints,choice.backend)||(friend&&choice.backend==='local');
      note.textContent=unavailable?'原配音来源在当前版本不可用，请明确选择新的来源后生成。':hints[choice.backend];
      voiceHost.replaceChildren(make('span','音色'));voiceHost.hidden=choice.backend==='local';
      const list=settings[choice.backend]?.voices;
      let voice;
      if(list) {
        voice=make('select');voice.setAttribute('aria-label','配音音色');
        for(const item of list)voice.append(new Option(item.label,item.id));
        if(!choice.voice_id)choice.voice_id=settings[choice.backend].default_voice||'';
        if(choice.voice_id&&!list.some(v=>v.id===choice.voice_id)) {
          const missing=new Option('原音色不可用，请重新选择',choice.voice_id);missing.disabled=true;voice.append(missing);
        }
        if(!list.length&&!choice.voice_id)voice.append(new Option('暂无可用音色',''));
        voice.value=choice.voice_id;
      } else {
        voice=make('input');voice.setAttribute('aria-label','配音音色');voice.maxLength=200;voice.placeholder='跟随已保存的服务音色';voice.value=choice.voice_id||'';
      }
      voice.oninput=()=>{choice.voice_id=voice.value;remembered[choice.backend]=voice.value;};
      voiceHost.append(voice);
      document.querySelectorAll('.voice-setup,.scene-voice-grid,#local-voice-presets,[data-creation="voice"]').forEach(node=>{node.hidden=choice.backend!=='local'||unavailable;});
      document.dispatchEvent(new CustomEvent('speech-source-change',{detail:choice.backend}));
    }
    function set(value) {
      const requested=value?.backend||'windows';
      // Imported projects keep their requested source until the user changes it.
      // In particular, a friend build must not silently turn a local voice into CPU speech.
      choice={backend:requested,voice_id:value?.voice_id||''};refresh();
    }
    backend.onchange=()=>{remembered[choice.backend]=choice.voice_id;set({backend:backend.value,voice_id:remembered[backend.value]||''});};
    const promise=api('/api/speech/options').then(options=>{settings=options;ready=true;refresh();}).catch(error=>{note.textContent='无法读取语音设置：'+error.message;throw error;});
    refresh();
    return {
      ready:promise,
      value(){
        if(!ready)throw Error('正在读取语音配置，请稍候。');
        if(!Object.hasOwn(hints,choice.backend)||(friend&&choice.backend==='local'))throw Error('原配音来源在当前版本不可用，请明确选择新的来源。');
        const list=settings[choice.backend]?.voices;
        if(list&&!list.some(v=>v.id===choice.voice_id))throw Error('所选音色不可用，请重新选择音色或配音来源。');
        return {...choice};
      },
      peek:()=>({...choice}),set,refresh
    };
  }
  if(location.pathname==='/whiteboard') {
    const target=document.querySelector('.voice-setup');if(!target)return;
    const box=make('div');target.before(box);window.WhiteboardSpeech=picker(box);window.WhiteboardSpeech.ready.catch(()=>{});
  }
  if(location.pathname==='/speech') {
    const backend=document.getElementById('backend'),submit=document.getElementById('submit');if(!backend)return;
    const oldSubmit=submit.onclick,box=make('div');backend.parentElement.after(box);
    const choice=picker(box,backend),params=new URLSearchParams(location.search);
    choice.set({backend:params.get('engine')||params.get('preset')?'local':params.get('backend')||'windows',voice_id:params.get('voice_id')||''});
    const extra=make('div');extra.className='speech-source-grid';
    const speedLabel=make('label','语速'),speed=make('select');speed.setAttribute('aria-label','轻量配音语速');
    for(const [value,label]of [['0.9','0.9 × 舒缓'],['1','1.0 × 自然'],['1.1','1.1 × 紧凑'],['1.2','1.2 × 轻快']])speed.append(new Option(label,value));
    speed.value='1';speedLabel.append(speed);
    const checkLabel=make('label','同时生成字幕'),check=make('input');check.type='checkbox';check.checked=true;check.style.width='auto';checkLabel.prepend(check);
    extra.append(speedLabel,checkLabel);
    const outputSettings=make('details'),outputSummary=make('summary');outputSettings.className='tool-details';extra.classList.add('detail-content');outputSettings.append(outputSummary,extra);
    if(managed)document.querySelector('.tool-submit').after(outputSettings);else box.append(outputSettings);
    function describe() {outputSettings.hidden=choice.peek().backend==='local';outputSummary.textContent=`语速与字幕 · ${Number(speed.value)} × · ${check.checked?'同时生成字幕':'仅生成音频'}`;if(!managed)submit.textContent=choice.peek().backend==='local'?'生成本地配音':'生成配音'+(check.checked?'与字幕':'');}
    document.addEventListener('speech-source-change',describe);check.onchange=describe;speed.addEventListener('change',describe);
    window.SpeechSource={
      ...choice,options:()=>({speed:Number(speed.value),subtitles:check.checked}),
      setOptions(value){if(['0.9','1','1.1','1.2'].includes(String(value?.speed)))speed.value=String(value.speed);if(typeof value?.subtitles==='boolean')check.checked=value.subtitles;describe();}
    };
    // Legacy markup keeps its handler; the workspace owns form validation and jobs.
    if(!managed)submit.onclick=async()=>{
      if(backend.value==='local')return oldSubmit?.();
      submit.disabled=true;
      try{await choice.ready;const result=await api('/api/speech',{...choice.value(),text:document.getElementById('text').value,speed:Number(speed.value),subtitles:check.checked});document.getElementById('result').textContent='已提交配音任务：'+result.job_id;if(typeof poll==='function')poll();}
      catch(error){document.getElementById('result').textContent=error.message;}
      finally{submit.disabled=false;}
    };
    choice.ready.then(()=>choice.refresh()).catch(()=>{});describe();
  }
})();
