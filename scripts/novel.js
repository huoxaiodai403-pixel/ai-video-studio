/* Novel and general production share one draft-preserving storyboard workspace. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id),api=Creation.api,S=StoryboardState,main=document.querySelector('main');
 const kind=document.body.dataset.storyKind,isNovel=kind==='novel',friend=document.documentElement.dataset.studioEdition==='friend';
 const key='ai-studio-'+kind+'-v2-'+(friend?'friend':'development'),backendKeys=['tts','asr','image','video'];
 let draft={title:'',scenes:[],characters:{},render_mode:'illustrated',editor:kind},selectedScene='',selectedJob='',loadedIdentity='',savedId='';
 let readyDraft=null,pending=null,submissions={},jobs={},rawDirty=false,rawText='',settingsReady=false,baseSettings=null,directorReady=false,methodPicker=null;
 let stages,initializing=true,submitting=false,polling=false,timer=null,stopped=false,blocked=false,resultSignature='',resultId='',resultVideo=null,compatibility='',storageLocked=false;
 const node=(tag,text,className)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(className)n.className=className;return n};
 const status=(text,error=false)=>{if(blocked)return;$('story-status').textContent=text;$('story-status').classList.toggle('error',error)};
 function download(name,value){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),link=node('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 function button(text,fn,className='secondary'){const b=node('button',text,className);b.type='button';b.onclick=fn;return b}
 function field(parent,label,value,{type='text',key='',rows=4,required=false,min,max,step,options}={}){
  const l=node('label',label,'form-field');let input;
  if(options)input=Creation.select(options,value??'');else{input=node(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.value=value??''}
  if(key)input.dataset.sceneField=key;if(type==='textarea')input.rows=rows;if(required)input.required=true;
  if(min!==undefined)input.min=min;if(max!==undefined)input.max=max;if(step!==undefined)input.step=step;
  l.append(input);parent.append(l);return input;
 }
 function settings(){return settingsReady?S.merge(draft.settings,Creation.read()):S.clone(draft.settings||{})}
 function collect(){
  draft.title=$('story-title').value;draft.editor=kind;if(isNovel){draft.source_text=$('novel-text').value;draft.director_method=methodPicker?.value??draft.director_method??''}
  draft.settings=settings();if(draft.voice_reference&&draft.settings.voice)draft.voice_reference=draft.settings.voice.reference;
  draft.backends=S.merge(draft.backends,Object.fromEntries(backendKeys.map(k=>[k,$('backend-'+k).value])));
  draft.motion_enabled=$('enable-motion').checked;return S.clone(draft);
 }
 function fingerprint(){return S.fingerprint(collect())}
 function form(){return isNovel?{mode:$('adapt-mode').value,count:$('scene-limit').value,style:$('novel-style').value}:{}}
 function store(){
  if(initializing)return;
  try{
   if(storageLocked)throw Error('原草稿读取失败且无法备份，原记录未被覆盖。请先下载或保存快照');
   const selected=Object.entries(submissions).filter(([id])=>id===selectedJob),recent=Object.entries(submissions).slice(-3);submissions=Object.fromEntries([...recent,...selected]);
   StudioStorage.local.setItem(key,JSON.stringify({schema:2,draft:collect(),selectedScene,selectedJob,loadedIdentity,savedId,stage:stages.current,form:form(),rawDirty,rawText:rawDirty?$('storyboard').value:'',pending,readyDraft,submissions}));
   $('draft-state').textContent='浏览器草稿已保留'+(savedId?' · 最近快照 '+savedId:'');
  }catch(e){$('draft-state').textContent='浏览器暂不能保存：'+e.message+'。请下载分镜备份。'}
  updateSummary();updateOrigin();
 }
 function backup(reason){
  const snapshot={saved_at:new Date().toISOString(),reason,draft:collect(),raw_json:rawDirty?$('storyboard').value:null};
  let rows=[];try{rows=JSON.parse(StudioStorage.local.getItem(key+'-backups')||'[]')}catch{}if(!Array.isArray(rows))rows=[];
  try{StudioStorage.local.setItem(key+'-backups',JSON.stringify([...rows.slice(-4),snapshot]))}catch{throw Error('浏览器无法备份当前稿件，已停止替换。请先下载分镜或释放存储。')}
  offerBackup(snapshot);return snapshot;
 }
 function offerBackup(snapshot){$('draft-backup').replaceChildren(node('span','替换前的稿件已备份。 '),button('下载最近备份',()=>download(kind+'-before-load.json',snapshot),'quiet'))}
 function available(select,value){return [...select.options].some(o=>o.value===value&&!o.disabled)}
 function setBackend(select,value){if(!available(select,value)){let option=[...select.options].find(o=>o.value===value);if(!option){option=new Option(value+' · 当前版本不可用',value);option.disabled=true;select.append(option)}}select.value=value}
 function defaultVoices(){
  draft.characters||={};
  for(const scene of draft.scenes)if(scene.speaker&&!draft.characters[scene.speaker])draft.characters[scene.speaker]=S.clone(draft.settings?.voice||{});
 }
 function applyDraft(value,{stage='story-review',identity='',resetRaw=true}={}){
  const wasInitializing=initializing;initializing=true;
  try{draft=S.check(value);draft.editor=kind;draft.render_mode||='illustrated';draft.characters||={};
  $('story-title').value=draft.title||'';if(isNovel)$('novel-text').value=draft.source_text||'';
  if(draft.voice_reference)draft.settings=S.merge(draft.settings,{voice:{reference:draft.voice_reference}});
  if(settingsReady){draft.settings=S.restoreSettings(baseSettings,draft.settings);Creation.set(draft.settings)}
  for(const k of backendKeys)setBackend($('backend-'+k),draft.backends?.[k]||(friend?'online':'local'));
  $('enable-motion').checked=!!draft.motion_enabled;
  if(methodPicker){methodPicker.value=draft.director_method||'';methodPicker.dispatchEvent(new Event('change'))}
  selectedScene=draft.scenes.some(s=>s.id===selectedScene)?selectedScene:draft.scenes[0]?.id||'';loadedIdentity=identity;
  defaultVoices();renderCharacters();renderScene();if(resetRaw){rawDirty=false;rawText='';$('storyboard').value=JSON.stringify(collect(),null,2)}
  if(stage)stages.show(stage,{notify:false});$('project-more').open=false;updateSummary();
  }finally{initializing=wasInitializing}store();
 }
 function replaceDraft(value,reason,options={}){const checked=S.check(value);backup(reason);savedId='';applyDraft(checked,options);status(reason+'。原稿已备份，尚未提交制作。')}
 function updateSummary(){
  const whiteboard=draft.render_mode==='whiteboard',motion=$('enable-motion').checked&&!whiteboard;
  $('image-source-label').hidden=whiteboard;$('video-source-label').hidden=!motion;$('enable-motion').closest('label').hidden=whiteboard;
  const needed=['tts','asr',...(!whiteboard?['image']:[]),...(motion?['video']:[])];
  compatibility=needed.some(k=>!available($('backend-'+k),$('backend-'+k).value))?'本稿指定了当前版本不可用的本地来源。请在制作设置中明确改选可用服务；原稿参数仍保留。':'';
  $('compatibility').textContent=compatibility;$('compatibility').hidden=!compatibility;
  $('production-summary').textContent=(draft.title||'未命名作品')+' · '+draft.scenes.length+' 个镜头 · '+(whiteboard?'旧版 Manim 白板':motion?'动态镜头':'静帧推拉')+'。服务选择和参数只用于本次任务。';
  $('produce').disabled=blocked||submitting||!settingsReady;
 }
 function updateOrigin(){
  const entry=submissions[selectedJob],changed=entry&&entry.fingerprint!==fingerprint();
  $('result-origin').dataset.changed=String(!!changed);
  $('result-origin').textContent=selectedJob?(entry?(changed?'当前稿件已有修改；下方结果仍对应之前提交的内容。':entry.loaded?'当前稿件来自该任务保存的分镜。':'下方结果对应本次提交的稿件。'):'这是已有任务的结果；尚未确认它与当前编辑稿件一致。'):'制作后在这里查看进度与成片。';
 }
 function renderCharacters(){
  const box=$('characters');box.replaceChildren();
  for(const [name,voice]of Object.entries(draft.characters||{})){
   const card=node('article',null,'card');card.append(node('h3',name));card.append(node('p',draft.character_links?.[name]?'角色库版本 '+draft.character_links[name].revision+' · 角色设定已绑定':'仅本稿 · 声音参数随当前分镜保存','small'));const grid=node('div',null,'grid');card.append(grid);
   const defs=friend?[['online_voice','在线音色 ID','text'],['speed','语速','number']]:voice.engine==='qwen3-custom'?[['qwen_speaker','Qwen3 声线','select'],['qwen_instruct','声音表达','text'],['speed','语速','number'],['online_voice','在线音色 ID','text']]:[['reference','本地参考音色','select'],['emotion','本地情感','select'],['intensity','情感强度','number'],['speed','语速','number'],['online_voice','在线音色 ID','text']];
   for(const [k,label,type]of defs){
    const options=k==='qwen_speaker'?['Vivian','Serena','Uncle_Fu','Dylan','Eric','Ryan','Aiden','Ono_Anna','Sohee'].map(v=>[v,v]):k==='reference'?(Creation.inventory?.voices||[]).map(v=>[v.path,v.name]):k==='emotion'?(Creation.inventory?.emotions||[]).map(v=>[v,v]):undefined;
    const input=field(grid,label,voice[k]??draft.settings?.voice?.[k]??(type==='number'?1:''),{type:type==='select'?'text':type,options,min:type==='number'?(k==='speed'?.5:0):undefined,max:type==='number'?(k==='speed'?2:.8):undefined,step:type==='number'?.05:undefined});
    input.setAttribute('aria-label',name+' '+label);input.oninput=()=>{voice[k]=type==='number'?Number(input.value):input.value};input.onchange=input.oninput;
   }
   const used=draft.scenes.some(s=>s.speaker===name||(s.character_ids||[]).includes(draft.character_links?.[name]?.id)),remove=button('移除角色',()=>{try{backup('移除角色 '+name);delete draft.characters[name];if(draft.character_links)delete draft.character_links[name];renderCharacters();renderScene();store()}catch(e){status(e.message,true)}},'quiet');remove.disabled=used;remove.title=used?'先将使用该角色的镜头改为其他角色':'移除未使用角色';card.append(remove);box.append(card);
  }
  if(!box.children.length)box.append(node('p','尚未添加角色。镜头可使用默认旁白。','small'));
 }
 function sceneField(parent,scene,key,label,type='text',options={}){
  const input=field(parent,label,scene[key]??'',{type,key,...options});input.oninput=()=>{scene[key]=type==='number'?Number(input.value):input.value};input.onchange=input.oninput;
  if(type!=='number')input.maxLength=2000;return input;
 }
 function renderScene(){
  const selector=$('scene-selector');selector.replaceChildren();for(const [index,scene]of draft.scenes.entries())selector.append(new Option((index+1)+' · '+scene.id+' · '+(scene.narration||'待填写旁白').slice(0,32),scene.id));
  const scene=draft.scenes.find(s=>s.id===selectedScene)||draft.scenes[0];selectedScene=scene?.id||'';selector.value=selectedScene;
  $('scene-count').textContent=draft.scenes.length+' / 12 个镜头';$('add-scene').disabled=draft.scenes.length>=12;
  const box=$('scene-editor');box.replaceChildren();
  if(!scene){selector.append(new Option('暂无镜头',''));box.append(node('p',isNovel?'先生成分镜，或添加一个镜头开始手动编写。':'添加镜头开始编写，或从“更多”载入示例、导入已有 JSON。','empty'));return}
  const index=draft.scenes.indexOf(scene);box.append(node('h3','镜头 '+(index+1)+' · '+scene.id));
  sceneField(box,scene,'narration','旁白 / 台词','textarea',{required:true});
  sceneField(box,scene,'subject','画面描述 · 人物、动作与场景','textarea',{required:true});
  const details=node('details',null,'workflow-details');details.append(node('summary','画风、角色与动作运镜'));const body=node('div',null,'detail-content');details.append(body);
  sceneField(body,scene,'style','画风','text',{required:true});
  const speaker=field(body,'说话角色',scene.speaker||'',{options:[['','默认旁白'],...Object.keys(draft.characters).map(name=>[name,name])]});speaker.dataset.sceneField='speaker';speaker.onchange=()=>{if(speaker.value)scene.speaker=speaker.value;else delete scene.speaker};
  const appearance=field(body,'本镜出场角色（可多选）','',{options:Object.entries(draft.character_links||{}).map(([name,link])=>[link.id,name])});appearance.multiple=true;appearance.size=3;for(const option of appearance.options)option.selected=(scene.character_ids||[]).includes(option.value);appearance.onchange=()=>{scene.character_ids=[...appearance.selectedOptions].map(o=>o.value);store()};
  sceneField(body,scene,'motion_prompt','动作与运镜','textarea');
  if(directorReady)Director.mountScene(body,scene,(prompt,plan)=>{if(!draft.scenes.includes(scene)){status('原镜头已变更，未应用此次运镜。',true);return}if(prompt!==scene.motion_prompt){try{backup('应用运镜到 '+scene.id);scene.motion_prompt=prompt;scene.camera_plan=plan;renderScene();store()}catch(e){status(e.message,true)}}});
  if(draft.render_mode==='whiteboard'){
   sceneField(body,scene,'board_title','白板标题');
   const cards=field(body,'白板卡片 · 每行一条，最多三条',(scene.board_cards||[]).join('\n'),{type:'textarea',key:'board_cards'});cards.oninput=()=>scene.board_cards=cards.value.split(/\r?\n/);
  }
  const extra=Object.keys(scene).filter(k=>!['id','narration','subject','style','speaker','motion_prompt','camera_plan','board_title','board_cards'].includes(k));
  if(extra.length)body.append(node('p','保留的独立字段：'+extra.join('、')+'。可在下方 JSON 中查看和修改；这些字段可能覆盖默认参数。','notice'));
  box.append(details);
  const actions=node('div',null,'toolbar scene-actions');
  for(const [label,offset]of [['上移',-1],['下移',1]]){
   const b=button(label,()=>{const target=index+offset;[draft.scenes[index],draft.scenes[target]]=[draft.scenes[target],scene];renderScene();store();$('scene-selector').focus()});b.disabled=index+offset<0||index+offset>=draft.scenes.length;actions.append(b);
  }
  actions.append(button('移除镜头',()=>{try{backup('移除镜头 '+scene.id);draft.scenes.splice(index,1);selectedScene=draft.scenes[Math.min(index,draft.scenes.length-1)]?.id||'';renderScene();store();$('scene-selector').focus()}catch(e){status(e.message,true)}},'quiet'));box.append(actions);
 }
 function validDraft(forProduction=false){
  if(rawDirty){stages.reveal($('storyboard'));throw Error('有尚未应用的 JSON 修改，请先应用，或用当前分镜更新 JSON。')}
  if(!$('story-title').value.trim()){stages.reveal($('story-title'));throw Error('请为影片填写标题。')}
  if(!draft.scenes.length){stages.show('story-review');$('add-scene').focus();throw Error('请先添加至少一个镜头。')}
  S.check(collect());
  if(forProduction){
   for(const scene of draft.scenes)for(const k of ['narration','subject','style'])if(typeof scene[k]!=='string'||!scene[k].trim()||scene[k].length>2000){selectedScene=scene.id;renderScene();stages.reveal($('scene-editor').querySelector('[data-scene-field="'+k+'"]'));throw Error('请填写 '+scene.id+' 的'+({narration:'旁白',subject:'画面描述',style:'画风'}[k])+'，不超过 2000 字。')}
   if(compatibility){stages.show('story-delivery');throw Error(compatibility)}
   if(!settingsReady)throw Error('本次参数尚未载入，请刷新后重试；当前文本已保留。');
   if(!stages.validate($('story-delivery'))||!stages.validate($('character-details')))return false;
  }
  return true;
 }
 function showPending(){
  const host=$('pending-draft');host.replaceChildren();host.hidden=!pending&&!readyDraft;
  if(pending)host.append(node('span','编剧任务 '+pending.id+' 正在处理。可以继续编辑，结果不会自动覆盖当前稿件。'));
  if(readyDraft){
   host.append(node('span','待审阅分镜已准备好 · '+(readyDraft.draft.scenes?.length||0)+' 个镜头。'));
   host.append(button('载入待审阅分镜',()=>{try{replaceDraft(readyDraft.draft,'已载入待审阅分镜');readyDraft=null;showPending();store()}catch(e){status(e.message,true)}}));
   host.append(button('下载待审阅稿',()=>download('pending-storyboard.json',readyDraft.draft),'quiet'));
  }
  if($('adapt'))$('adapt').disabled=blocked||!!pending;
 }
 async function listDrafts(){
  const selected=$('draft-list').value;
  try{const rows=await api('/api/drafts');$('draft-list').replaceChildren(new Option('选择已保存草稿',''));for(const row of rows)$('draft-list').append(new Option(row.title+' · '+row.id,row.id));$('draft-list').value=selected||savedId;$('draft-list-status').textContent='保存会创建新快照，保留旧版本。'}
  catch(e){$('draft-list-status').textContent='草稿列表读取失败：'+e.message+'。输入仍可保留或下载。'}
 }
 async function guardedLoad(load,reason,options={}){
  const before=fingerprint(),rawBefore=$('storyboard').value;
  const value=S.check(await load());
  if(before!==fingerprint()||rawBefore!==$('storyboard').value)throw Error('读取期间稿件已有修改，未覆盖。请再次载入，或先保存当前稿件。');
  replaceDraft(value,reason,options);
 }
 function safeProject(id){if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/.test(id))throw Error('制作工程编号无效。');return id}
 async function loadProject(id){safeProject(id);await guardedLoad(()=>api('/outputs/'+id+'/storyboard.json'),'已载入原任务分镜',{identity:'project:'+id});selectedJob=id;submissions[id]={fingerprint:fingerprint(),title:draft.title,loaded:true};main.dataset.currentProject=id;store()}
 async function handoff(){
  const params=new URLSearchParams(location.search),requested=params.get('draft'),project=params.get('project');
  if(requested===null&&project===null)return;
  try{
   if(requested!==null&&project!==null)throw Error('请一次打开一个草稿或制作工程。');
   const identity=requested!==null?'draft:'+requested:'project:'+project;
   if(loadedIdentity!==identity){
    if(requested!==null){
     if(!/^lib-[a-f0-9]{24}$/.test(requested))throw Error('草稿编号无效。');
     await guardedLoad(async()=>{const {item}=await api('/api/library/item?id='+encodeURIComponent(requested));if(item?.id!==requested||!['story','video'].includes(item.workflow)||!/^[a-f0-9]{12}$/.test(item.draft_id||''))throw Error('指定资源不是分镜草稿。');const url=new URL(item.download_url,location.origin);if(url.origin!==location.origin||url.pathname!=='/api/library/file'||url.searchParams.get('id')!==requested||url.hash)throw Error('草稿地址无效。');return api(url.pathname+url.search)},'已载入指定草稿',{identity});
    }else await loadProject(project);
   }else status('已恢复此工程的浏览器修订。需要原稿时，可在结果区重新载入任务分镜。');
   params.delete('draft');params.delete('project');history.replaceState(null,'',location.pathname+(params.size?'?'+params.toString():'')+location.hash);store();
  }catch(e){
   blocked=true;$('story-status').replaceChildren(node('span','无法载入指定工程：'+e.message+'。当前输入保留。 '));const link=node('a','返回本页草稿');link.href=location.pathname;$('story-status').append(link);$('story-status').classList.add('error');
   for(const id of ['produce','save-draft','adapt','load-draft','import','apply-json','template','board'])if($(id))$(id).disabled=true;updateSummary();
  }
 }
 function updateResult(){
  const selected=jobs[selectedJob],host=$('jobs');
  if(!selected){if(resultId){$('jobs-status').textContent='当前任务暂未出现在列表中，保留已有结果。';return}host.replaceChildren(node('p','还没有制片任务。准备分镜后可开始制作。','empty'));return}
  const signature=JSON.stringify([selected.status,selected.error,selected.phase,selected.video]);
  if(resultId===selectedJob&&signature===resultSignature)return;
  const path=mediaUrl(selected.video);
  if(resultId===selectedJob&&resultVideo&&!resultVideo.paused&&!resultVideo.ended&&resultVideo.getAttribute('src')!==path){$('jobs-status').textContent='任务状态已更新，当前播放结束后更新结果。';return}
  const keepVideo=resultId===selectedJob&&resultVideo&&resultVideo.getAttribute('src')===path?resultVideo:null,focus=host.contains(document.activeElement);
  const label={queued:'排队中',running:'制作中',done:'已完成',error:'失败',failed:'失败',interrupted:'已中断'}[selected.status]||selected.status;
  const state=node('p',selectedJob+' · '+label);host.replaceChildren(state);if(selected.phase)host.append(node('p',selected.phase,'small'));
  if(selected.error)host.append(node('p',selected.error,'error'));
  resultVideo=keepVideo;
  if(path){if(!resultVideo){resultVideo=node('video');resultVideo.controls=true;resultVideo.preload='metadata';resultVideo.playsInline=true;resultVideo.src=path;resultVideo.setAttribute('aria-label','当前制片结果');resultVideo.addEventListener('pause',updateResult);resultVideo.addEventListener('ended',updateResult)}host.append(resultVideo)}
  const actions=node('div',null,'downloads');
  if(path){const link=node('a','下载成片');link.href=path;link.download='';actions.append(link)}
  if(/^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/.test(selectedJob)){
   const id=selectedJob;
   actions.append(button('载入该任务分镜',async()=>{try{await loadProject(id)}catch(e){status(e.message,true)}},'quiet'));
   const link=node('a','下载任务分镜');link.href='/outputs/'+id+'/storyboard.json';link.download='';actions.append(link);
  }
  host.append(actions);resultId=selectedJob;resultSignature=signature;if(focus)$('result-selector').focus();
 }
 function mediaUrl(value){if(!value)return '';try{const url=new URL(value,location.origin);return url.origin===location.origin&&url.pathname.startsWith('/outputs/')?url.pathname+url.search:''}catch{return ''}}
 async function poll(){
  if(polling||stopped||document.hidden)return;polling=true;
  try{
   jobs=await api('/api/jobs');
   if(pending){
    const job=jobs[pending.id];
    if(job?.status==='done'){
     readyDraft={draft:S.check(S.merge(pending.base,job.storyboard)),job:pending.id};pending=null;showPending();store();status('编剧结果已准备好。当前稿件保留，点击「载入待审阅分镜」后再审阅。');
    }else if(job?.status==='error'){status('编剧失败：'+job.error+'。当前稿件保留。',true);pending=null;showPending();store()}
    else if(!job){status('编剧任务未出现在服务中，可能已重启。当前稿件保留，可以重新提交。',true);pending=null;showPending();store()}
   }
   const rows=Object.entries(jobs).filter(([,job])=>job.kind==='video').reverse();
   if(!selectedJob&&rows.length)selectedJob=rows[0][0];
   const current=rows.find(([id])=>id===selectedJob),recent=rows.slice(0,20);if(current&&!recent.some(([id])=>id===selectedJob))recent.push(current);
   const signature=JSON.stringify(recent.map(([id,job])=>[id,job.status]));
   if($('result-selector').dataset.signature!==signature){$('result-selector').replaceChildren(...(recent.length?recent.map(([id,job])=>new Option(id+' · '+({done:'已完成',error:'失败',running:'制作中',queued:'排队中'}[job.status]||job.status),id)):[new Option('暂无任务','')]));$('result-selector').dataset.signature=signature}
   $('result-selector').value=selectedJob;$('jobs-status').textContent='';updateResult();updateOrigin();
  }catch(e){$('jobs-status').textContent='任务更新失败，保留当前结果：'+e.message}
  finally{polling=false}
 }
 $('scene-selector').onchange=()=>{selectedScene=$('scene-selector').value;renderScene();store()};
 $('add-scene').onclick=()=>{if(draft.scenes.length>=12)return;const scene={id:S.nextId(draft.scenes),narration:'',subject:'',style:isNovel?$('novel-style').value:'自然电影感',motion_prompt:'缓慢推近，保持人物与场景一致。'};draft.scenes.push(scene);selectedScene=scene.id;renderScene();store();stages.reveal($('scene-editor').querySelector('[data-scene-field=narration]'))};
 CharacterPicker.mount($('character-library-picker'),actor=>{if(initializing||blocked||submitting||!settingsReady)throw Error('请等待当前稿件载入或提交完成');if(Object.hasOwn(draft.characters,actor.name))throw Error('本片已有同名角色，请保留当前角色，或先移除未使用角色后再带入');if(['__proto__','constructor','prototype'].includes(actor.name))throw Error('角色名不可用');backup('从角色库带入 '+actor.name);draft.character_links||={};draft.character_links[actor.name]={id:actor.id,revision:actor.revision};draft.characters[actor.name]=S.clone(actor.voice||settings().voice);if(actor.voice)setBackend($('backend-tts'),'local');renderCharacters();renderScene();store();status('已带入 '+actor.name+'，请在各镜头选择出场角色。'+(actor.reference_ids.length?'参考图生图需在本次参数中选择本地 FLUX.2 klein。':''))},status,fingerprint);
 $('add-character').onclick=()=>{const name=$('character-name').value.trim();if(!name)return;if(Object.hasOwn(draft.characters,name)||['__proto__','constructor','prototype'].includes(name)){status('该角色名称已存在或不可用。',true);return}if(Object.keys(draft.characters).length>=30){status('每稿最多 30 个角色。',true);return}draft.characters[name]=S.clone(settings().voice||{});$('character-name').value='';renderCharacters();renderScene();store()};
 $('review-next').onclick=()=>{try{if(validDraft(true))stages.show('story-delivery',{focus:true})}catch(e){status(e.message,true)}};
 $('storyboard').oninput=()=>{rawDirty=true;$('json-status').textContent='JSON 有未应用修改；当前可视分镜保持原稿。'};
 $('raw-details').ontoggle=()=>{if($('raw-details').open&&!rawDirty)$('storyboard').value=JSON.stringify(collect(),null,2)};
 $('refresh-json').onclick=()=>{try{if(rawDirty)backup('用当前分镜替换未应用 JSON');rawDirty=false;$('storyboard').value=JSON.stringify(collect(),null,2);$('json-status').textContent='已更新为当前分镜。';status('JSON 已更新为当前分镜，未应用的旧文字已备份。');store()}catch(e){status(e.message,true)}};
 $('apply-json').onclick=()=>{try{const value=S.check(JSON.parse($('storyboard').value));replaceDraft(value,'已应用分镜 JSON');$('json-status').textContent='JSON 已应用。'}catch(e){$('json-status').textContent=e instanceof SyntaxError?'JSON 格式有误，内容仍保留，请检查后重新应用。':e.message;stages.reveal($('storyboard'))}};
 $('export').onclick=()=>download(kind+'-storyboard.json',collect());
 $('import').onchange=async()=>{try{const file=$('import').files[0];if(!file)return;if(file.size>1500000)throw Error('分镜文件不能超过 1.5 MB。');await guardedLoad(async()=>{const value=JSON.parse(await file.text());return value.draft||value},'已导入分镜 JSON')}catch(e){status(e.message,true)}finally{$('import').value=''}};
 $('save-draft').onclick=async()=>{const b=$('save-draft');try{if(!validDraft())return;b.disabled=true;const value=collect(),before=S.fingerprint(value),result=await api('/api/drafts',value);savedId=result.id;store();status('已保存草稿快照 '+savedId+(before!==fingerprint()?'；保存期间的新修改仍在浏览器草稿中。':'。'));await listDrafts();$('draft-list').value=savedId}catch(e){status(e.message,true)}finally{b.disabled=blocked}};
 $('load-draft').onclick=async()=>{try{const id=$('draft-list').value;if(!/^[a-f0-9]{12}$/.test(id))throw Error('请选择已保存草稿。');await guardedLoad(()=>api('/api/drafts/'+id),'已载入已保存草稿',{identity:'saved:'+id});savedId=id;store()}catch(e){status(e.message,true)}};
 $('refresh-drafts').onclick=listDrafts;
 $('result-selector').onchange=()=>{resultVideo?.pause();selectedJob=$('result-selector').value;resultId='';resultSignature='';resultVideo=null;updateResult();store()};
 $('refresh').onclick=poll;
 $('produce').onclick=async()=>{if(submitting||blocked)return;try{if(!validDraft(true))return;submitting=true;updateSummary();const value=collect(),signature=S.fingerprint(value);status('正在提交这次审阅的分镜…');const r=await api('/api/produce',{storyboard:value});selectedJob=r.job_id;submissions[selectedJob]={fingerprint:signature,title:value.title};main.dataset.currentJobId=selectedJob;store();status('任务已提交 '+selectedJob+'。结果使用提交时的分镜与参数。');await poll()}catch(e){status(e.message,true)}finally{submitting=false;updateSummary()}};
 if(isNovel){
  $('manual-review').onclick=()=>stages.show('story-review',{focus:true});
  $('novel-file').onchange=async()=>{try{const file=$('novel-file').files[0];if(!file)return;if(file.size>200000)throw Error('请按章节导入小于 200 KB 的 UTF-8 TXT。');const before=fingerprint(),text=await file.text();if(text.length>16000)throw Error('本段超过 16000 字，请按章节拆分后导入。');if(before!==fingerprint())throw Error('读取期间内容已有修改，未替换。');backup('导入小说文本');$('novel-text').value=text;store();status('已导入小说片段。请选择分镜方式。')}catch(e){status(e.message,true)}finally{$('novel-file').value=''}};
  $('adapt').onclick=async()=>{
   if(pending||blocked)return;const b=$('adapt');
   try{
    if(rawDirty)throw Error('请先处理未应用的 JSON 修改，再生成新分镜。');
    if(!stages.validate($('source')))return;
    if(!$('novel-text').value.trim()){stages.reveal($('novel-text'));throw Error('请先输入小说片段。')}
    if(!available($('adapt-mode'),$('adapt-mode').value))throw Error('当前版本不提供所选编剧，请明确选择可用方式。');
    b.disabled=true;status('正在生成待审阅分镜…');const base=collect(),request={text:base.source_text,title:base.title||'小说分镜草稿',mode:$('adapt-mode').value,count:Number($('scene-limit').value),style:$('novel-style').value,director_method:base.director_method};
    const result=await api('/api/novel',request);
    if(result.job_id){pending={id:result.job_id,base};status('编剧任务已提交。可以继续编辑，完成后手动载入。')}
    else{readyDraft={draft:S.check(S.merge(base,result))};status('分段完成。当前稿件未替换，可载入待审阅分镜。')}
    showPending();store();poll();
   }catch(e){status(e.message,true)}finally{b.disabled=blocked||!!pending}
  };
 }else for(const [id,whiteboard]of [['template',false],['board',true]])$(id).onclick=async()=>{try{await guardedLoad(async()=>{const value=await api('/api/project-template');delete value.voice_reference;if(whiteboard){value.render_mode='whiteboard';for(const scene of value.scenes){scene.board_title='从内容到成片';scene.board_cards=['内容','画面','声音']}}return value},'已载入'+(whiteboard?'旧版 Manim':'两镜头')+'示例')}catch(e){status(e.message,true)}};
 let saved=null,rawSaved=null;
 try{rawSaved=StudioStorage.local.getItem(key);saved=JSON.parse(rawSaved||'null');if(!saved&&isNovel){rawSaved=StudioStorage.local.getItem('ai-studio-novel-v1');const legacy=JSON.parse(rawSaved||'null');if(legacy)saved={draft:legacy}}if(saved?.draft){draft=S.check(saved.draft);selectedScene=saved.selectedScene||'';selectedJob=saved.selectedJob||'';loadedIdentity=saved.loadedIdentity||'';savedId=saved.savedId||'';pending=saved.pending||null;readyDraft=saved.readyDraft||null;submissions=saved.submissions||{};rawDirty=!!saved.rawDirty;rawText=saved.rawText||''}}catch(e){
  try{if(!rawSaved)throw e;const recoveryKey=key+'-recovery-'+Date.now();StudioStorage.local.setItem(recoveryKey,rawSaved);StudioStorage.local.setItem(key+'-last-recovery',recoveryKey);status('旧草稿无法读取，原始记录已另存备份，可在“更多”下载：'+e.message,true)}catch{storageLocked=true;status('旧草稿无法读取，原记录仍保留。当前编辑请下载或保存快照：'+e.message,true)}
 }
 try{const recoveryKey=StudioStorage.local.getItem(key+'-last-recovery'),raw=recoveryKey&&StudioStorage.local.getItem(recoveryKey);if(raw)$('project-more').querySelector('.toolbar').append(button('下载无法读取的原记录',()=>download('draft-recovery.json',{raw_json:raw}),'quiet'))}catch{}
 stages=WorkflowStages({onchange:store});
 applyDraft(draft,{stage:saved?.stage||(isNovel?'source':'story-review'),identity:loadedIdentity,resetRaw:!rawDirty});
 if(rawDirty)$('storyboard').value=rawText;
 if(isNovel&&saved?.form){for(const [k,id]of [['mode','adapt-mode'],['count','scene-limit'],['style','novel-style']])if(saved.form[k]!==undefined){if(k==='mode')setBackend($(id),saved.form[k]);else $(id).value=saved.form[k]}}
 try{const rows=JSON.parse(StudioStorage.local.getItem(key+'-backups')||'[]');if(rows.length)offerBackup(rows.at(-1))}catch{}
 initializing=false;showPending();store();
 document.addEventListener('input',store);document.addEventListener('change',store);
 document.addEventListener('voices-updated',()=>{renderCharacters();store()});
 document.addEventListener('creation-settings-changed',()=>{if(!initializing)store()});
 const setup=Creation.ready.then(data=>{
  baseSettings=S.clone(data.settings);settingsReady=true;
  draft.settings=S.restoreSettings(baseSettings,draft.settings);Creation.set(draft.settings);defaultVoices();renderCharacters();updateSummary();store();
 }).catch(e=>{status('制作参数未能载入：'+e.message+'。文本仍可编辑和下载，刷新可重试。',true);updateSummary()});
 Director.ready.then(()=>{
  directorReady=true;
  if(isNovel){let picked='';try{picked=StudioStorage.session.getItem('director-method')||draft.director_method||'';StudioStorage.session.removeItem('director-method')}catch{}methodPicker=Director.methodSelect($('director-method-box'),picked)}
  renderScene();store();
 }).catch(e=>{if(isNovel)$('writer-health').textContent='导演工具暂不可用：'+e.message+'；仍可手动填写分镜和运镜。'});
 if(isNovel&&!friend)api('/api/story/status').then(state=>$('writer-health').textContent=state.message).catch(e=>$('writer-health').textContent='本地编剧状态暂不可用：'+e.message);
 listDrafts();
 const navigation=new URLSearchParams(location.search),loadingHandoff=navigation.has('draft')||navigation.has('project');
 if(loadingHandoff){main.inert=true;main.setAttribute('aria-busy','true');status('正在载入指定工程，请稍候… 当前浏览器稿件已保留。')}
 Promise.allSettled([setup,Director.ready]).then(handoff).finally(()=>{main.inert=false;main.removeAttribute('aria-busy')}).then(poll);timer=setInterval(poll,7000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll()});
 window.addEventListener('pagehide',()=>{store();stopped=true;clearInterval(timer)});
 window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;timer=setInterval(poll,7000);poll()}});
})();
