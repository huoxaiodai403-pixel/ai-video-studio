/* Whiteboard editor: all topic/model output is treated as text, never HTML. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id), key='ai-studio-whiteboard-v1';
 const layouts={opening:'开场 · 问题与主张',compare:'对比 · 并列关系',steps:'步骤 · 顺序推进',summary:'总结 · 回顾重点'};
 const operationNames={draft:'AI 分镜',preview:'静帧预览',render:'有声视频'};
 let spec=null, polling=false, environmentReady=null,voiceLibrary={presets:[],default_preset_id:null},cast=[];
 const handledDrafts=new Set(), taskNodes=new Map();
 function node(tag,text,className){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(className)item.className=className;return item}
 function message(value,error=false){$('action-status').textContent=value;$('action-status').className=error?'error-text':'success-text'}
 async function api(path,data){const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||`请求失败：${response.status}`);return result}
 function store(){if(!spec)return;spec.title=$('video-title').value;spec.voice_preset_id=$('voice-preset').value;spec.characters=Object.fromEntries(cast.map(role=>[role.name,role.preset]));delete spec.character_preset_ids;spec.voice=$('voice-speed').value?{speed:Number($('voice-speed').value)}:{};try{localStorage.setItem(key,JSON.stringify({spec,speed:$('voice-speed').value}))}catch{}}
 function backupDraft(reason){
  store();const snapshot={saved_at:new Date().toISOString(),reason,spec:structuredClone(spec),speed:$('voice-speed').value,topic:$('topic').value,pendingDraft:sessionStorage.getItem('whiteboard-pending-draft')};
  let rows=[];try{rows=JSON.parse(localStorage.getItem(key+'-backups')||'[]')}catch{}if(!Array.isArray(rows))rows=[];
  try{localStorage.setItem(key+'-backups',JSON.stringify([...rows.slice(-4),snapshot]))}catch{throw Error('浏览器无法备份当前草稿，已停止替换。请先导出草稿并释放浏览器存储。')}
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
  backupDraft('载入项目 '+id);sessionStorage.removeItem('whiteboard-pending-draft');setSpec(value,true);
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
 function renderEditor(){
  $('editor-empty').hidden=!!spec;$('editor').hidden=!spec;if(!spec)return;
  $('video-title').value=spec.title;const selected=spec.voice_preset_id||'';const voiceSelect=presetSelect(selected,'跟随工作台默认音色');$('voice-preset').replaceChildren(...voiceSelect.childNodes);$('voice-preset').value=selected;renderCast();$('scenes').replaceChildren();
  spec.scenes.forEach((scene,index)=>{
   const article=node('article',undefined,'scene'),top=node('div',undefined,'scene-top'),tools=node('div',undefined,'toolbar');
   top.append(node('h3',`镜头 ${String(index+1).padStart(2,'0')}`));
   const moveUp=button('↑',()=>{[spec.scenes[index-1],spec.scenes[index]]=[spec.scenes[index],spec.scenes[index-1]];reindex();renderEditor();store()});moveUp.disabled=index===0;moveUp.setAttribute('aria-label',`向上移动镜头 ${index+1}`);
   const moveDown=button('↓',()=>{[spec.scenes[index+1],spec.scenes[index]]=[spec.scenes[index],spec.scenes[index+1]];reindex();renderEditor();store()});moveDown.disabled=index===spec.scenes.length-1;moveDown.setAttribute('aria-label',`向下移动镜头 ${index+1}`);
   const remove=button('移除',()=>{spec.scenes.splice(index,1);reindex();renderEditor();store()});remove.disabled=spec.scenes.length===1;remove.setAttribute('aria-label',`移除镜头 ${index+1}`);tools.append(moveUp,moveDown,remove);top.append(tools);article.append(top);
   const grid=node('div',undefined,'scene-grid'),left=node('div'),right=node('div');
   left.append(field('画面标题',input(scene.board_title,36,value=>{scene.board_title=value;scene.subject=value;store()})));
   const narrator=node('select');narrator.dataset.sceneSpeaker=String(index);narrator.onchange=()=>{scene.speaker=narrator.value;store()};const override=presetSelect(scene.voice_preset_id||'','跟随角色 / 全片音色');override.onchange=()=>{if(override.value)scene.voice_preset_id=override.value;else delete scene.voice_preset_id;store()};const voiceGrid=node('div',undefined,'scene-voice-grid');voiceGrid.append(field('说话角色',narrator),field('本镜头音色覆盖 · 可选',override));left.append(voiceGrid);
   const narration=input(scene.narration,600,value=>{scene.narration=value;delete scene.board_beats;store()},'textarea');narration.className='narration';left.append(field('旁白 / 角色台词 · 逐字配音',narration));
   const layout=node('select');for(const [value,label]of Object.entries(layouts)){const option=node('option',label);option.value=value;layout.append(option)}layout.value=scene.board_layout;layout.onchange=()=>{scene.board_layout=layout.value;store()};right.append(field('画面布局',layout));
   const sticker=node('select');for(const [value,label]of Object.entries({none:'不使用贴纸',reader:'阅读与思考',stepper:'行动与步骤',stuck:'困惑与问题',panicked:'惊讶与提醒'})){const option=node('option',label);option.value=value;sticker.append(option)}sticker.value=scene.board_sticker||'none';sticker.onchange=()=>{scene.board_sticker=sticker.value;store()};right.append(field('手绘人物贴纸',sticker));
   const cards=input(scene.board_cards.join('\n'),100,value=>{scene.board_cards=value.split('\n').map(s=>s.trim()).filter(Boolean);delete scene.board_beats;store()},'textarea');cards.rows=3;right.append(field('关键词 · 每行一个，共 1–3 个，每个最多 24 字',cards));
   right.append(node('p','关键词按旁白顺序出现。修改旁白或关键词后，渲染器会重新计算节拍。','small'));
   grid.append(left,right);article.append(grid);$('scenes').append(article);
  });
  refreshSpeakers();$('add-scene').disabled=spec.scenes.length>=8;
 }
 function setSpec(value,exact=false){const previous=spec;spec=structuredClone(value);if(!Object.hasOwn(value,'voice_preset_id'))spec.voice_preset_id=exact?'':previous?.voice_preset_id||new URLSearchParams(location.search).get('preset')||'';if(exact)$('voice-speed').value='';readCast();reindex();renderEditor();if(value.voice&&Object.hasOwn(value.voice,'speed'))$('voice-speed').value=String(value.voice.speed);store()}
 function payload(){if(!spec)throw Error('请先生成分镜或载入示例。');store();if(!spec.title.trim())throw Error('请填写视频标题。');for(const role of cast)if(!role.preset)throw Error(`请选择角色「${role.name}」的音色。`);for(let i=0;i<spec.scenes.length;i++){const scene=spec.scenes[i];if(!scene.board_title.trim()||!scene.narration.trim())throw Error(`请填写镜头 ${i+1} 的标题与旁白。`);if(scene.board_cards.length<1||scene.board_cards.length>3||scene.board_cards.some(s=>s.length>24))throw Error(`镜头 ${i+1} 需要 1–3 条关键词，每条最多 24 字。`)}return{storyboard:spec,...(spec.voice_preset_id?{voice_preset_id:spec.voice_preset_id}:{}),characters:spec.characters,voice:spec.voice,backends:{tts:'local',asr:'local'}}}
 async function submit(operation){const control=$(operation);control.disabled=true;try{const data=operation==='draft'?{topic:$('topic').value,count:Number($('scene-count').value)}:payload();if(operation==='draft'&&!data.topic.trim())throw Error('请先输入选题。');const result=await api(`/api/whiteboard/${operation}`,data);if(operation==='draft'){try{sessionStorage.setItem('whiteboard-pending-draft',result.job_id)}catch{}}message(`${operationNames[operation]}任务已提交：${result.job_id}`);await poll()}catch(error){message(error.message,true)}finally{control.disabled=false}}
 function downloadLink(url,label){const link=node('a',label);link.href=url;link.download='';return link}
 function taskCard(id,state){
  const article=node('article',undefined,'task'),header=node('div',undefined,'job-header');article.dataset.jobId=id;
  header.append(node('strong',state.title||operationNames[state.operation]),node('span',{queued:'排队中',running:'运行中',done:'已完成',error:'失败'}[state.status]||state.status,`task-state ${state.status}`));article.append(header,node('p',`${operationNames[state.operation]||'白板'} · ${id}`,'small'),node('p',state.phase||state.status));
  if(state.status==='running'||state.status==='queued'){const progress=node('progress');progress.setAttribute('aria-label',state.phase||'正在处理');article.append(progress)}
  if(state.error)article.append(node('p',state.error,'error-text'));
  if(state.storyboard||state.storyboard_url){const load=button('载入此分镜',async()=>{try{await loadProject(id,state);$('editor-title').scrollIntoView({behavior:'smooth',block:'start'})}catch(error){message(error.message,true)}},'secondary');article.append(load)}
  if(state.video){const video=node('video');video.src=state.video;video.controls=true;video.preload='metadata';article.append(video)}
  if(state.previews?.length){const details=node('details');details.open=!state.video;const images=node('div',undefined,'preview-grid');details.append(node('summary',`查看静帧预览（${state.previews.length} 张）`));state.previews.forEach((url,index)=>{const figure=node('figure'),link=node('a'),image=node('img');image.src=url;image.alt=`白板预览 ${index+1}`;image.loading='lazy';link.href=url;link.target='_blank';link.rel='noopener';link.append(image);figure.append(link,node('figcaption',decodeURIComponent(url.split('/').pop())));images.append(figure)});details.append(images);article.append(details)}
  const downloads=node('div',undefined,'download-row');if(state.video)downloads.append(downloadLink(state.video,'下载视频'));if(state.subtitle)downloads.append(downloadLink(state.subtitle,'下载字幕'));(state.covers||[]).forEach((url,index)=>downloads.append(downloadLink(url,`下载封面 ${index+1}`)));if(state.storyboard_url)downloads.append(downloadLink(state.storyboard_url,'分镜 JSON'));if(state.manifest_url)downloads.append(downloadLink(state.manifest_url,'素材清单'));if(downloads.childNodes.length)article.append(downloads);
  if(state.sources?.length){const details=node('details'),sources=node('div',undefined,'download-row');details.append(node('summary','下载可编辑 Excalidraw 源文件'));state.sources.forEach((url,index)=>sources.append(downloadLink(url,`镜头 ${index+1}`)));details.append(sources);article.append(details)}
  return article;
 }
 async function poll(){if(polling)return;polling=true;try{
  const jobs=await api('/api/jobs'),rows=Object.entries(jobs).filter(([,state])=>state.kind==='whiteboard').sort((a,b)=>(b[1].created||0)-(a[1].created||0));
  if(!rows.length){$('tasks').replaceChildren(node('p','暂无白板任务。载入示例即可开始。','small'));return}
  if(!taskNodes.size)$('tasks').replaceChildren();
  let pending=null;try{pending=sessionStorage.getItem('whiteboard-pending-draft')}catch{}
  for(const [id,state]of rows){const signature=JSON.stringify(state),old=taskNodes.get(id);if(old?.signature!==signature){const card=taskCard(id,state);if(old)old.node.replaceWith(card);else{const later=rows.slice(rows.findIndex(row=>row[0]===id)+1).find(row=>taskNodes.has(row[0]));if(later)$('tasks').insertBefore(card,taskNodes.get(later[0]).node);else $('tasks').append(card)}taskNodes.set(id,{signature,node:card})}
   if(id===pending&&state.status==='done'&&state.storyboard&&!handledDrafts.has(id)){handledDrafts.add(id);setSpec(state.storyboard);message('AI 分镜已载入，请逐镜头审阅后预览。');try{sessionStorage.removeItem('whiteboard-pending-draft')}catch{}}
   if(id===pending&&state.status==='error'){message(state.error,true);try{sessionStorage.removeItem('whiteboard-pending-draft')}catch{}}
  }
 }catch(error){message('读取任务失败：'+error.message,true)}finally{polling=false}}
 async function health(){try{const results=await Promise.allSettled([api('/api/whiteboard/status'),api('/api/story/status'),api('/api/services')]);const [renderer,story,services]=results;
  if(renderer.status==='fulfilled'){environmentReady=renderer.value.ready;$('renderer-health').textContent=environmentReady?'白板渲染已就绪':'白板渲染需配置';$('renderer-health').className=`status-pill ${environmentReady?'ready':'error'}`;$('environment').replaceChildren();for(const check of renderer.value.checks||[])$('environment').append(node('p',`${check.ready?'✓':'○'} ${check.name}：${check.message}`,'small'))}else{$('renderer-health').textContent='无法读取渲染状态';$('renderer-health').className='status-pill error'}
  if(story.status==='fulfilled'){$('story-health').textContent=story.value.ready?'本地编剧已就绪':'本地编剧未就绪';$('story-health').title=story.value.message;$('story-health').className=`status-pill ${story.value.ready?'ready':'error'}`}
  if(services.status==='fulfilled'){$('services').textContent=`千问生图：${services.value.comfyui.ready?'就绪':'未启动'} · 配音：${services.value.tts.ready?'就绪':'未启动'}`}
 }catch{}}
 $('draft').onclick=()=>submit('draft');$('preview').onclick=()=>submit('preview');$('render').onclick=()=>submit('render');$('refresh').onclick=()=>{poll();health()};
 $('example').onclick=async()=>{try{setSpec(await api('/api/whiteboard/example'));message('已载入内置示例。可直接生成静帧预览，也可以先编辑。')}catch(error){message(error.message,true)}};
 $('add-scene').onclick=()=>{if(spec.scenes.length>=8)return;spec.scenes.push({id:'new',narration:'',subject:'新镜头',style:'Excalidraw 手绘白板',board_title:'新镜头',board_layout:'steps',board_cards:['关键词']});reindex();renderEditor();store()};
 $('video-title').addEventListener('input',store);$('voice-speed').addEventListener('change',store);
 $('voice-preset').onchange=store;$('voice-preview').onclick=()=>previewVoice($('voice-preset').value);
 $('add-character').onclick=()=>{if(!spec||cast.length>=16)return;let number=cast.length+1;while(cast.some(role=>role.name===`角色${number}`))number++;cast.push({name:`角色${number}`,preset:$('voice-preset').value||voiceLibrary.default_preset_id||voiceLibrary.presets[0]?.id||''});renderCast();refreshSpeakers();store()};
 $('export-draft').onclick=()=>{try{const data=payload();const blob=new Blob([JSON.stringify(data.storyboard,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=downloadLink(url,'');link.download='whiteboard-storyboard.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){message(error.message,true)}};
 try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved?.spec?.scenes?.length){spec=saved.spec;readCast();$('voice-speed').value=saved.speed??'';renderEditor()}}catch{message('上次保存的草稿无法读取，请重新载入示例或生成。',true)}
 async function init(){const params=new URLSearchParams(location.search),project=params.get('project');
  try{voiceLibrary=await api('/api/voice-library');const requested=params.get('preset');if(requested&&spec&&project===null){spec.voice_preset_id=requested;$('voice-speed').value=''}if(spec){renderEditor();if(project===null)store()}$('voice-library-status').textContent='可在音色库按题材挑选。参考试听播放原录音。'}catch(error){$('voice-library-status').textContent='音色库读取失败：'+error.message}
  if(project!==null){try{await loadProject(project)}catch(error){message('无法载入指定项目：'+error.message,true)}}
  // A navigation to a particular project must never be replaced by an older pending draft.
  if(project!==null){try{const pending=sessionStorage.getItem('whiteboard-pending-draft');if(pending)handledDrafts.add(pending)}catch{}}
  poll();health();setInterval(poll,2500);setInterval(health,30000);
 }
 init();
})();
