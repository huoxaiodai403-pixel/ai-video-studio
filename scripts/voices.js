(() => {
 'use strict';
 const $=id=>document.getElementById(id),friend=document.documentElement.dataset.studioEdition==='friend';
 const node=(tag,text,cls)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(cls)item.className=cls;return item};
 const action=(label,callback,cls='secondary')=>{const button=node('button',label,cls);button.type='button';button.onclick=callback;return button};
 const link=(label,url,cls='secondary')=>{const anchor=node('a',label,'button '+cls);anchor.href=url;return anchor};
 const speakers=['Vivian','Serena','Uncle_Fu','Dylan','Eric','Ryan','Aiden','Ono_Anna','Sohee'];
 const languages=[['Chinese','中文'],['English','英语'],['Japanese','日语'],['Korean','韩语'],['German','德语'],['French','法语'],['Russian','俄语'],['Portuguese','葡萄牙语'],['Spanish','西班牙语'],['Italian','意大利语'],['Auto','自动识别']];
 let library={presets:[],references:[],emotions:['平静']},speech=null,libraryReady=false,loading=false,filterWasActive=false,builtinOpenBeforeFilter=false;
 let editor=null,fixedJob=null,opening=0,saving=false,fixedSaving=false;
 let memory={version:1},blocked=false,recoveryRaw=null;
 const cacheBase='ai-video-voices-v1-'+(document.documentElement.dataset.studioEdition||'development');
 let cacheKey=cacheBase;
 const fields=form=>Object.fromEntries([...$(form).querySelectorAll('input[id],select[id],textarea[id]')].map(field=>[field.id,field.value]));
 function status(message,error=false){$('library-status').textContent=message;$('library-status').className='status'+(error?' error':'')}
 function editorStatus(message,error=false,id='editor-status'){$(id).textContent=message+(blocked?' 浏览器草稿尚未保存；收起后可导出或启用独立草稿。':'');$(id).className='small'+(error?' error':'')}
 async function api(url,data){
  const response=await fetch(url,data===undefined?{signal:AbortSignal.timeout(15000)}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  let value;try{value=await response.json()}catch{throw Error('服务没有返回可读取的结果，请稍后重试。')}
  if(!response.ok)throw Object.assign(Error(value.error||'请求失败'),{conflict:!!value.conflict});return value;
 }
 function missingOption(select,value,label='原选项暂不可用：'){
  if(value&&!Array.from(select.options).some(option=>option.value===value))select.append(new Option(label+value,value));
  select.value=value;
 }
 function choices(id,rows,placeholder){
  const select=$(id),value=select.value;select.replaceChildren();if(placeholder)select.append(new Option(placeholder,''));
  for(const [key,label]of rows)select.append(new Option(label,key));missingOption(select,value);
 }
 function updateDraftControls(){$('voice-draft-summary').textContent=blocked?'草稿需要处理':memory.editor||memory.fixed?'有未完成的编辑草稿':'编辑草稿与恢复';if(blocked)$('voice-drafts').open=true;
  $('resume-preset').hidden=friend||!memory.editor;
  $('resume-fixed').hidden=friend||!memory.fixed;
  $('restore-fixed').hidden=friend||!memory.previousFixed;
  $('restore-preset').hidden=friend||!memory.previous;
  $('export-draft').hidden=friend||!memory.editor&&!memory.fixed&&!blocked;
  $('independent-draft').hidden=friend||!blocked;
 }
 function writeDraft(){
  updateDraftControls();if(friend)return;
  if(blocked){$('draft-status').textContent=recoveryRaw!==null?'已有草稿无法读取，原文仍保留；请先导出，或继续使用独立草稿。':'其他窗口已更新浏览器草稿；当前内容仍保留，可导出或使用独立草稿。';if($('preset-editor').open)editorStatus('当前输入仍保留在窗口中。',true);return}
  try{VoiceEditorState.write(StudioStorage.local,cacheKey,memory);$('draft-status').textContent='编辑草稿已保存在此浏览器'}
  catch{blocked=true;$('draft-status').textContent='无法保存浏览器草稿；请导出当前内容后再离开。';updateDraftControls()}
 }
 function capture(){
  if(editor)memory.editor={...editor,fields:fields('preset-form')};
  if(fixedJob)memory.fixed={job:fixedJob,fields:fields('fixed-voice-form')};
 }
 function stash(){capture();writeDraft()}
 function exportDraft(){
  capture();const raw=recoveryRaw??JSON.stringify(memory,null,2),url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));
  const anchor=link('导出',url);anchor.download='voice-editor-recovery.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 if(!friend){
  try{cacheKey=StudioStorage.session.getItem(cacheBase+':active')||cacheBase;memory=VoiceEditorState.read(StudioStorage.local,cacheKey);if(memory.editor||memory.fixed)$('draft-status').textContent='有上次编辑的草稿，可以继续。'}
  catch(error){blocked=true;recoveryRaw=error.raw??null;$('draft-status').textContent=error.message}
  addEventListener('storage',event=>{if(StudioStorage.local.matches(event,cacheKey)&&event.newValue!==JSON.stringify(memory)){blocked=true;writeDraft()}});
 }
 updateDraftControls();
 function openEditor(dialog){if(!dialog.open)dialog.showModal();}
 function play(name,url,inEditor=false){
  if(!url){(inEditor?editorStatus:status)('这份参考录音暂不可用，请重新选择。',true);return}
  const audio=$(inEditor?'preset-audio':'reference-audio');audio.hidden=false;
  if(audio.getAttribute('src')!==url)audio.src=url;
  if(!inEditor){$('playing-name').textContent=name;$('reference-player').hidden=false}
  audio.play().catch(()=>{if(!audio.error)(inEditor?editorStatus:status)('请点击播放器开始试听。')});
 }
 for(const id of ['reference-audio','preset-audio','fixed-voice-audio'])$(id).addEventListener('error',()=>{
  const message='参考录音读取失败。参数仍保留，请刷新音色列表或重新选择录音。';
  id==='reference-audio'?status(message,true):editorStatus(message,true,id==='preset-audio'?'editor-status':'fixed-status');
 });
 function voiceCard(preset){
  const isDefault=preset.id===library.default_preset_id,unavailable=preset.available===false;
  const card=node('article',undefined,'voice-card'+(isDefault?' is-default':'')+(unavailable?' is-unavailable':'')),tags=node('div',undefined,'tag-list');card.dataset.presetId=preset.id;card.append(node('h3',preset.name));
  if(isDefault)tags.append(node('span','本地默认','tag default'));for(const tag of preset.tags||[])tags.append(node('span',tag,'tag'));card.append(tags);
  card.append(node('p',preset.description||'尚未填写适用说明。','small voice-description'));
  const voice=preset.voice||{},expression=voice.engine==='qwen3-clone'?'Qwen3-TTS · 固定参考克隆':voice.engine==='qwen3-design'?'Qwen3-TTS · 声音设计':voice.engine==='qwen3-custom'?`Qwen3-TTS · ${voice.qwen_speaker||'Vivian'} · ${voice.qwen_instruct||'默认表达'}`:voice.prosody_reference?'IndexTTS · 独立表达参考':`IndexTTS · ${voice.emotion||'平静'} · 强度 ${voice.intensity??0}`;
  card.append(node('p',`${expression} · 语速 ${voice.speed??1} ×`,'small voice-expression'));
  if(unavailable)card.append(node('p','需要修复：'+preset.error,'small error'));
  const toolbar=node('div',undefined,'toolbar voice-card-actions');
  if(!unavailable)toolbar.append(link('试配音',`/speech?preset=${encodeURIComponent(preset.id)}`));
  const preview=action('参考试听',()=>play(preset.name,preset.preview_url),'quiet');preview.disabled=!preset.preview_url;toolbar.append(preview);
  const more=node('div',undefined,'toolbar voice-card-more');more.append(action(unavailable?'修复预设':preset.source==='saved'?'编辑预设':'另存预设',()=>edit(preset),'quiet'));
  if(!unavailable){
   const defaultButton=action(isDefault?'当前默认':'设为本地默认',async()=>{defaultButton.disabled=true;try{await api('/api/voice-library/default',{id:preset.id});status('已设为本地新任务的默认音色。');await load()}catch(error){status(error.message,true);defaultButton.disabled=isDefault}},'quiet');defaultButton.disabled=isDefault;
   more.append(defaultButton,link('用于白板',`/whiteboard?preset=${encodeURIComponent(preset.id)}`,'quiet'));
  }
  card.append(toolbar,more);return card;
 }
 function systemCard(row){
  const card=node('article',undefined,'voice-card');card.append(node('h3',row.name),node('p',row.description,'small voice-description'),node('p',row.note,'small'));
  const params=new URLSearchParams({backend:row.backend});if(row.id)params.set('voice_id',row.id);
  const toolbar=node('div',undefined,'toolbar voice-card-actions');toolbar.append(link('选择并试配音','/speech?'+params));
  if(['online','volc'].includes(row.backend))toolbar.append(link('配置语音服务','/settings?service=tts','quiet'));
  card.append(toolbar);return card;
 }
 function systemRows(){
  const rows=[];
  if(speech){
   for(const row of speech.windows?.voices||[])rows.push({backend:'windows',id:row.id,name:row.label||row.id,description:'Windows 系统语音 · '+(row.language||'已安装音色'),note:'CPU 离线运行，无需模型或密钥。'});
   for(const row of speech.edge?.voices||[])rows.push({backend:'edge',id:row.id,name:row.label||row.id,description:'Edge 在线语音 · 免密钥联网',note:speech.edge.available?'文字发送到微软语音服务，可用性以试听为准。':'需先安装语音组件，可在配音页查看提示。'});
  }
  rows.push({backend:'online',name:'OpenAI 兼容语音',description:'使用在线设置中保存的音色，也可在配音页填写音色 ID。',note:'按服务商计费；生成字幕还需识别接口。'},
            {backend:'volc',name:'豆包语音',description:'使用已配置的火山引擎账号和音色。',note:'按服务商计费；可在配音页调整音色 ID。'});
  return rows;
 }
 function render(){
  const query=$('voice-search').value.trim().toLowerCase(),tag=$('voice-tag').value,mode=$('voice-source').value;
  const matches=row=>(!tag||(row.tags||[]).includes(tag))&&(!query||[row.name,row.description,...(row.tags||[])].join(' ').toLowerCase().includes(query));
  const local=!friend&&['all','local'].includes(mode);$('new-preset').hidden=!local;$('local-voice-default').hidden=!local;$('local-collection').hidden=!local;$('voice-tag').disabled=!local;$('voice-tag').closest('label').hidden=!local;document.querySelector('.filters').classList.toggle('system-filter',!local);
  const localRows=local?library.presets.filter(matches):[];
  const personal=row=>row.source==='saved'||row.id===library.default_preset_id;
  const preferred=localRows.filter(personal).sort((a,b)=>Number(b.id===library.default_preset_id)-Number(a.id===library.default_preset_id));
  const references=localRows.filter(row=>!personal(row)&&row.source!=='builtin'),builtins=localRows.filter(row=>!personal(row)&&row.source==='builtin');
  const filtering=!!(query||tag),section=$('builtin-section');if(filtering&&!filterWasActive)builtinOpenBeforeFilter=section.open;
  if(filtering&&builtins.length)section.open=true;if(!filtering&&filterWasActive)section.open=builtinOpenBeforeFilter;filterWasActive=filtering;
  $('personal-count').textContent=`${preferred.length} 个`;$('reference-count').textContent=`${references.length} 份`;$('builtin-count').textContent=`${builtins.length} 个`;
  $('reference-section').hidden=!references.length;section.hidden=!builtins.length;
  for(const [id,rows]of [['voice-list',preferred],['reference-list',references],['builtin-list',builtins]]){$(id).replaceChildren(...rows.map(voiceCard));$(id).setAttribute('aria-busy','false')}
  if(!preferred.length)$('voice-list').append(node('p',!libraryReady?(loading?'正在读取本地预设…':'本地音色暂不可用，可刷新重试。'):filtering?'没有匹配的个人预设，可清空搜索和题材。':'还没有个人预设。新建预设，或选择参考录音后另存。','empty'));
  const system=mode==='local'?[]:systemRows().filter(row=>(mode!=='windows'||row.backend==='windows')&&(mode!=='online'||row.backend!=='windows')&&(!query||[row.name,row.description,row.id].join(' ').toLowerCase().includes(query)));
  $('system-section').hidden=mode==='local';$('system-list').replaceChildren(...system.map(systemCard));$('system-count').textContent=`${system.length} 个`;
  if(!system.length)$('system-list').append(node('p',loading&&!speech?'正在读取可用系统音色…':query?'没有匹配的系统或在线音色。':speech?'没有已安装的系统音色，可选择在线语音。':'暂时无法读取系统音色，请刷新重试。','empty'));
  $('filter-summary').textContent=`当前显示 ${localRows.length+system.length} 个音色。`+(local?'参考试听播放原录音；实际配音请用自己的台词判断。':'选择音色后在配音页生成试听。');
  $('default-voice-name').textContent=libraryReady?(library.presets.find(row=>row.id===library.default_preset_id)?.name||'自定义参数'):'暂未读取';
  $('library-summary').textContent=local?`${library.presets.filter(row=>row.source==='saved').length} 个个人预设 · ${library.references.length} 份参考录音`:loading&&!speech?'正在读取可用音色':`${system.length} 个${mode==='windows'?' Windows 系统':'在线'}音色`;
 }
 function syncFilters(){const params=new URLSearchParams(location.search);for(const [id,key]of [['voice-search','q'],['voice-tag','tag'],['voice-source','source']]){$(id).value?params.set(key,$(id).value):params.delete(key)}history.replaceState(null,'','/voices'+(params.size?'?'+params:''));render()}
 const query=new URLSearchParams(location.search);
 if(friend)$('voice-source').querySelector('option[value="local"]').remove();
 $('voice-source').value=Array.from($('voice-source').options).some(row=>row.value===query.get('source'))?query.get('source'):'all';$('voice-search').value=query.get('q')||'';missingOption($('voice-tag'),query.get('tag')||'','原题材：');
 $('voice-search').oninput=syncFilters;$('voice-tag').onchange=syncFilters;$('voice-source').onchange=syncFilters;
 async function load(){
  if(loading)return;loading=true;$('reload-library').disabled=true;$('reload-library').textContent='正在读取…';
  const errors=[];
  await Promise.allSettled([
   (async()=>{try{speech=await api('/api/speech/options');render()}catch(error){errors.push('系统音色：'+error.message)}})(),
   ...(friend?[]:[(async()=>{try{
    const value=await api('/api/voice-library');library=value;libraryReady=true;$('new-preset').disabled=false;
    const tag=$('voice-tag').value||'';choices('voice-tag',[...new Set(library.presets.flatMap(row=>row.tags||[]))].sort().map(value=>[value,value]),'全部题材');missingOption($('voice-tag'),tag,'原题材：');
    if(editor)referenceChoices();render();
   }catch(error){errors.push('本地预设：'+error.message)}})()])
  ]);
  loading=false;$('reload-library').disabled=false;$('reload-library').textContent='刷新音色';render();
  if(errors.length)status(errors.join(' ')+' 已载入的内容和草稿仍保留。',true);
  return errors;
 }
 function referenceChoices(){
  const refs=library.references.map(row=>[row.path,row.name]);choices('preset-reference',refs,'不使用试听样本 / 请选择克隆参考');choices('preset-prosody',refs,'按情感控制');choices('preset-emotion',library.emotions.map(value=>[value,value]));
 }
 function draftFor(preset=null,voiceOverride=null){
  const defaults=library.default_voice||library.presets[0]?.voice||{};
  const voice=structuredClone(voiceOverride||preset?.voice||defaults),saved=preset?.source==='saved';
  const map={name:preset?(saved?preset.name:preset.name+' · 自定义'):'',tags:(preset?.tags||[]).join('，'),description:preset?.description||'',engine:voice.engine||'index-tts',
   'qwen-speaker':voice.qwen_speaker||'Vivian','qwen-language':voice.qwen_language||'Chinese','qwen-instruct':voice.qwen_instruct||'','qwen-reftext':voice.qwen_ref_text||'','qwen-seed':voice.qwen_seed??42,
   reference:voice.reference||'',emotion:voice.emotion||'平静',intensity:voice.intensity??.6,speed:voice.speed??1,online:voice.online_voice||'alloy',duration:voice.duration_factor??1,pitch:voice.pitch_semitones??0,formant:voice.formant_shift??1,
   prosody:voice.prosody_reference||'','prosody-strength':voice.prosody_strength??1};
  return {id:saved?preset.id:null,revision:saved?preset.revision:null,voice,fields:Object.fromEntries(Object.entries(map).map(([key,value])=>['preset-'+key,String(value)]))};
 }
 function showEditor(row){
  if(friend)return;opening++;editor={id:row.id,revision:row.revision,voice:structuredClone(row.voice)};
  choices('preset-qwen-speaker',speakers.map(value=>[value,value]));choices('preset-qwen-language',languages);referenceChoices();
  const restored={...draftFor(null,row.voice).fields,...row.fields};
  for(const [id,value]of Object.entries(restored)){const field=$(id);if(!field||!$('preset-form').contains(field))continue;if(field.tagName==='SELECT')missingOption(field,value);else field.value=value}
  $('preset-editor-title').textContent=editor.id?'编辑音色预设':'保存新的音色预设';
  $('preset-audio').pause();$('preset-audio').hidden=true;updateExpressionMode();
  editorStatus('输入自动保留；保存预设后仍可继续编辑。');
  openEditor($('preset-editor'));$('preset-name').focus();stash();
 }
 function edit(preset=null,voiceOverride=null){capture();if(memory.editor)memory.previous=structuredClone(memory.editor);showEditor(draftFor(preset,voiceOverride))}
 function updateExpressionMode(){
  const engine=$('preset-engine').value,qwen=engine.startsWith('qwen3-'),design=engine==='qwen3-design',usingReference=!!$('preset-prosody').value;
  for(const group of document.querySelectorAll('[data-voice-engine]')){group.hidden=!group.dataset.voiceEngine.split(' ').includes(engine);for(const field of group.querySelectorAll('input,select,textarea'))field.disabled=group.hidden}
  $('preset-emotion').disabled=qwen||usingReference;$('preset-intensity').disabled=qwen||usingReference;$('preset-prosody-strength').disabled=qwen||!usingReference;
  $('preset-reference').closest('label').hidden=design;$('preset-reference').disabled=design;$('preset-reference').required=!['qwen3-custom','qwen3-design'].includes(engine);
  for(const field of $('preset-form').querySelectorAll('input[type=number]'))field.required=!field.disabled;
  $('preset-name').required=!design;$('preset-preview').hidden=design;$('save-copy').hidden=design||!editor?.id;
  $('save-preset').textContent=design?'先生成试听，再保存固定角色':'保存到音色库';
  $('preset-engine-note').textContent=({'index-tts':'使用参考声音克隆音色，可用情感或独立表达参考控制语气。','qwen3-custom':'使用现成声线；下方参考录音仅供试听，可不选。','qwen3-design':'先生成试听，再从满意的结果保存固定角色。','qwen3-clone':'根据参考录音克隆声音；参考原文应与录音一致，也可留空。'})[engine]||'原引擎不可用，请选择当前支持的引擎。';
  $('preset-engine-health').hidden=!qwen;if(qwen)checkQwen(engine);updateProcessingSummary();updateReferenceState();
 }
 function updateReferenceState(){
  const field=$('preset-reference'),hint=$('preset-reference-status');
  const reference=library.references.find(row=>row.path===field.value),missing=!field.disabled&&field.value&&!reference;
  const message=missing?(field.required?'原参考录音当前不可用，请重新选择一份录音后保存。':'原试听样本当前不可用，可重新选择或选择“不使用试听样本”。'):!field.disabled&&field.required&&!field.value?'此引擎需要一份参考录音。请选择可用录音，或切换到不需要录音的现成声线。':'';
  hint.textContent=message;hint.hidden=!message;hint.className='small full'+(missing?' error':'');
  field.setCustomValidity(field.required&&missing?'请重新选择可用的参考录音。':'');field.setAttribute('aria-invalid',String(!!missing));
  $('preset-preview').disabled=!reference?.preview_url;
 }
 let healthEpoch=0;
 async function checkQwen(engine){
  const epoch=++healthEpoch,hint=$('preset-engine-health');hint.textContent='正在检查所选 Qwen 模型…';
  try{const result=await api('/api/voice-library/qwen-status?engine='+encodeURIComponent(engine));if(epoch!==healthEpoch||$('preset-engine').value!==engine)return;
   hint.textContent=(result.ready?'本地文件齐备；实际声音仍需试听。':'本地模型尚未就绪。')+' '+(result.checks||[]).filter(row=>!row.ready).map(row=>row.message).join(' ');hint.className='small full'+(result.ready?'':' error');
  }catch(error){if(epoch!==healthEpoch||$('preset-engine').value!==engine)return;hint.textContent='暂时无法检查模型：'+error.message;hint.className='small full error'}
 }
 function updateProcessingSummary(){
  let panel=$('preset-processing');if(!panel){panel=node('p',undefined,'small full');panel.id='preset-processing';$('preset-engine-note').after(panel)}
  const values=['preset-speed','preset-pitch','preset-formant'].map(id=>$(id).value||'待填写');panel.textContent=`本次调音：语速 ${values[0]} × · 音高 ${values[1]} 半音 · 共鸣 ${values[2]}。`;
 }
 function payload(){
  const voice={...editor.voice},mapping={reference:'reference',emotion:'emotion',intensity:'intensity',speed:'speed',online:'online_voice',duration:'duration_factor',pitch:'pitch_semitones',formant:'formant_shift',prosody:'prosody_reference','prosody-strength':'prosody_strength',engine:'engine','qwen-speaker':'qwen_speaker','qwen-instruct':'qwen_instruct','qwen-language':'qwen_language','qwen-seed':'qwen_seed','qwen-reftext':'qwen_ref_text'};
  for(const [field,key]of Object.entries(mapping)){const input=$('preset-'+field);if(!input.disabled)voice[key]=input.type==='number'?Number(input.value):input.value.trim()}
  if(voice.engine!=='index-tts')voice.prosody_reference='';if(voice.engine==='qwen3-design')voice.reference='';
  return {name:$('preset-name').value.trim(),tags:$('preset-tags').value.split(/[,，、]/).map(tag=>tag.trim()).filter(Boolean),description:$('preset-description').value.replace(/[\r\n]+/g,' ').trim(),voice};
 }
 async function savePreset(copy=false){
  if(saving||!editor||!$('preset-form').reportValidity())return;
  const currentOpening=opening,submitted=JSON.stringify(fields('preset-form')),request=payload();
  if(request.voice.engine==='qwen3-design'){try{StudioStorage.session.setItem('voice-library-to-speech',JSON.stringify(request.voice));stash();location.assign('/speech?engine=qwen3-design')}catch(error){editorStatus(error.message,true)}return}
  if(editor.id&&!copy){request.id=editor.id;request.revision=editor.revision}
  saving=true;$('save-preset').disabled=true;$('save-copy').disabled=true;editorStatus('正在保存这次提交的参数…');
  try{
   const result=await api('/api/voice-library/save',request);
   if(opening===currentOpening){
    editor={id:result.preset.id,revision:result.preset.revision,voice:structuredClone(result.preset.voice)};
    $('preset-editor-title').textContent='编辑音色预设';$('save-copy').hidden=false;stash();
    editorStatus(submitted===JSON.stringify(fields('preset-form'))?'已保存到音色库。可继续编辑，或收起窗口。':'提交的版本已保存；之后修改的内容仍在草稿中，需要再次保存。');
   }
   status('已保存「'+result.preset.name+'」。');await load();
  }catch(error){if(opening===currentOpening)editorStatus(error.message,true);else status(error.message,true)}
  finally{saving=false;$('save-preset').disabled=false;$('save-copy').disabled=false}
 }
 $('preset-form').onsubmit=event=>{event.preventDefault();savePreset()};$('save-copy').onclick=()=>savePreset(true);
 $('preset-form').addEventListener('input',()=>{updateProcessingSummary();stash()});$('preset-form').addEventListener('change',stash);
 $('preset-engine').onchange=()=>{updateExpressionMode();stash()};$('preset-prosody').onchange=()=>{updateExpressionMode();stash()};
 $('preset-reference').onchange=()=>{updateReferenceState();stash()};
 $('preset-form').addEventListener('invalid',event=>{for(let parent=event.target.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true},true);
 $('preset-preview').onclick=()=>{const ref=library.references.find(row=>row.path===$('preset-reference').value);play(ref?.name,ref?.preview_url,true)};
 $('cancel-preset').onclick=()=>{$('preset-editor').close()};$('preset-editor').addEventListener('close',()=>{$('preset-audio').pause();stash()});
 $('new-preset').onclick=()=>edit();$('reload-library').onclick=()=>{status('正在刷新音色…');load().then(errors=>{if(!errors?.length)status('音色列表已刷新，当前草稿保持不变。')})};
 $('resume-preset').onclick=()=>{if(memory.editor)showEditor(memory.editor)};
 $('resume-fixed').onclick=()=>showFixedJob(memory.fixed.job).catch(error=>status(error.message,true));
 $('restore-fixed').onclick=()=>{capture();const previous=memory.previousFixed;memory.previousFixed=memory.fixed;memory.fixed=previous;fixedJob=null;writeDraft();showFixedJob(previous.job).catch(error=>status(error.message,true))};
 $('restore-preset').onclick=()=>{capture();const saved=memory.previous;memory.previous=memory.editor;showEditor(saved)};
 $('export-draft').onclick=exportDraft;
 $('independent-draft').onclick=()=>{capture();cacheKey=cacheBase+':copy:'+Date.now();try{StudioStorage.session.setItem(cacheBase+':active',cacheKey)}catch{}blocked=false;recoveryRaw=null;writeDraft()};
 $('import-draft').onclick=()=>{$('draft-file').click()};
 $('draft-file').onchange=async()=>{const file=$('draft-file').files[0];if(!file)return;try{
  if(file.size>2*1024*1024)throw Error('草稿文件应小于 2 MB');const value=VoiceEditorState.check(JSON.parse(await file.text()));capture();
  const previous=memory.editor,previousFixed=memory.fixed;memory={...value,previous:previous||value.previous,previousFixed:previousFixed||value.previousFixed};editor=null;fixedJob=null;writeDraft();
  if(memory.editor)showEditor(memory.editor);else if(memory.fixed)await showFixedJob(memory.fixed.job);status('已导入草稿。保存预设前请检查当前音色和参考录音。');
 }catch(error){status('导入失败：'+error.message,true)}finally{$('draft-file').value=''}};
 async function showFixedJob(id){
  if(friend)throw Error('当前版本请使用系统或在线音色；本地声音设计需要完整版。');
  const epoch=opening,jobs=await api('/api/jobs'),job=jobs[id];
  if(!job||job.kind!=='speech'||job.status!=='done'||!job.audio||job.voice_engine!=='qwen3-design')throw Error('请选择已成功生成的 Qwen 声音设计试听。');
  if(epoch!==opening)return;capture();if(memory.fixed&&memory.fixed.job!==id)memory.previousFixed=structuredClone(memory.fixed);fixedJob=id;
  for(const field of $('fixed-voice-form').querySelectorAll('input,textarea'))field.value=memory.fixed?.job===id?memory.fixed.fields[field.id]||'':'';
  $('fixed-voice-job').textContent='来源任务：'+id;$('fixed-voice-audio').src=job.audio;
  openEditor($('fixed-voice-editor'));$('fixed-voice-name').focus();stash();editorStatus('先试听这次结果，再填写角色名称保存。',false,'fixed-status');
 }
 $('fixed-voice-form').addEventListener('input',stash);$('close-fixed').onclick=()=>{$('fixed-voice-editor').close()};$('fixed-voice-editor').addEventListener('close',()=>{$('fixed-voice-audio').pause();stash()});
 $('fixed-voice-form').onsubmit=async event=>{
  event.preventDefault();if(!fixedJob||fixedSaving)return;const job=fixedJob,submitted=JSON.stringify(fields('fixed-voice-form'));fixedSaving=true;$('fixed-voice-save').disabled=true;
  try{const result=await api('/api/voice-library/from-speech',{job_id:job,name:$('fixed-voice-name').value.trim(),tags:$('fixed-voice-tags').value.split(/[,，、]/).map(tag=>tag.trim()).filter(Boolean),description:$('fixed-voice-description').value.replace(/[\r\n]+/g,' ').trim()});
   editorStatus(submitted===JSON.stringify(fields('fixed-voice-form'))?'已保存固定角色「'+result.preset.name+'」。':'提交的角色已保存；新输入仍保留，可另存其他角色。',false,'fixed-status');
   await load();
  }catch(error){editorStatus(error.message,true,'fixed-status')}finally{fixedSaving=false;$('fixed-voice-save').disabled=false}
 };
 async function init(){
  const epoch=opening;await load();
  try{
   if(query.get('fromJob')){if(epoch===opening)await showFixedJob(query.get('fromJob'))}
   else if(query.get('from')==='speech'&&!friend){
    const raw=StudioStorage.session.getItem('voice-library-from-speech');if(raw){const voice=JSON.parse(raw);if(!voice||typeof voice!=='object'||Array.isArray(voice))throw Error('配音页参数无法读取');
     if(epoch===opening)edit(null,voice);else{memory.previous=draftFor(null,voice);writeDraft();status('配音页参数已保留，可用“恢复上次替换前的草稿”查看。')}
     StudioStorage.session.removeItem('voice-library-from-speech');const url=new URL(location.href);url.searchParams.delete('from');history.replaceState(null,'',url.pathname+url.search);
    }
   }
  }catch(error){status(error.message,true)}
 }
 if(friend)render();
 init();
})();
