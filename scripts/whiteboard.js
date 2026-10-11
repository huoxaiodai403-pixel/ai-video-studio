/* Whiteboard editor: all topic/model output is treated as text, never HTML. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id), key='ai-studio-whiteboard-v1';
 const layouts={opening:'开场 · 问题与主张',compare:'对比 · 并列关系',steps:'步骤 · 顺序推进',summary:'总结 · 回顾重点'};
 const operationNames={draft:'AI 分镜',preview:'静帧预览',render:'有声视频'};
 let spec=null, polling=false, environmentReady=null,voiceLibrary={presets:[],default_preset_id:null},cast=[];
 const handledDrafts=new Set(), taskNodes=new Map();
 let selectedScene=0,stage='brief',activeJob='',activeState=null,previewKey='',submittedSignature='',jobSubmitting=false;
 let previewJob='',previewState=null,previewSignature='';
 const runSignatures=new Map();
 const compactScenes=matchMedia('(max-width:700px)');
 const sceneOrientation=()=>$('scene-list').setAttribute('aria-orientation',compactScenes.matches?'horizontal':'vertical');
 compactScenes.addEventListener('change',sceneOrientation);sceneOrientation();
 function node(tag,text,className){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(className)item.className=className;return item}
 function message(value,error=false){$('action-status').textContent=value;$('action-status').className=error?'error-text':'success-text';if($('voice-dialog').open)$('voice-feedback').textContent=value}
 function resultNotice(){return submittedSignature&&JSON.stringify(spec)!==submittedSignature?'内容或配音已修改，上次结果已保留；请按当前内容重新生成。':activeState?.operation==='render'?'视频已完成，请播放检查画面与旁白。':'画面已生成。请检查文字、构图与镜头顺序。'}
 async function api(path,data){const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||`请求失败：${response.status}`);return result}
 function store(){
  if(spec){spec.title=$('video-title').value;spec.voice_preset_id=$('voice-preset').value;spec.characters=Object.fromEntries(cast.map(role=>[role.name,role.preset]));delete spec.character_preset_ids;spec.voice=$('voice-speed').value?{speed:Number($('voice-speed').value)}:{};const source=window.WhiteboardSpeech?.peek();if(source){spec.backends={tts:source.backend,asr:source.backend==='local'?'local':'synthesis'};spec.voice.voice_id=source.voice_id}}
  try{StudioStorage.local.setItem(key,JSON.stringify({spec,stage,speed:$('voice-speed').value,selectedScene,activeJob,topic:$('topic').value,count:$('scene-count').value,storyBackend:$('story-backend').value,submittedSignature,previewJob,previewSignature}));$('draft-state').textContent='草稿已保存在此浏览器'}catch{$('draft-state').textContent='草稿未保存 · 请导出备份'}updateSceneLabel();renderPreview();
  if(activeState?.status==='done'&&activeState.operation!=='draft'&&submittedSignature&&JSON.stringify(spec)!==submittedSignature)message(resultNotice());
 }
 function backupDraft(reason){
  store();const snapshot={saved_at:new Date().toISOString(),reason,spec:structuredClone(spec),speed:$('voice-speed').value,topic:$('topic').value,pendingDraft:StudioStorage.session.getItem('whiteboard-pending-draft')};
  let rows=[];try{rows=JSON.parse(StudioStorage.local.getItem(key+'-backups')||'[]')}catch{}if(!Array.isArray(rows))rows=[];
  try{StudioStorage.local.setItem(key+'-backups',JSON.stringify([...rows.slice(-4),snapshot]))}catch{throw Error('浏览器无法备份当前草稿，已停止替换。请先导出草稿并释放浏览器存储。')}
  let host=$('draft-backup');if(!host){host=node('div',undefined,'small');host.id='draft-backup';$('action-status').after(host)}host.replaceChildren(node('span','载入前的浏览器草稿已备份。 '));
  host.append(button('下载备份',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'})),link=downloadLink(url,'');link.download='whiteboard-before-load.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)},'secondary'));
  return snapshot;
 }
 async function loadProject(id,state){
  if(!/^whiteboard-[a-f0-9]{10}$/.test(id))throw Error('白板项目编号无效。');
  state=state||(await api('/api/jobs'))[id];if(!state||state.kind!=='whiteboard')throw Error('找不到指定的白板项目：'+id);
  let value=state.storyboard;
  if(!value&&state.storyboard_url){const url=new URL(state.storyboard_url,location.origin);if(url.origin!==location.origin||url.search||url.hash||!url.pathname.startsWith('/outputs/'+id+'/')||!url.pathname.endsWith('/storyboard.json'))throw Error('该项目的分镜地址无效。');value=await api(url.pathname)}
  if(!value||!Array.isArray(value.scenes)||!value.scenes.length||value.scenes.some(scene=>typeof scene.narration!=='string'||typeof scene.board_title!=='string'||!Array.isArray(scene.board_cards)))throw Error('该项目暂无可恢复的白板分镜，请等待写稿完成。');
  backupDraft('载入项目 '+id);StudioStorage.session.removeItem('whiteboard-pending-draft');selectedScene=0;setSpec(value,true);activeJob=id;activeState=state;submittedSignature=JSON.stringify(spec);runSignatures.set(id,submittedSignature);previewJob=state.previews?.length?id:'';previewState=state.previews?.length?state:null;previewSignature=submittedSignature;renderPreview();store();
  const main=document.querySelector('main');if(main)main.dataset.currentProject=id;
  message('已载入白板项目 '+id+' 的分镜。提交预览或制作会创建新任务，原成片仍保留。');
 }
 function field(label,control){const wrapper=node('label',undefined,'form-field');wrapper.append(node('span',label),control);return wrapper}
 function input(value,max,oninput,tag='input'){const item=document.createElement(tag);item.value=value;item.maxLength=max;item.addEventListener('input',()=>oninput(item.value));return item}
 function button(label,callback,className='quiet'){const item=node('button',label,className);item.type='button';item.addEventListener('click',callback);return item}
 function reindex(){spec.scenes.forEach((scene,index)=>{scene.id=`scene${String(index+1).padStart(2,'0')}`})}
 function presetSelect(value='',emptyLabel='跟随全片音色'){const select=node('select');select.append(new Option(emptyLabel,''));for(const preset of voiceLibrary.presets)select.append(new Option(preset.name,preset.id));if(value&&!voiceLibrary.presets.some(preset=>preset.id===value))select.append(new Option('预设未找到 · 请重新选择',value));select.value=value;return select}
 function previewVoice(presetId){const preset=voiceLibrary.presets.find(item=>item.id===(presetId||voiceLibrary.default_preset_id))||(!presetId?(voiceLibrary.references||[]).find(item=>item.path===voiceLibrary.default_voice?.reference):null);if(!preset?.preview_url){message('该预设暂无可试听的参考录音，请在音色库中选择。',true);return}const audio=$('cast-preview-audio');if(audio.getAttribute('src')!==preset.preview_url)audio.src=preset.preview_url;audio.hidden=false;$('cast-preview-name').hidden=false;$('cast-preview-name').textContent=`${preset.name} · 参考录音，实际效果需生成试听`;audio.play().catch(()=>message('请点击播放器开始试听。'))}
 function readCast(){const map=spec.character_preset_ids||spec.characters||{};cast=Object.entries(map).map(([name,preset])=>({name,preset:typeof preset==='string'?preset:''}));spec.scenes.forEach(scene=>{if(!scene.speaker)scene.speaker='旁白'})}
 function refreshSpeakers(){document.querySelectorAll('[data-scene-speaker]').forEach(select=>{const scene=spec.scenes[Number(select.dataset.sceneSpeaker)],value=scene.speaker||'旁白';select.replaceChildren(new Option('旁白 · 使用全片音色','旁白'));for(const role of cast)select.append(new Option(role.name,role.name));if(!['旁白',...cast.map(role=>role.name)].includes(value))select.append(new Option(value+' · 角色未配置',value));select.value=value})}
 function renderCast(){
  $('characters').replaceChildren();if(!cast.length)$('characters').append(node('p','当前为单人旁白。添加角色后，可在镜头里切换说话者。','small'));
  cast.forEach((role,index)=>{const row=node('div',undefined,'role-row'),name=input(role.name,32,()=>{});name.onchange=()=>{const next=name.value.trim();if(!next||next==='旁白'||! /^[\p{L}\p{N} _·-]+$/u.test(next)||['__proto__','constructor','prototype'].includes(next)||cast.some((other,i)=>i!==index&&other.name===next)){name.value=role.name;message('角色名需唯一，请使用中英文、数字、空格或 _-·；旁白为保留名称。',true);return}const old=role.name;role.name=next;spec.scenes.forEach(scene=>{if(scene.speaker===old)scene.speaker=next});refreshSpeakers();store()};
   const preset=presetSelect(role.preset,'请选择角色音色');preset.onchange=()=>{role.preset=preset.value;store()};row.append(field('角色名',name),field('角色音色',preset),button('试听',()=>previewVoice(role.preset),'secondary'),button('移除',()=>{cast.splice(index,1);spec.scenes.forEach(scene=>{if(scene.speaker===role.name)scene.speaker='旁白'});renderCast();refreshSpeakers();store()}));$('characters').append(row)
  });$('add-character').disabled=cast.length>=16;
 }
 function setStage(next){
  stage=next;document.body.dataset.stage=next;
  $('brief-panel').hidden=next!=='brief';$('editor').hidden=next!=='edit'||!spec;$('result-panel').hidden=next!=='result';
  for(const control of document.querySelectorAll('[data-stage]')){
   if(control.dataset.stage===next)control.setAttribute('aria-current','step');else control.removeAttribute('aria-current');
   control.disabled=control.dataset.stage==='edit'&&!spec||control.dataset.stage==='result'&&!taskNodes.size;
  }
 }
 function updateSceneLabel(){
  if(!spec)return;
  const control=$('scene-list').children[selectedScene],scene=spec.scenes[selectedScene];
  if(control&&scene){control.querySelector('small').textContent=String(selectedScene+1).padStart(2,'0')+' / '+(layouts[scene.board_layout]||layouts.steps).split(' · ')[0];control.querySelector('strong').textContent=scene.board_title||'未命名镜头';control.querySelector('small:last-child').textContent=scene.narration.length+' 字旁白'}
 }
 function renderPreview(){
  if(!spec)return;
  const state=activeState,stale=!!previewState&&JSON.stringify(spec)!==previewSignature;
  // Beat frames are ordered within each scene. Its final beat shows the complete board;
  // the renderer's "mid" frame is only the beginning of the first drawing stroke.
  const frames=new Map();for(const url of previewState?.previews||[]){const match=url.match(/\/([^/]+)-beat(\d+)\.png$/);if(match&&(!frames.has(match[1])||frames.get(match[1]).beat<Number(match[2])))frames.set(match[1],{url,beat:Number(match[2])})}
  const src=[...frames.values()][selectedScene]?.url,busy=state?.status==='running'||state?.status==='queued',viewKey=[activeJob,selectedScene,src||'',state?.status||'',state?.phase||'',stale].join('|');
  if(previewKey===viewKey)return;previewKey=viewKey;
  $('preview-label').textContent='镜头 '+String(selectedScene+1).padStart(2,'0')+' · 画面预览';
  const screen=$('board-preview');
  screen.setAttribute('aria-busy',String(busy));
  if(src){if(screen.querySelector('img')?.getAttribute('src')!==src){const image=node('img');image.src=src;image.alt='上次生成的白板镜头 '+(selectedScene+1);screen.replaceChildren(image)}}
  else{const empty=node('div',undefined,'wb-preview-empty'),mark=node('img');mark.src='/assets/brand/studio-mark.svg';mark.alt='';empty.append(mark,node('h3',busy?'正在准备真实画面':'先看看这段内容如何呈现'),node('p',busy?'可以继续编辑分镜，新修改会在下次生成时生效。':'编辑旁白与关键词后，点击「生成画面预览」。'));screen.replaceChildren(empty)}
  $('preview-state').textContent=state?.status==='error'?'制作失败 · '+(src?'内容与上次画面已保留':'草稿已保留'):busy?((state.phase||'正在制作…')+(src?' · 暂示上次画面':'')):src?(stale?'上次画面 · 内容或顺序已修改，需重新预览':'已生成画面 · 可继续编辑'):'尚未生成预览';
 }
 function selectScene(index,focus=false){
  selectedScene=Math.max(0,Math.min(spec.scenes.length-1,index));renderScene();
  for(const [i,control] of [...$('scene-list').children].entries()){control.setAttribute('aria-selected',String(i===selectedScene));control.tabIndex=i===selectedScene?0:-1}
  if(focus)$('scene-list').children[selectedScene]?.focus();store();
 }
 function renderEditor(){
  if(!spec)return;
  selectedScene=Math.max(0,Math.min(selectedScene,spec.scenes.length-1));
  $('video-title').value=spec.title;
  const selected=spec.voice_preset_id||'',voiceSelect=presetSelect(selected,'跟随工作台默认音色');$('voice-preset').replaceChildren(...voiceSelect.childNodes);$('voice-preset').value=selected;renderCast();
  $('scene-list').replaceChildren();
  spec.scenes.forEach((scene,index)=>{
   const control=button('',()=>selectScene(index),'wb-scene-tab');control.id='scene-tab-'+index;control.setAttribute('role','tab');control.setAttribute('aria-controls','scenes');control.setAttribute('aria-selected',String(index===selectedScene));control.tabIndex=index===selectedScene?0:-1;
   control.append(node('small',String(index+1).padStart(2,'0')+' / '+layouts[scene.board_layout].split(' · ')[0]),node('strong',scene.board_title||'未命名镜头'),node('small',scene.narration.length+' 字旁白'));
   control.onkeydown=event=>{let next=index;if(event.key==='ArrowDown'||event.key==='ArrowRight')next=(index+1)%spec.scenes.length;else if(event.key==='ArrowUp'||event.key==='ArrowLeft')next=(index+spec.scenes.length-1)%spec.scenes.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=spec.scenes.length-1;else return;event.preventDefault();selectScene(next,true)};
   $('scene-list').append(control);
  });
  $('scene-counter').textContent=spec.scenes.length+' 个镜头';$('add-scene').disabled=spec.scenes.length>=8;$('open-voice').disabled=false;
  renderScene();updateBusy();setStage('edit');
 }
 function renderScene(){
  const scene=spec.scenes[selectedScene],index=selectedScene;$('scenes').replaceChildren();$('scenes').setAttribute('role','tabpanel');$('scenes').setAttribute('aria-labelledby','scene-tab-'+index);$('inspector-number').textContent=String(index+1).padStart(2,'0')+' / '+String(spec.scenes.length).padStart(2,'0');
  const grid=node('div',undefined,'scene-grid'),left=node('div'),right=node('div');
  left.append(field('画面标题',input(scene.board_title,36,value=>{scene.board_title=value;scene.subject=value;store()})));
  const narration=input(scene.narration,600,value=>{scene.narration=value;delete scene.board_beats;store()},'textarea');narration.className='narration';left.append(field('旁白 · 这段要说的话',narration));
  const cards=input(scene.board_cards.join('\n'),100,value=>{scene.board_cards=value.split('\n').map(s=>s.trim()).filter(Boolean);delete scene.board_beats;store()},'textarea');cards.className='keywords';cards.rows=3;right.append(field('画面关键词 · 每行一个，最多 3 个',cards));
  const choices=node('div',undefined,'wb-inline-fields'),layout=node('select');for(const [value,label]of Object.entries(layouts))layout.append(new Option(label.split(' · ')[0],value));layout.value=scene.board_layout;layout.onchange=()=>{scene.board_layout=layout.value;store()};
  const sticker=node('select');for(const [value,label]of Object.entries({none:'无贴纸',reader:'阅读',stepper:'步骤',stuck:'困惑',panicked:'惊讶'}))sticker.append(new Option(label,value));sticker.value=scene.board_sticker||'none';sticker.onchange=()=>{scene.board_sticker=sticker.value;store()};choices.append(field('构图',layout),field('人物贴纸',sticker));right.append(choices);
  const voice=node('details',undefined,'scene-voice-grid');voice.append(node('summary','本镜头的角色与音色'));const narrator=node('select');narrator.dataset.sceneSpeaker=String(index);narrator.onchange=()=>{scene.speaker=narrator.value;store()};const override=presetSelect(scene.voice_preset_id||'','跟随角色 / 全片音色');override.onchange=()=>{if(override.value)scene.voice_preset_id=override.value;else delete scene.voice_preset_id;store()};voice.append(field('说话角色',narrator),field('音色覆盖',override));right.append(voice);
  grid.append(left,right);$('scenes').append(grid);
  const controls=node('div',undefined,'wb-scene-actions');
  const move=delta=>{[spec.scenes[index+delta],spec.scenes[index]]=[spec.scenes[index],spec.scenes[index+delta]];selectedScene+=delta;reindex();renderEditor();store()};
  const up=button('上移',()=>move(-1)),down=button('下移',()=>move(1)),remove=button('移除镜头',()=>{spec.scenes.splice(index,1);selectedScene=Math.max(0,index-1);reindex();renderEditor();store()});up.disabled=index===0;down.disabled=index===spec.scenes.length-1;remove.disabled=spec.scenes.length===1;
  controls.append(up,down,remove);$('scenes').append(controls);window.WhiteboardSpeech?.refresh();refreshSpeakers();renderPreview();
 }
 function updateBusy(){
  const busy=jobSubmitting||activeState?.status==='running'||activeState?.status==='queued';
  for(const id of ['preview','render'])$(id).disabled=!spec||busy;
  $('draft').disabled=busy;
  $('preview').textContent=busy?'正在制作…':activeState?.status==='error'?'重新生成预览':'生成画面预览';
 }
 function speechSource(value){
  const hasPresets=!!(value.voice_preset_id||Object.keys(value.character_preset_ids||value.characters||{}).length||value.scenes?.some(scene=>scene.voice_preset_id));
  return {backend:value.backends?.tts||(hasPresets?'local':'windows'),voice_id:value.voice?.voice_id||value.settings?.voice?.voice_id||''};
 }
 function setSpec(value,exact=false){
  const previous=spec,requested=exact?'':new URLSearchParams(location.search).get('preset');spec=structuredClone(value);
  if(requested)spec.voice_preset_id=requested;
  else if(!Object.hasOwn(value,'voice_preset_id'))spec.voice_preset_id=exact?'':previous?.voice_preset_id||'';
  const source=speechSource(spec);if(requested)source.backend='local';window.WhiteboardSpeech?.set(source);
  if(exact)$('voice-speed').value='';readCast();reindex();renderEditor();if(value.voice&&Object.hasOwn(value.voice,'speed'))$('voice-speed').value=String(value.voice.speed);store();
 }
 function payload(){
  if(!spec)throw Error('请先生成分镜或载入示例。');
  store();const source=window.WhiteboardSpeech.value();
  if(!spec.title.trim())throw Error('请填写视频标题。');
  if(source.backend==='local')for(const role of cast)if(!role.preset)throw Error(`请选择角色「${role.name}」的音色。`);
  for(let i=0;i<spec.scenes.length;i++){const scene=spec.scenes[i];if(!scene.board_title.trim()||!scene.narration.trim())throw Error(`请填写镜头 ${i+1} 的标题与旁白。`);if(scene.board_cards.length<1||scene.board_cards.length>3||scene.board_cards.some(s=>s.length>24))throw Error(`镜头 ${i+1} 需要 1–3 条关键词，每条最多 24 字。`)}
  if(source.backend==='local')return {storyboard:spec,...(spec.voice_preset_id?{voice_preset_id:spec.voice_preset_id}:{}),characters:spec.characters,voice:spec.voice,backends:{tts:'local',asr:'local'}};
  const board=structuredClone(spec);
  for(const scene of board.scenes){delete scene.voice_preset_id;delete scene.voice;scene.speaker='旁白'}
  delete board.voice_preset_id;delete board.characters;
  return {storyboard:board,voice:spec.voice,backends:{tts:source.backend,asr:'synthesis'}};
 }
 function draftInputSignature(){return JSON.stringify({spec,topic:$('topic').value,count:$('scene-count').value,backend:$('story-backend').value})}
 async function submit(operation){
  if(jobSubmitting)return;jobSubmitting=true;updateBusy();
  try{
   if(operation!=='draft')await window.WhiteboardSpeech.ready;
   const data=operation==='draft'?{topic:$('topic').value,count:Number($('scene-count').value),backend:$('story-backend').value}:payload();
   if(operation==='draft'&&!data.topic.trim())throw Error('先写下你想讲的主题。');
   const signature=operation==='draft'?draftInputSignature():JSON.stringify(spec);
   const result=await api(`/api/whiteboard/${operation}`,data);activeJob=result.job_id;submittedSignature=signature;runSignatures.set(activeJob,signature);activeState={status:'queued',operation};
   if(operation==='draft'){try{StudioStorage.session.setItem('whiteboard-pending-draft',result.job_id);StudioStorage.session.setItem('whiteboard-pending-signature',signature)}catch{}}
   store();message(operationNames[operation]+'已提交，可以继续查看分镜。');await poll();
   if(operation==='render')setStage('result');
  }catch(error){message(error.message,true)}finally{jobSubmitting=false;updateBusy()}
 }
 function downloadLink(url,label){const link=node('a',label);link.href=url;link.download='';return link}
 function taskCard(id,state){
  const article=node('article',undefined,'task'),header=node('div',undefined,'job-header');article.dataset.jobId=id;
  const when=state.created?new Date(state.created*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'';
  header.append(node('strong',state.title||operationNames[state.operation]),node('span',{queued:'排队中',running:'运行中',done:'已完成',error:'失败'}[state.status]||state.status,`task-state ${state.status}`));article.append(header,node('p',`${operationNames[state.operation]||'白板'}${when?' · '+when:''}`,'small'),node('p',state.phase||state.status));
  if(state.status==='running'||state.status==='queued'){const progress=node('progress');progress.setAttribute('aria-label',state.phase||'正在处理');article.append(progress)}
  if(state.error)article.append(node('p',state.error,'error-text'));
  if(state.storyboard||state.storyboard_url){const load=button('载入此分镜',async()=>{try{await loadProject(id,state);setStage('edit')}catch(error){message(error.message,true)}},'secondary');article.append(load)}
  if(state.video){const video=node('video');video.src=state.video;video.setAttribute('aria-label','白板成片预览');video.controls=true;video.preload='metadata';article.append(video)}
  if(state.previews?.length){const details=node('details');const images=node('div',undefined,'preview-grid');details.append(node('summary',`查看过程静帧（${state.previews.length} 张）`));state.previews.forEach((url,index)=>{const figure=node('figure'),link=node('a'),image=node('img');image.src=url;image.alt=`白板预览 ${index+1}`;image.loading='lazy';link.href=url;link.target='_blank';link.rel='noopener';link.append(image);figure.append(link,node('figcaption','过程画面 '+(index+1)));images.append(figure)});details.append(images);article.append(details)}
  const downloads=node('div',undefined,'download-row');if(state.video)downloads.append(downloadLink(state.video,'下载视频'));if(state.subtitle)downloads.append(downloadLink(state.subtitle,'下载字幕'));(state.covers||[]).forEach((url,index)=>downloads.append(downloadLink(url,`下载封面 ${index+1}`)));if(state.storyboard_url)downloads.append(downloadLink(state.storyboard_url,'分镜 JSON'));if(state.manifest_url)downloads.append(downloadLink(state.manifest_url,'素材清单'));if(downloads.childNodes.length)article.append(downloads);
  if(state.sources?.length){const details=node('details'),sources=node('div',undefined,'download-row');details.append(node('summary','下载可编辑 Excalidraw 源文件'));state.sources.forEach((url,index)=>sources.append(downloadLink(url,`镜头 ${index+1}`)));details.append(sources);article.append(details)}
  return article;
 }
 async function poll(){if(polling)return;polling=true;try{
  const jobs=await api('/api/jobs'),rows=Object.entries(jobs).filter(([,state])=>state.kind==='whiteboard').sort((a,b)=>(b[1].created||0)-(a[1].created||0));
  if(!rows.length){$('tasks').replaceChildren(node('p','还没有制作记录。完成分镜后，先生成画面预览。','small'));return}
  if(previewJob&&jobs[previewJob])previewState=jobs[previewJob];
  if(activeJob&&jobs[activeJob]){const previousStatus=activeState?.status;activeState=jobs[activeJob];if(activeState.status==='error'&&previousStatus!=='error')message('本次制作未完成，草稿已保留。可重新生成，或在「预览与成片」查看原因。',true);if(activeState.previews?.length){const changed=previewJob!==activeJob;previewJob=activeJob;previewState=activeState;previewSignature=runSignatures.get(activeJob)||submittedSignature;if(changed)store()}if(activeState.status==='done'&&previousStatus!=='done'&&activeState.operation!=='draft')message(resultNotice());renderPreview();updateBusy()}
  if(!taskNodes.size)$('tasks').replaceChildren();
  let pending=null;try{pending=StudioStorage.session.getItem('whiteboard-pending-draft')}catch{}
  for(const [id,state]of rows){const signature=JSON.stringify(state),old=taskNodes.get(id);if(old?.signature!==signature){const card=taskCard(id,state);if(old)old.node.replaceWith(card);else{const later=rows.slice(rows.findIndex(row=>row[0]===id)+1).find(row=>taskNodes.has(row[0]));if(later)$('tasks').insertBefore(card,taskNodes.get(later[0]).node);else $('tasks').append(card)}taskNodes.set(id,{signature,node:card})}
   if(id===pending&&state.status==='done'&&state.storyboard&&!handledDrafts.has(id)){handledDrafts.add(id);const previous=StudioStorage.session.getItem('whiteboard-pending-signature');if(previous===draftInputSignature()){setSpec(state.storyboard);message('分镜已生成，可以逐镜头编辑。')}else{message('新的分镜已生成。当前选题或草稿有修改，已保留；请在「预览与成片」中选择是否载入。')}try{StudioStorage.session.removeItem('whiteboard-pending-draft')}catch{}}
   if(id===pending&&state.status==='error'){message(state.error,true);try{StudioStorage.session.removeItem('whiteboard-pending-draft')}catch{}}
  }
 for(const [index,[id]] of rows.entries()){const card=taskNodes.get(id)?.node;if(card){const playing=[...card.querySelectorAll('video,audio')].some(media=>!media.paused&&!media.ended);card.hidden=index>=3&&id!==activeJob&&!playing&&!card.contains(document.activeElement)}}
 document.querySelector('[data-stage=result]').disabled=!rows.length;
 }catch(error){message('读取任务失败：'+error.message,true)}finally{polling=false}}
 async function health(){try{const results=await Promise.allSettled([api('/api/whiteboard/status'),api('/api/story/status'),api('/api/services')]);const [renderer,story,services]=results;
  if(renderer.status==='fulfilled'){environmentReady=renderer.value.ready;$('renderer-health').textContent=environmentReady?'白板渲染已就绪':'白板渲染需配置';$('renderer-health').className=`status-pill ${environmentReady?'ready':'error'}`;$('environment').replaceChildren();for(const check of renderer.value.checks||[])$('environment').append(node('p',`${check.ready?'✓':'○'} ${check.name}：${check.message}`,'small'))}else{$('renderer-health').textContent='无法读取渲染状态';$('renderer-health').className='status-pill error'}
  if(story.status==='fulfilled'){$('story-health').textContent=story.value.ready?'本地编剧已就绪':'本地编剧未就绪';$('story-health').title=story.value.message;$('story-health').className=`status-pill ${story.value.ready?'ready':'error'}`}
  if(services.status==='fulfilled'){$('services').textContent=`千问生图：${services.value.comfyui.ready?'就绪':'未启动'} · 配音：${services.value.tts.ready?'就绪':'未启动'}`}
 }catch{}}
 $('story-backend').onchange=()=>{$('story-health').hidden=$('story-backend').value==='online';store()};$('topic').addEventListener('input',store);$('scene-count').addEventListener('change',store); $('draft').onclick=()=>submit('draft');$('preview').onclick=()=>submit('preview');$('render').onclick=()=>submit('render');$('refresh').onclick=()=>{poll();health()};
 $('example').onclick=async()=>{try{const example=await api('/api/whiteboard/example'+(new URLSearchParams(location.search).get('method')==='simon-skills'?'?method=simon-skills':''));if(spec)backupDraft('载入内置示例');StudioStorage.session.removeItem('whiteboard-pending-draft');activeJob='';activeState=null;previewJob='';previewState=null;previewSignature='';selectedScene=0;setSpec(example);message('已载入内置示例。可直接生成静帧预览，也可以先编辑。')}catch(error){message(error.message,true)}};
 $('add-scene').onclick=()=>{if(spec.scenes.length>=8)return;spec.scenes.push({id:'new',narration:'',subject:'新镜头',style:'Excalidraw 手绘白板',board_title:'新镜头',board_layout:'steps',board_cards:['关键词']});selectedScene=spec.scenes.length-1;reindex();renderEditor();store()};
 $('video-title').addEventListener('input',store);$('voice-speed').addEventListener('change',store);
 $('voice-preset').onchange=store;$('voice-preview').onclick=()=>previewVoice($('voice-preset').value);
 $('add-character').onclick=()=>{if(!spec||cast.length>=16)return;let number=cast.length+1;while(cast.some(role=>role.name===`角色${number}`))number++;cast.push({name:`角色${number}`,preset:$('voice-preset').value||voiceLibrary.default_preset_id||voiceLibrary.presets[0]?.id||''});renderCast();refreshSpeakers();store()};
 $('export-draft').onclick=()=>{try{const data=payload();const blob=new Blob([JSON.stringify(data.storyboard,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=downloadLink(url,'');link.download='whiteboard-storyboard.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){message(error.message,true)}};
 try{const saved=JSON.parse(StudioStorage.local.getItem(key)||'null');if(saved){$('topic').value=saved.topic||'';if(saved.count)$('scene-count').value=saved.count;if([...$('story-backend').options].some(option=>option.value===saved.storyBackend&&!option.disabled))$('story-backend').value=saved.storyBackend;$('story-health').hidden=$('story-backend').value==='online';if(saved.spec?.scenes?.length){spec=saved.spec;selectedScene=saved.selectedScene||0;activeJob=saved.activeJob||'';submittedSignature=saved.submittedSignature||'';previewJob=saved.previewJob||'';previewSignature=saved.previewSignature||'';window.WhiteboardSpeech?.set(speechSource(spec));readCast();$('voice-speed').value=saved.speed??'';renderEditor();if(['brief','result'].includes(saved.stage))setStage(saved.stage)}}}catch{message('上次保存的草稿无法读取，请重新载入示例或生成。',true)}
 async function init(){const params=new URLSearchParams(location.search),project=params.get('project');
  try{voiceLibrary=await api('/api/voice-library');const requested=params.get('preset');if(requested&&project===null){window.WhiteboardSpeech?.set({backend:'local'});if(spec){spec.voice_preset_id=requested;$('voice-speed').value=''}}if(spec){const currentStage=stage;renderEditor();setStage(currentStage);if(project===null)store()}$('voice-library-status').textContent='可在音色库按题材挑选。参考试听播放原录音。'}catch(error){$('voice-library-status').textContent='音色库读取失败：'+error.message}
  if(project!==null){try{await loadProject(project)}catch(error){message('无法载入指定项目：'+error.message,true)}}
  // A navigation to a particular project must never be replaced by an older pending draft.
  if(project!==null){try{const pending=StudioStorage.session.getItem('whiteboard-pending-draft');if(pending)handledDrafts.add(pending)}catch{}}
  poll();health();setInterval(poll,2500);setInterval(health,30000);
 }
 for(const control of document.querySelectorAll('[data-stage]'))control.onclick=()=>{setStage(control.dataset.stage);store()};
 $('open-voice').onclick=()=>{$('voice-feedback').textContent='';$('voice-dialog').showModal()};$('close-voice').onclick=()=>{$('voice-dialog').close();store()};$('voice-dialog').addEventListener('close',()=>{$('cast-preview-audio').pause();store();$('open-voice').focus()});
 init();
})();
