/* Named presets fill the existing per-task voice controls without saving defaults. */
(()=>{
 'use strict';
 const host=document.querySelector('[data-creation="voice"]');if(!host)return;
 const box=document.createElement('div'),label=document.createElement('label'),select=document.createElement('select'),toolbar=document.createElement('div'),save=document.createElement('button'),libraryLink=document.createElement('a'),status=document.createElement('p');
 label.textContent='题材音色预设';select.id='speech-voice-preset';select.append(new Option('当前参数 / 自定义',''));label.htmlFor=select.id;label.append(select);save.type='button';save.textContent='将当前参数保存为音色预设';libraryLink.textContent='打开音色库';libraryLink.href='/voices';libraryLink.style.marginLeft='12px';toolbar.append(save,libraryLink);status.className='small';status.setAttribute('role','status');box.id='local-voice-presets';box.append(label,toolbar,status);host.before(box);
 let presets=[];
 function apply(id){const preset=presets.find(item=>item.id===id);if(!preset){if(id)throw Error('该音色预设不存在，请重新选择。');return}if(preset.available===false)throw Error('该预设需要先在音色库修复：'+preset.error);const config=Creation.read();config.voice={...config.voice,...preset.voice};Creation.set(config);select.value=id;document.getElementById('backend').value='local';document.getElementById('backend').dispatchEvent(new Event('change'));status.textContent='已带入「'+preset.name+'」的参考音色与调音参数。修改只影响本次配音。'}
 select.onchange=()=>{try{if(select.value)apply(select.value);else status.textContent='继续使用当前参数，可以在下方自由调整。'}catch(error){status.textContent=error.message}};
 document.addEventListener('input',event=>{if(event.target?.dataset?.group==='voice'){select.value='';status.textContent='已调整本次参数，可另存为新的音色预设。'}});
 document.addEventListener('voices-updated',()=>{select.value='';status.textContent='新参考声音已选中，调整并试听后可保存为音色预设。'});
 save.onclick=async()=>{try{await Creation.ready;StudioStorage.session.setItem('voice-library-from-speech',JSON.stringify(Creation.read().voice));location.assign('/voices?from=speech')}catch(error){status.textContent='无法带入参数：'+error.message}};
 const query=new URLSearchParams(location.search),requested=query.get('preset'),requestedEngine=query.get('engine');
 if(document.documentElement.dataset.studioEdition==='friend'){
  box.hidden=true;
  window.SpeechPresetsReady=requested||requestedEngine?Promise.reject(Error('此音色需要本地模型，请返回配音选择系统或在线来源。')):Promise.resolve();
  window.SpeechPresetsReady.catch(()=>{});return;
 }
 if(requested||requestedEngine)document.getElementById('submit').disabled=true;
 window.SpeechPresetsReady=Promise.all([Creation.ready,Creation.api('/api/voice-library')]).then(([,data])=>{presets=data.presets;for(const preset of presets)select.append(new Option(preset.name,preset.id));if(requested)apply(requested);else if(requestedEngine){if(!['index-tts','qwen3-custom','qwen3-design','qwen3-clone'].includes(requestedEngine))throw Error('未知本地声音引擎');let transferred=null;try{transferred=JSON.parse(StudioStorage.session.getItem('voice-library-to-speech')||'null')}catch{}const config=Creation.read();config.voice={...config.voice,...(transferred?.engine===requestedEngine?transferred:{}),engine:requestedEngine};if(requestedEngine==='qwen3-design')config.voice.reference='';Creation.set(config);StudioStorage.session.removeItem('voice-library-to-speech');document.getElementById('backend').value='local';document.getElementById('backend').dispatchEvent(new Event('change'));status.textContent=requestedEngine==='qwen3-design'?'已带入声音设计参数。填写试听台词，成功后可保存为固定角色音色。':'已选择本地声音引擎，请先生成简短试听。'}}).catch(error=>{status.textContent='音色预设读取失败：'+error.message;if(requested||requestedEngine)throw error}).finally(()=>{if((requested||requestedEngine)&&!document.body.dataset.speechWorkspace)document.getElementById('submit').disabled=false});
})();
