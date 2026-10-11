/* Investigation editor: source text, model output and paths are data only. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id),legacyKey='ai-studio-investigation-v1',edition=document.documentElement.dataset.studioEdition||'development',storageKey=legacyKey+'-'+edition;
 const modes={account:['账目','从单据和分配关系出发，逐项对照来源。'],cost:['代价','从具体的人与时间点出发，追踪后果。'],rules:['规则','从冲突现场回到条文和执行。'],process:['过程','按时间线推进，每章增加一个转折。'],compare:['对照','先确定参照样本，再找有依据的差异。'],identity:['身份','从实物、主体和证照出发，核对来源。']};
 const kinds={video:'真实视频',image:'图片',evidence:'证据截图',diagram:'机制图解'};
 let spec={version:1,render_mode:'investigation',mode:'investigation',title:'',topic:'',hot_relevance:'',narrative_mode:'rules',target_minutes:10,demo_mode:false,backend:'online',backends:{tts:'windows',asr:'synthesis'},sources:[],chapters:[],scenes:[]};
 let jobId=null,media=[],cast=[],library={presets:[],references:[]},pendingDraft=null,polling=false,actionBusy=false,pendingResource=null,allowPendingDraft=true;
 let flow,selectedChapter='',selectedScene='',selectedResult='',pendingFingerprint=null,readyDraft=null,submittedSnapshots={},loadingProject=0,latestJobs={},navigationError=false;
 const jobNodes=new Map();
 const node=(tag,text,className)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(className)item.className=className;return item};
 function status(text,error=false){if(navigationError)return;$('action-status').textContent=text;$('action-status').className='workflow-feedback'+(error?' error':'')}
 async function api(url,data){const response=await fetch(url,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok){const error=Error(result.error||`请求失败：${response.status}`);error.payload=result;throw error}return result}
 function button(label,callback,className='quiet'){const value=node('button',label,className);value.type='button';value.onclick=callback;return value}
 function field(label,control){const wrapper=node('label',undefined,'form-field');wrapper.append(node('span',label),control);return wrapper}
 function input(value,max,callback,type='input'){const item=node(type);item.value=value??'';if(max)item.maxLength=max;item.oninput=()=>{callback(item.value);store();coverage()};return item}
 function select(options,value,callback){const item=node('select');for(const [id,label]of options)item.append(new Option(label,id));if(value&&!options.some(([id])=>id===value))item.append(new Option(value+' · 未找到',value));item.value=value??'';item.onchange=()=>{callback(item.value);store();coverage()};return item}
 function numeric(value,min,max,callback,step=1){const item=input(value,null,value=>callback(Number(value)));item.type='number';item.min=min;item.max=max;item.step=step;return item}
 function uid(prefix,rows){let n=rows.length+1;while(rows.some(row=>row.id===prefix+String(n).padStart(3,'0')))n++;return prefix+String(n).padStart(3,'0')}
 function knownSourceOptions(){return[['','未关联来源'],...spec.sources.map(source=>[source.id,`${source.id} · ${source.title||'未命名来源'}`])]}
 function presetOptions(label='跟随全片旁白'){return[['',label],...library.presets.map(preset=>[preset.id,preset.name])]}
 function readTop(){spec.backends={tts:$('speech-source').value,asr:$('speech-source').value==='windows'?'synthesis':'local'};spec.backend=$('story-backend').value;spec.topic=$('topic').value;spec.hot_relevance=$('hot-relevance').value;spec.narrative_mode=$('narrative-mode').value;spec.target_minutes=Number($('target-minutes').value);spec.title=$('project-title').value;spec.mode=$('production-mode').value;spec.voice_preset_id=$('voice-preset').value;spec.character_preset_ids=Object.fromEntries(cast.map(role=>[role.name,role.preset]));}
 function fingerprint(){readTop();return JSON.stringify({storyboard:spec,media,cast})}
 function store(){
  readTop();$('title-summary').textContent=spec.title?'影片标题 · '+spec.title:'影片标题与工程信息';
  for(const id of Object.keys(submittedSnapshots).slice(0,-3))if(id!==selectedResult&&id!==jobId)delete submittedSnapshots[id];
  try{$('draft-state').classList.remove('error');StudioStorage.local.setItem(storageKey,JSON.stringify({jobId,storyboard:spec,media,pendingDraft,pendingFingerprint,readyDraft,submittedSnapshots,selectedChapter,selectedScene,selectedResult,stage:flow?.current}));$('draft-state').textContent='浏览器草稿已保留 · '+(jobId?'已有项目快照':'尚未保存项目快照')}
  catch{$('draft-state').textContent='浏览器存储失败，请下载项目 JSON 保存';$('draft-state').classList.add('error')}
  resultOrigin();systemVoiceNotice();
 }
 function resultOrigin(){
  const host=$('result-origin'),state=latestJobs[selectedResult],submitted=submittedSnapshots[selectedResult];if(!host)return;
  if(!state){host.textContent='暂无选中的调查任务。';return}
  const known=submitted&&submitted.operation===state.operation&&submitted.created===state.created;
  const changed=known&&submitted.signature!==fingerprint();host.dataset.changed=String(changed);
  host.textContent=state.operation==='save'?'这是项目保存记录。已有媒体可能来自较早的制作任务。':changed?'稿件已修改；下面的结果仍对应此前提交内容。重新制作后才会更新。':known?'结果对应本页提交时的稿件。请审阅实际画面和声音。':'这是已有任务的结果，尚未与当前草稿核对。保存稿件不会更新已有媒体。';
 }
 function renderDraftReady(){
  const host=$('draft-ready');host.hidden=!readyDraft;if(!readyDraft){host.replaceChildren();return}
  host.replaceChildren(node('p','分章草稿已完成。当前编辑内容保持不变，载入前会自动备份。'),button('载入待审阅草稿',async()=>{try{await loadProject(readyDraft.id)}catch(error){status(error.message,true)}},'secondary'));
 }
 function systemVoiceNotice(){
  const system=spec.backends?.tts==='windows';$('cast-details').hidden=system;const local=Boolean(spec.voice_preset_id||cast.length||spec.scenes.some(scene=>scene.voice_preset_id));

  let host=$('friend-voice-note');if(!host){host=node('div',undefined,'notice');host.id='friend-voice-note';$('action-status').after(host)}
  host.hidden=!system;if(!system)return;if(host.dataset.local===String(local))return;host.dataset.local=String(local);
  host.replaceChildren(node('p',local?'此稿件带有本地角色音色。请选择本地模型配音，或明确改用系统旁白后再制作。':'当前使用 Windows 系统旁白与同次合成时间戳，无需下载模型。'));
  if(local)host.append(button('将本稿改为系统旁白',()=>{backupDraft('改为系统旁白');delete spec.voice_preset_id;cast=[];spec.character_preset_ids={};spec.characters={};for(const scene of spec.scenes){delete scene.voice_preset_id;delete scene.voice;scene.speaker='旁白'}renderAll();store();status('已将本稿改为系统旁白，旧音色版本已备份。')},'secondary'));
 }
 function failNavigation(message){
  navigationError=false;status(message.replace(/[。；]+$/,'')+'。当前草稿保持不变，返回编辑器后可继续。',true);navigationError=true;busyControls();
  const link=node('a','返回调查编辑器');link.href='/investigation';$('action-status').append(node('br'),link);
 }
 function busyControls(){
  for(const id of ['save','draft','preview','render','example','import'])$(id).disabled=actionBusy||navigationError||(id==='draft'&&Boolean(pendingDraft));
 }
 function backupDraft(reason){
  readTop();const snapshot={saved_at:new Date().toISOString(),reason,jobId,storyboard:structuredClone(spec),media:structuredClone(media),pendingDraft};
  let rows=[];try{rows=JSON.parse(StudioStorage.local.getItem(storageKey+'-backups')||'[]')}catch{}if(!Array.isArray(rows))rows=[];
  try{StudioStorage.local.setItem(storageKey+'-backups',JSON.stringify([...rows.slice(-4),snapshot]))}catch{throw Error('浏览器无法备份当前草稿，已停止替换。请先导出草稿并释放浏览器存储。')}
  offerBackup(snapshot);
 }
 function offerBackup(snapshot){
  let host=$('draft-backup');if(!host){host=node('div',undefined,'small');host.id='draft-backup';$('project-more').querySelector('.toolbar').append(host)}host.replaceChildren(node('span','载入前的浏览器草稿已备份。 '),button('下载备份',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'})),link=download(url,'');link.download='investigation-before-load.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)},'secondary'));
 }
 function projectContext(){let host=$('project-context');if(!host){host=node('p',undefined,'small');host.id='project-context';$('project-title').parentElement.after(host)}host.textContent=jobId?'当前编辑工程：'+jobId+'。保存会更新此工程的分镜；原视频不会自动重渲染。':'当前为未保存的浏览器草稿。';const main=document.querySelector('main');if(main)main.dataset.currentProject=jobId||'';$('title-summary').textContent=spec.title?'影片标题 · '+spec.title:'影片标题与工程信息';$('title-details').open=!spec.title}
 async function loadProject(id){
  if(actionBusy)throw Error('正在保存或登记素材，请完成后再切换工程。');
  if(!/^investigation-[a-f0-9]{10}$/.test(id))throw Error('调查项目编号无效。');
  const request=++loadingProject,before=fingerprint();
  const data=await api('/api/investigation/project?job_id='+encodeURIComponent(id));
  if(request!==loadingProject)return;
  if(data.job_id!==id)throw Error('返回的工程与所选编号不一致。');
  checkProject(data);
  if(before!==fingerprint())throw Error('载入期间草稿有修改，已保留当前内容。请再次载入工程。');
  backupDraft('载入项目 '+id);pendingDraft=null;pendingFingerprint=null;readyDraft=null;selectedResult=id;
  applyProject(data);renderDraftReady();busyControls();flow.show('production');status('已载入工程 '+id+'。原浏览器草稿已备份，请确认后再保存或制作。');
 }
 function checkProject(data){
  const value=data?.storyboard||data;
  for(const key of ['scenes','chapters','sources'])if(!Array.isArray(value?.[key])||value[key].some(row=>!row||typeof row!=='object'||typeof row.id!=='string'))throw Error('项目缺少有效的来源、章节或镜头数组。');
  if(value.scenes.length>96||value.chapters.length>12||value.sources.length>24)throw Error('项目超过 12 章、96 镜头或 24 条来源的限制。');
  return value;
 }
 function applyProject(data){const value=checkProject(data);spec=structuredClone(value);spec.mode=spec.mode||'investigation';spec.hot_relevance=spec.hot_relevance||'';spec.narrative_mode=spec.narrative_mode||'rules';spec.target_minutes=spec.target_minutes||10;jobId=data.job_id??null;media=Array.isArray(data.media)?data.media:[];cast=Object.entries(spec.character_preset_ids||spec.characters||{}).map(([name,preset])=>({name,preset:typeof preset==='string'?preset:''}));renderAll();renderPendingResource();showGaps(data.gaps);showDownloads(data.downloads);store()}
 function renderAll(){$('speech-source').value=spec.backends?.tts||'local';
  $('story-backend').value=spec.backend||'local';$('topic').value=spec.topic||'';$('hot-relevance').value=spec.hot_relevance||'';$('narrative-mode').value=spec.narrative_mode;$('target-minutes').value=spec.target_minutes;$('project-title').value=spec.title||'';$('production-mode').value=spec.mode;
  const chosen=spec.voice_preset_id||'';$('voice-preset').replaceChildren(...presetOptions('跟随工作台默认音色').map(([id,label])=>new Option(label,id)));if(chosen&&!library.presets.some(item=>item.id===chosen))$('voice-preset').append(new Option(chosen+' · 待加载',chosen));$('voice-preset').value=chosen;
  $('demo-info').hidden=!spec.demo_mode;$('narrative-help').textContent=modes[spec.narrative_mode]?.[1]||'';renderSources();renderAssets();renderCast();renderChapters();coverage();projectContext();systemVoiceNotice();
 }
 function renderSources(){
  $('sources').replaceChildren();if(!spec.sources.length)$('sources').append(node('p','添加公开报道、官方文件或原始声明，再编写调查草稿。','empty'));
  spec.sources.forEach(source=>{
   const card=node('details',undefined,'card');card.dataset.sourceId=source.id;card.open=!source.title;const summary=node('summary',`${source.id} · ${source.title||'新来源'}`),grid=node('div',undefined,'grid');
   grid.append(field('来源标题',input(source.title,300,value=>{source.title=value;summary.textContent=`${source.id} · ${value||'新来源'}`})),field('公开日期',input(source.published_at,100,value=>{source.published_at=value})),field('原始链接',input(source.url,2000,value=>{source.url=value})),field('审阅状态',select([['unreviewed','待人工核对'],['source_checked','已查阅原文，仍需核对事实'],['user_reviewed','已由我核对原文']],source.status||'unreviewed',value=>{source.status=value})));
   const content=field('支撑事实的原文或摘录 · AI 按此写稿',input(source.content,16000,value=>{source.content=value},'textarea'));content.classList.add('full');grid.append(content);const tools=node('div',undefined,'toolbar');
   tools.append(button('读取该网页正文',async()=>{try{if(!source.url)throw Error('先填写来源链接。');status('正在读取公开网页正文…');const before=JSON.stringify(source),project=spec;const result=await api('/api/investigation/source',{url:source.url});if(project!==spec||!spec.sources.includes(source)||before!==JSON.stringify(source))throw Error('读取期间来源有修改，已保留当前内容。请再次读取。');Object.assign(source,result.source,{id:source.id});renderSources();store();status('已读取网页内容，仍需人工核对事实与日期。')}catch(error){status(error.message,true)}},'secondary'),button('移除来源',()=>{if(spec.scenes.some(scene=>(scene.source_ids||[]).includes(source.id))||media.some(item=>item.source_id===source.id)){status('该来源已关联镜头或素材，请先解除关联。',true);return}spec.sources=spec.sources.filter(item=>item!==source);renderSources();renderAssets();store()}));card.append(summary,grid,tools);$('sources').append(card);
  });$('add-source').disabled=spec.sources.length>=24;
 }
 function coverage(){
  const scenes=spec.scenes||[],associated=scenes.filter(scene=>scene.kind==='diagram'||media.some(item=>item.id===scene.media_id)).length,reviewed=scenes.filter(scene=>['user_reviewed','analysis'].includes(scene.fact_status)).length,chars=scenes.reduce((sum,scene)=>sum+(scene.narration||'').length,0);
  $('coverage').replaceChildren();for(const [value,label]of [[spec.chapters.length+' / '+scenes.length,'章节 / 镜头'],[`${associated} / ${scenes.length}`,'有素材关联或图解'],[`${reviewed} / ${scenes.length}`,'人工审阅 / 解释段'],[chars,'旁白字数 · 非实际时长']]){const metric=node('div',undefined,'metric');metric.append(node('strong',String(value)),node('span',label));$('coverage').append(metric)}
 }
 function renderAssets(){
  $('assets').replaceChildren();if(!media.length)$('assets').append(node('p','尚未导入素材。完成分镜后保存项目，再登记已有本地文件。','small'));
  for(const item of media){const card=node('details',undefined,'card');card.append(node('summary',`${item.id} · ${item.kind==='audio'?'音频素材':kinds[item.kind]||item.kind} · ${item.description||item.path?.split(/[\\/]/).pop()||'本地素材'}`));card.append(node('p',`${item.source_id||'未关联来源'}${item.kind==='audio'?'':` · ${item.width||'?'} × ${item.height||'?'}`}${item.duration?' · '+Number(item.duration).toFixed(1)+' 秒':''}`,'small'));if(item.preview_url){const tag=item.kind==='video'?'video':item.kind==='audio'?'audio':'img',preview=node(tag);preview.src=item.preview_url;preview.style.maxWidth='100%';preview.style.maxHeight='280px';if(tag!=='img'){preview.controls=true;preview.preload='none'}else{preview.alt=item.description||'素材预览';preview.loading='lazy'}card.append(preview)}$('assets').append(card)}
  if(spec.bgm?.mode==='media'){const track=media.find(row=>row.id===spec.bgm.media_id),line=node('div',undefined,'notice');line.append(node('span','本片背景音乐：'+(track?.description||track?.name||spec.bgm.media_id)+'。 '),button('取消背景音乐',()=>{spec.bgm={mode:'none'};store();renderAssets();status('已从本次草稿移除背景音乐，请保存后再制作。')}));$('assets').append(line)}
 }
 async function importMedia(){
  try{if(!spec.scenes.length)throw Error('请先生成或添加分镜，再保存项目和导入素材。');await saveProject(false);const data={job_id:jobId,path:$('media-path').value.trim(),kind:$('media-kind').value,description:$('media-description').value.trim()};if($('media-source').value)data.source_id=$('media-source').value;if(!data.path)throw Error('请填写已有素材的绝对路径。');$('media-import').disabled=true;status('正在校验并复制本地素材…');const result=await api('/api/investigation/media',data);media=Array.isArray(result.media)?result.media:[...media,result.item||result.media];$('media-import-panel').hidden=true;renderAssets();renderChapters();store();coverage();status('素材已登记。请在对应镜头中选择这份素材。')}catch(error){status(error.message,true)}finally{$('media-import').disabled=false}
 }
 function safeLibraryPreview(value){try{const url=new URL(value,location.origin);return url.origin===location.origin&&(url.pathname.startsWith('/outputs/')||['/api/library/file','/api/image-references/preview'].includes(url.pathname))?url.href:''}catch{return''}}
 function reusableResource(item){return item&&item.status==='done'&&['image','video','audio'].includes(item.media_type)&&typeof item.absolute_path==='string'&&item.absolute_path.length>0}
 async function resourceItem(id){if(!/^lib-[a-f0-9]{24}$/.test(id))throw Error('资源编号无效。');const {item}=await api('/api/library/item?id='+encodeURIComponent(id));if(item?.id!==id||!reusableResource(item))throw Error('这份资源未完成、已不存在，或不能作为调查素材使用。');return item}
 async function chooseResource(id){try{pendingResource=await resourceItem(id);renderPendingResource();status('资源已待加入，请选择保存目标后点击加入。尚未修改任何工程。');flow.show('production');$('asset-details').open=true;$('library-pending').scrollIntoView({behavior:'instant',block:'nearest'})}catch(error){new URLSearchParams(location.search).has('resource')?failNavigation('资源载入失败：'+error.message):status('资源载入失败：'+error.message,true)}}
 async function openResourcePicker(){
  const host=$('library-picker');host.hidden=false;host.replaceChildren(node('p','正在读取可复用资源…','small'));
  try{const results=await Promise.all([api('/api/library?view=assets&status=done'),api('/api/library?view=products&status=done')]),rows=new Map();
   for(const [index,result]of results.entries())for(const item of result.items||[])if(reusableResource(item)&&(index===0||['image','video'].includes(item.media_type)))rows.set(item.id,item);
   host.replaceChildren(node('h3','选择已完成的素材'),node('p','加入时复制到当前项目；来源需在本项目中重新关联。音效仅登记为素材，不会自动循环播放。','small'));
   const search=node('input');search.placeholder='搜索资源名称或工程编号';search.setAttribute('aria-label','搜索可复用资源');host.append(search);const list=node('div',undefined,'grid');host.append(list);
   const draw=()=>{list.replaceChildren();const term=search.value.trim().toLowerCase();for(const item of rows.values()){if(term&&!`${item.title} ${item.project_id||''}`.toLowerCase().includes(term))continue;const card=node('div',undefined,'card');card.append(node('strong',item.title||item.id),node('p',`${item.media_type} · ${item.workflow||item.kind} · ${item.project_id||'资源库'}`,'small'));const preview=safeLibraryPreview(item.thumbnail_url||(item.media_type==='image'?item.preview_url:''));if(preview){const img=node('img');img.src=preview;img.alt=item.title||'资源预览';img.loading='lazy';img.style.maxWidth='100%';img.style.maxHeight='160px';card.append(img)}card.append(button('选择这份资源',()=>chooseResource(item.id),'secondary'));list.append(card)}if(!list.childNodes.length)list.append(node('p','没有匹配的已完成素材。','small'))};search.oninput=draw;draw();
   host.append(button('收起资源库',()=>{host.hidden=true}));
  }catch(error){host.replaceChildren(node('p','无法读取资源库：'+error.message,'error'))}
 }
 function renderPendingResource(){
  const host=$('library-pending');if(!host)return;host.replaceChildren();host.hidden=!pendingResource;if(!pendingResource)return;
  const item=pendingResource;host.append(node('h3','待加入：'+(item.title||item.id)),node('p',`${item.workflow||item.kind} · ${item.project_id||'资源库'}。原工程不会因打开本页而改变。`,'small'));
  const preview=safeLibraryPreview(item.preview_url);if(preview){const tag=item.media_type==='audio'?'audio':item.media_type==='video'?'video':'img',element=node(tag);element.src=preview;element.style.maxWidth='100%';element.style.maxHeight='220px';if(tag==='img'){element.alt=item.title||'待加入素材'}else{element.controls=true;element.preload='none'}host.append(element)}
  const target=node('select');target.id='library-target';target.append(new Option('请选择保存目标',''));if(jobId)target.append(new Option('保存并加入当前工程 '+jobId,'current'));target.append(new Option(jobId?'另存当前分镜为新工程，并复制已有素材':'将当前草稿保存为新工程后加入','new'));host.append(field('加入哪个工程',target));
  host.append(node('p','请先有可保存的分镜。新工程会复制当前分镜和已有素材；新引入资源不继承其他工程的来源 ID。','small'));
  const actions=node('div',undefined,'toolbar');actions.append(button('保存并加入素材',()=>addLibraryResource(false),'secondary'));
  if(item.workflow==='music'&&item.media_type==='audio')actions.append(button('保存并用作背景音乐',()=>addLibraryResource(true),'secondary'));
  if(item.workflow==='sfx')host.append(node('p','这是音效。当前长片尚无逐点音效轨道，本次只能登记素材，不会作为循环背景音乐。','notice'));
  actions.append(button('取消带入',()=>{if(actionBusy)return;pendingResource=null;renderPendingResource()}));host.append(actions);
 }
 async function duplicateProject(){
  const oldJob=jobId,oldMedia=structuredClone(media),copies=[];
  // Resolve all paths from the current allowlisted catalog before creating the new project.
  if(oldMedia.length){const catalog=await api('/api/library?view=assets&status=done');for(const item of oldMedia){const match=(catalog.items||[]).find(row=>row.sha256&&row.sha256===item.sha256&&row.media_type===(item.kind==='evidence'?'image':item.kind));if(!match)throw Error('无法复制已有素材 '+item.id+'，请先在资源库核对该文件。');copies.push({old:item,resource:await resourceItem(match.id)})}}
  backupDraft('另存新工程');jobId=null;
  try{await saveProject(false)}catch(error){jobId=oldJob;projectContext();store();throw error}
  media=[];renderAssets();projectContext();
  for(const copy of copies){const result=await api('/api/investigation/media',{job_id:jobId,path:copy.resource.absolute_path,kind:copy.old.kind,description:copy.old.description||''});media=result.media;for(const scene of spec.scenes)if(scene.media_id===copy.old.id)scene.media_id=result.item.id;if(spec.bgm?.media_id===copy.old.id)spec.bgm.media_id=result.item.id;store()}
  await saveProject(false);renderAssets();renderChapters();
 }
 async function addLibraryResource(asBgm){
  if(actionBusy)return;const target=$('library-target')?.value;if(!pendingResource)return;if(!target)return status('请明确选择当前工程或另存新工程。',true);
  if(!spec.scenes.length)return status('请先添加或载入分镜，再保存并加入这份资源。待加入卡会保留。',true);
  actionBusy=true;for(const control of $('library-pending').querySelectorAll('button,select'))control.disabled=true;
  try{payload();const item=await resourceItem(pendingResource.id);if(asBgm&&(item.workflow!=='music'||item.media_type!=='audio'))throw Error('只有资源库中的配乐可以直接用作背景音乐。');
   if(target==='new'&&jobId)await duplicateProject();else if(target==='current'&&!jobId)throw Error('当前工程已改变，请重新选择保存目标。');else await saveProject(false);
   status('正在复制资源到工程 '+jobId+'…');const kind=item.media_type==='image'&&item.asset_kind==='evidence'?'evidence':item.media_type;
   const result=await api('/api/investigation/media',{job_id:jobId,path:item.absolute_path,kind,description:(item.title||'资源库素材').slice(0,1000)});media=result.media;
   if(asBgm)spec.bgm={...(spec.bgm||{}),mode:'media',media_id:result.item.id};
   await saveProject(false);pendingResource=null;renderAssets();renderChapters();renderPendingResource();coverage();projectContext();store();
   status((asBgm?'已设置背景音乐':'素材已加入')+'：'+jobId+'。'+(asBgm?'重新制作后生效。':'请在镜头中选择素材，并按需要关联本项目来源。'));
  }catch(error){renderAssets();renderChapters();coverage();projectContext();store();status('资源未全部加入：'+error.message+(jobId?'；当前工程 '+jobId+' 已保留已完成的步骤。':''),true)}finally{actionBusy=false;if(pendingResource)renderPendingResource()}
 }
 function previewVoice(){const id=$('voice-preset').value||library.default_preset_id,preset=library.presets.find(item=>item.id===id)||library.references.find(item=>item.path===library.default_voice?.reference);if(!preset?.preview_url){status('当前音色没有可试听的参考录音。',true);return}const audio=$('voice-audio');if(audio.getAttribute('src')!==preset.preview_url)audio.src=preset.preview_url;audio.hidden=false;audio.play().catch(()=>status('请点击播放器开始试听。'))}
 function renderCast(){
  $('characters').replaceChildren();cast.forEach((role,index)=>{const row=node('div',undefined,'role-row'),name=input(role.name,32,()=>{});name.onchange=()=>{const next=name.value.trim();if(!next||next==='旁白'||cast.some((other,i)=>i!==index&&other.name===next)||! /^[\p{L}\p{N} _·-]+$/u.test(next)){name.value=role.name;status('角色名需唯一，仅使用中英文、数字、空格和 _-·。',true);return}const old=role.name;if(spec.character_links?.[old]){name.value=old;status('角色库绑定名称保持不变，请在角色库另建角色后带入。',true);return}role.name=next;spec.scenes.forEach(scene=>{if(scene.speaker===old)scene.speaker=next});renderChapters();store()};row.append(field('角色名',name),field('音色预设',select(presetOptions('请选择角色音色'),role.preset,value=>{role.preset=value})),button('移除',()=>{cast.splice(index,1);if(spec.character_links)delete spec.character_links[role.name];spec.scenes.forEach(scene=>{if(scene.speaker===role.name)scene.speaker='旁白'});renderCast();renderChapters();store()}));$('characters').append(row)});$('add-character').disabled=cast.length>=16;
 }
 function addScene(chapter){if(spec.scenes.length>=96){status('最多 96 个镜头。',true);return}const scene={id:uid('s',spec.scenes),chapter_id:chapter.id,narration:'',speaker:'旁白',kind:'diagram',media_id:null,media_start:0,heading:'',badge:'',text:'',points:[],source_ids:[],fact_status:'needs_review',visual_brief:''};const rank=spec.chapters.indexOf(chapter),next=spec.scenes.findIndex(item=>spec.chapters.findIndex(ch=>ch.id===item.chapter_id)>rank);spec.scenes.splice(next<0?spec.scenes.length:next,0,scene);selectedChapter=chapter.id;selectedScene=scene.id;renderChapters();store()}
 function sceneCard(scene,index,chapterScenes){
  const card=node('article',undefined,'object-editor');card.dataset.sceneId=scene.id;
  const summary=node('h3',scene.id+' · '+(scene.heading||'编辑当前镜头')),grid=node('div',undefined,'grid');
  const narration=input(scene.narration,500,value=>{scene.narration=value},'textarea');narration.className='narration';narration.dataset.field='narration';
  const text=field('旁白 / 台词 · 每段最多 500 字',narration);text.classList.add('full');grid.append(text);
  grid.append(field('画面类型',select(Object.entries(kinds),scene.kind||'diagram',value=>{scene.kind=value;scene.media_id=null;renderChapters()})),field('事实审阅状态',select([['needs_review','待人工核对'],['source_checked','已查阅出处，仍需核对事实'],['user_reviewed','已由我核对来源'],['analysis','解释 / 分析段']],scene.fact_status||'needs_review',value=>{scene.fact_status=value})));
  const sources=node('details',undefined,'workflow-details');sources.append(node('summary','支撑来源 · 已选 '+(scene.source_ids||[]).length+' 条'));
  const sourceList=node('div',undefined,'source-choices detail-content');for(const source of spec.sources){const box=node('input');box.type='checkbox';box.checked=(scene.source_ids||[]).includes(source.id);const label=node('label');label.append(box,node('span',source.id+' · '+(source.title||'未命名来源')));box.onchange=()=>{scene.source_ids=box.checked?[...new Set([...(scene.source_ids||[]),source.id])]:(scene.source_ids||[]).filter(id=>id!==source.id);sources.querySelector('summary').textContent='支撑来源 · 已选 '+scene.source_ids.length+' 条';store()};sourceList.append(label)}
  if(!spec.sources.length)sourceList.append(node('p','尚无来源，请返回第一步添加。','small'));
  const missing=(scene.source_ids||[]).filter(id=>!spec.sources.some(source=>source.id===id));if(missing.length)sourceList.append(node('p','部分来源已不存在：'+missing.join('、')+'。请在项目 JSON 中修正。','error'));
  sources.append(sourceList);
  const details=node('details',undefined,'workflow-details');details.append(node('summary','画面内容、素材与镜头音色'));const advanced=node('div',undefined,'grid detail-content');
  advanced.append(field('画面短标题',input(scene.heading,80,value=>{scene.heading=value;summary.textContent=scene.id+' · '+(value||'编辑当前镜头');const option=[...$('scene-selector').options].find(row=>row.value===scene.id);if(option)option.textContent=scene.id+' · '+(value||'待编辑镜头')})),field('短标记 · 日期 / 资料画面',input(scene.badge,80,value=>{scene.badge=value})),field('说话角色',select([['旁白','旁白 · 全片音色'],...cast.map(role=>[role.name,role.name])],scene.speaker||'旁白',value=>{scene.speaker=value})),field('本镜头音色覆盖 · 可选',select(presetOptions('跟随角色 / 全片音色'),scene.voice_preset_id||'',value=>{if(value)scene.voice_preset_id=value;else delete scene.voice_preset_id})),field('已登记素材',select([['','图解可留空；证据可用绑定来源的逐字摘录'],...media.filter(item=>scene.kind==='diagram'||item.kind===scene.kind||(scene.kind==='evidence'&&item.kind==='image')).map(item=>[item.id,item.id+' · '+(item.description||item.path?.split(/[\\/]/).pop()||item.kind)])],scene.media_id||'',value=>{scene.media_id=value||null})),field('视频使用起点 · 秒',numeric(scene.media_start||0,0,86400,value=>{scene.media_start=value},0.1)),field('证据摘录 / 说明文字',input(scene.text,1200,value=>{scene.text=value},'textarea')),field('图解要点 · 最多 6 行，每行 100 字',input((scene.points||[]).join('\n'),606,value=>{scene.points=value.split('\n').map(item=>item.trim()).filter(Boolean)},'textarea')));
  if(scene.kind==='diagram')advanced.append(field('图解布局',select([['flow','流程'],['compare','对比'],['timeline','时间线'],['checklist','检查清单']],scene.diagram_layout||'flow',value=>{scene.diagram_layout=value})));
  if(spec.backends?.tts==='windows')for(const label of advanced.children)if(/说话角色|本镜头音色覆盖/.test(label.firstElementChild?.textContent||''))label.hidden=true;
  advanced.append(field('画面用途 / 素材缺口',input(scene.visual_brief,1000,value=>{scene.visual_brief=value},'textarea')));details.append(advanced);
  const toolbar=node('div',undefined,'toolbar');
  const move=offset=>{const other=chapterScenes[index+offset],a=spec.scenes.indexOf(scene),b=spec.scenes.indexOf(other);if(b<0)return;[spec.scenes[a],spec.scenes[b]]=[spec.scenes[b],spec.scenes[a]];renderChapters();store()};
  const up=button('镜头上移',()=>move(-1)),down=button('镜头下移',()=>move(1));up.disabled=index===0;down.disabled=index===chapterScenes.length-1;
  toolbar.append(up,down,button('移除镜头',()=>{spec.scenes=spec.scenes.filter(item=>item!==scene);selectedScene=chapterScenes[index+1]?.id||chapterScenes[index-1]?.id||'';renderChapters();coverage();store()}));card.append(summary,grid,sources,details,toolbar);return card;
 }
 function renderChapters(){
  const host=$('chapters');host.replaceChildren();$('add-chapter').disabled=spec.chapters.length>=12;
  if(!spec.chapters.length){host.append(node('p','尚无章节。先生成草稿，或添加章节手动编写。','empty'));return}
  if(!spec.chapters.some(chapter=>chapter.id===selectedChapter))selectedChapter=spec.chapters[0].id;
  const chapter=spec.chapters.find(row=>row.id===selectedChapter),scenes=spec.scenes.filter(scene=>scene.chapter_id===chapter.id);
  if(!scenes.some(scene=>scene.id===selectedScene))selectedScene=scenes[0]?.id||'';
  const selectors=node('div',undefined,'object-selector');
  const chapterSelect=select(spec.chapters.map((row,index)=>[row.id,(index+1)+' · '+(row.title||'未命名章节')]),chapter.id,value=>{selectedChapter=value;selectedScene='';renderChapters();$('chapter-selector').focus()});chapterSelect.id='chapter-selector';
  const sceneSelect=select(scenes.length?scenes.map(row=>[row.id,row.id+' · '+(row.heading||'待编辑镜头')]):[['','本章尚无镜头']],selectedScene,value=>{selectedScene=value;renderChapters();$('scene-selector').focus()});sceneSelect.id='scene-selector';sceneSelect.disabled=!scenes.length;
  selectors.append(field('当前章节 · '+spec.chapters.length+' 章',chapterSelect),field('当前镜头 · 本章 '+scenes.length+' 个',sceneSelect));const side=node('div',undefined,'chapter-side');side.append(selectors);host.append(side);
  const tools=node('div',undefined,'toolbar');tools.append(button('＋ 添加镜头',()=>addScene(chapter),'secondary'));
  const chapterDetails=node('details',undefined,'workflow-details');chapterDetails.append(node('summary','章节标题与概要'));const fields=node('div',undefined,'grid detail-content');
  const title=input(chapter.title,80,value=>{chapter.title=value;chapterSelect.selectedOptions[0].textContent=(spec.chapters.indexOf(chapter)+1)+' · '+(value||'未命名章节')});title.dataset.field='chapter-title';
  fields.append(field('章节标题',title),field('本章推进的事实 / 问题',input(chapter.summary,1000,value=>{chapter.summary=value})));chapterDetails.append(fields,button('移除空章节',()=>{if(scenes.length){status('请先移除该章节内的镜头，再移除章节。',true);return}spec.chapters=spec.chapters.filter(item=>item!==chapter);renderChapters();coverage();store()}));
  side.append(tools,chapterDetails);const scene=scenes.find(row=>row.id===selectedScene);if(scene)host.append(sceneCard(scene,scenes.indexOf(scene),scenes));else host.append(node('p','本章尚无镜头，请添加镜头。','empty'));
 }
 function invalidField(message,control){flow.reveal(control);throw Error(message)}
 function revealScene(scene,fieldName='narration'){selectedChapter=scene.chapter_id;selectedScene=scene.id;renderChapters();flow.reveal(document.querySelector('[data-field="'+fieldName+'"]'))}

 function payload(){
  if(navigationError)throw Error('请先返回调查编辑器，确认所编辑的工程。');store();if(spec.backends?.tts==='windows'&&(spec.voice_preset_id||cast.length||spec.scenes.some(scene=>scene.voice_preset_id)))throw Error('本稿包含本地角色音色，请先在页面提示中明确改为系统旁白。');if(!flow.validate())throw Error('请修正已定位的字段。');
  if(!spec.title?.trim())invalidField('请填写影片标题。',$('project-title'));
  if(!spec.scenes.length)invalidField('请先生成或添加分镜。',$('add-chapter'));
  for(const chapter of spec.chapters)if(!chapter.title?.trim()){selectedChapter=chapter.id;renderChapters();invalidField('请填写章节标题。',document.querySelector('[data-field="chapter-title"]'))}
  for(const scene of spec.scenes)if(typeof scene.narration!=='string'||!scene.narration.trim()||scene.narration.length>500){revealScene(scene);throw Error(scene.id+' 的旁白需填写 1–500 字。')}
  for(const role of cast)if(!role.preset){$('cast-details').open=true;invalidField('请选择角色「'+role.name+'」的音色。',$('characters').querySelector('select'))}
  return{...(jobId?{job_id:jobId}:{}),storyboard:spec,...(spec.voice_preset_id?{voice_preset_id:spec.voice_preset_id}:{}),characters:Object.fromEntries(cast.map(role=>[role.name,role.preset]))};
 }
 async function saveProject(announce=true){
  const data=payload(),signature=fingerprint(),project=spec,result=await api('/api/investigation/save',data);
  if(project!==spec)throw Error('项目已在后台保存，但当前编辑项目已切换。请在作品库中查看保存结果。');
  const unchanged=signature===fingerprint();if(!spec.settings&&result.storyboard?.settings)spec.settings=structuredClone(result.storyboard.settings);jobId=result.job_id;selectedResult=jobId;submittedSnapshots[jobId]={signature:unchanged?fingerprint():signature,operation:'save'};showGaps(result.gaps);showDownloads(result.downloads);projectContext();store();
  if(announce)status('项目快照已保存：'+jobId+(!unchanged?'；提交后的新修改仍在浏览器草稿中。':gapText(result.gaps)));return result;
 }
 function showGaps(gaps){const host=$('project-gaps');host.replaceChildren();if(!Array.isArray(gaps)||!gaps.length){host.hidden=true;return}host.hidden=false;host.append(node('summary',`上次保存 / 提交检查：${gaps.length} 项素材或审阅提示`));const list=node('ul');for(const gap of gaps)list.append(node('li',typeof gap==='string'?gap:`${gap.scene_id?gap.scene_id+' · ':''}${gap.message}`));host.append(list);host.open=gaps.some(gap=>gap.severity==='error')}
 function showDownloads(rows){const host=$('project-downloads');host.replaceChildren();for(const row of Array.isArray(rows)?rows:[])if(row.url)host.append(download(row.url,row.label||row.name||'下载文件'))}
 function gapText(gaps){if(!gaps)return'';const values=Array.isArray(gaps)?gaps:Object.values(gaps).flat();return values.length?'；仍有 '+values.length+' 项素材或审阅缺口。':''}
 async function submit(operation){
  if(actionBusy||navigationError||(operation==='draft'&&pendingDraft))return;actionBusy=true;busyControls();
  try{
   if(operation==='save'){await saveProject();await poll();return}
   let data;
   if(operation==='draft'){
    store();if(!flow.validate($('research')))throw Error('请修正已定位的选题字段。');
    if(!spec.topic.trim())invalidField('请填写具体选题。',$('topic'));
    if(!spec.sources.some(source=>(source.content||'').trim().length>=100)){flow.show('research');const source=$('sources').querySelector('textarea');if(source)flow.reveal(source);else flow.reveal($('add-source'));throw Error('请添加至少一条含 100 字正文的来源。')}
    data={backend:spec.backend,topic:spec.topic,hot_relevance:spec.hot_relevance,narrative_mode:spec.narrative_mode,mode:spec.mode,target_minutes:spec.target_minutes,sources:spec.sources};
   }else data=payload();
   const signature=fingerprint(),result=await api('/api/investigation/'+operation,data);selectedResult=result.job_id;submittedSnapshots[result.job_id]={signature,operation};
   if(operation==='draft'){pendingDraft=result.job_id;pendingFingerprint=signature;readyDraft=null;allowPendingDraft=true;renderDraftReady()}else{jobId=result.job_id;flow.show('delivery')}
   store();projectContext();status('任务已提交：'+result.job_id+'。继续编辑不会改变已提交任务。');await poll();
  }catch(error){if(error.payload?.job_id){jobId=error.payload.job_id;selectedResult=jobId;store();projectContext()}if(error.payload?.gaps){showGaps(error.payload.gaps);flow.show('delivery')}status(error.message,true)}
  finally{actionBusy=false;busyControls()}
 }
 function download(url,label){const a=node('a',label);a.href=url;a.download='';return a}
 function durationLabel(seconds){const total=Math.max(0,Math.round(seconds));return `${Math.floor(total/60)} 分 ${String(total%60).padStart(2,'0')} 秒`}
 function taskCard(id,state){
  const card=node('article',undefined,'job'),head=node('div',undefined,'header-row');card.dataset.jobId=id;head.append(node('h3',state.title||id),node('span',({queued:'已排队',running:'运行中',done:'已完成',error:'失败',saved:'已保存'})[state.status]||state.status,'tag'));card.append(head,node('p',`${id} · ${state.operation||'项目'}`,'small'),node('p',state.phase||state.status));
  if(Number.isFinite(state.duration_seconds)){const estimated=state.estimated_duration===true||(!state.video&&state.operation==='preview');let detail=`${estimated?'预估时长':'实际时长'}：${durationLabel(state.duration_seconds)}`;if(estimated)detail+=' · 静帧预览按稿件估算，成片以配音实测为准';else{if(state.duration_note)detail+=' · '+state.duration_note;else if(typeof state.target_reached==='boolean')detail+=state.target_reached?' · 达到目标时长':' · 未达到目标时长，需要补充实质内容';if(state.target_difference_seconds<0)detail+=` · 距目标还差 ${durationLabel(-state.target_difference_seconds)}`}card.append(node('p',detail,'notice'))}
  if(['queued','running'].includes(state.status)){const progress=node('progress');if(typeof state.progress==='number'){progress.max=state.progress>1?100:1;progress.value=state.progress}progress.setAttribute('aria-label',state.phase||'任务进行中');card.append(progress)}if(state.error)card.append(node('p',state.error,'error'));
  const toolbar=node('div',undefined,'toolbar');if(state.operation!=='draft'||state.status==='done')toolbar.append(button('载入此项目',async()=>{try{await loadProject(id)}catch(error){status(error.message,true)}},'secondary'));
  if(state.status==='error')toolbar.append(button('恢复上次任务',async()=>{try{const result=await api('/api/investigation/resume',{job_id:id});selectedResult=result.job_id;delete submittedSnapshots[result.job_id];status('已请求恢复：'+result.job_id+'。恢复使用原提交稿件，不包含当前新修改。');store();poll()}catch(error){status(error.message,true)}},'secondary'));card.append(toolbar);
  if(state.video){const video=node('video');video.src=state.video;video.controls=true;video.preload='metadata';card.append(video)}
  if(state.previews?.length){const details=node('details'),grid=node('div',undefined,'preview-grid');details.open=!state.video;details.append(node('summary',`静帧预览 · ${state.previews.length} 张`));for(const url of state.previews){const a=node('a'),img=node('img');a.href=url;a.target='_blank';a.rel='noopener';img.src=url;img.alt='调查长片分镜预览';img.loading='lazy';a.append(img);grid.append(a)}details.append(grid);card.append(details)}
  const links=node('div',undefined,'downloads'),seen=new Set();const add=(url,label)=>{if(typeof url==='string'&&!seen.has(url)){links.append(download(url,label));seen.add(url)}};add(state.video,'下载视频');add(state.subtitle,'下载字幕');add(state.storyboard_url,'源分镜 JSON');add(state.manuscript,'口播稿');add(state.source_ledger,'来源台账');add(state.publish_copy,'发布稿');add(state.bundle,'完整交付包');add(state.verification,'成片检查记录');add(state.manifest_url,'素材与检查清单');(state.covers||[]).forEach((url,index)=>add(url,`封面 ${index+1}`));for(const row of Array.isArray(state.downloads)?state.downloads:[]){add(row.url,row.label||row.name||'下载文件')}if(state.downloads&&!Array.isArray(state.downloads))for(const [label,url]of Object.entries(state.downloads))add(url,label);card.append(links);
  if(state.gaps){const details=node('details');details.append(node('summary','查看素材 / 审阅缺口'));const list=node('ul');for(const gap of Array.isArray(state.gaps)?state.gaps:Object.values(state.gaps).flat())list.append(node('li',typeof gap==='string'?gap:gap.message||JSON.stringify(gap)));details.append(list);card.append(details)}return card;
 }
 function drawResult(){
  const state=latestJobs[selectedResult],host=$('jobs');resultOrigin();
  if(!state){for(const media of host.querySelectorAll('video,audio'))media.pause();host.replaceChildren(node('p',selectedResult?'此任务暂未出现在列表中，请刷新或前往作品库。':'暂无调查任务。先审阅稿件，再保存或制作。','empty'));return}
  const signature=JSON.stringify(state),old=jobNodes.get(selectedResult);
  if(old?.signature===signature){if(old.node.parentElement!==host){for(const media of host.querySelectorAll('video,audio'))media.pause();host.replaceChildren(old.node)}return}
  const focused=old?.node.contains(document.activeElement)?document.activeElement:null;
  const card=taskCard(selectedResult,state),previousVideo=old?.node.querySelector('video'),nextVideo=card.querySelector('video');
  if(previousVideo&&nextVideo&&previousVideo.getAttribute('src')===nextVideo.getAttribute('src'))nextVideo.replaceWith(previousVideo);
  else if(previousVideo&&!previousVideo.paused&&!previousVideo.ended){$('result-origin').textContent='任务已更新；仍保留正在播放的上一版视频。暂停后显示新任务状态。';$('result-origin').dataset.changed='true';return;}
  old?.node.querySelectorAll('details').forEach((details,index)=>{const replacement=card.querySelectorAll('details')[index];if(replacement)replacement.open=details.open});
  if(focused?.matches('button,a')){const replacement=[...card.querySelectorAll(focused.tagName.toLowerCase())].find(control=>control.textContent===focused.textContent&&control.getAttribute('href')===focused.getAttribute('href'));if(replacement)replacement.replaceWith(focused)}
  for(const media of host.querySelectorAll('video,audio'))media.pause();
  host.replaceChildren(card);if(focused){if(card.contains(focused))focused.focus({preventScroll:true});else $('result-selector').focus({preventScroll:true})}jobNodes.set(selectedResult,{signature,node:card});
 }
 async function poll(){
  if(polling)return;polling=true;
  try{
   const data=await api('/api/jobs'),rows=Object.entries(data).filter(([,state])=>state.kind==='investigation').sort((a,b)=>(b[1].created||0)-(a[1].created||0));latestJobs=Object.fromEntries(rows);
   if(!selectedResult)selectedResult=jobId&&latestJobs[jobId]?jobId:pendingDraft&&latestJobs[pendingDraft]?pendingDraft:rows[0]?.[0]||'';
   const recent=rows.slice(0,20);if(selectedResult&&!recent.some(([id])=>id===selectedResult)&&latestJobs[selectedResult])recent.unshift([selectedResult,latestJobs[selectedResult]]);
   const selector=$('result-selector'),options=recent.map(([id,state])=>[id,(state.title||id)+' · '+({queued:'已排队',running:'运行中',done:state.operation==='save'?'已保存':'已完成',error:'失败'}[state.status]||state.status)]);
   const optionSignature=JSON.stringify(options);if(selector.dataset.signature!==optionSignature){selector.replaceChildren(...(options.length?options:[['','暂无任务']]).map(([id,label])=>new Option(label,id)));selector.dataset.signature=optionSignature}selector.value=selectedResult;
   for(const [id,submitted]of Object.entries(submittedSnapshots)){const state=latestJobs[id];if(state&&submitted.created===undefined&&state.operation===submitted.operation){submitted.created=state.created;store()}}
   drawResult();
   const pending=latestJobs[pendingDraft];
   if(allowPendingDraft&&pending?.status==='done'){readyDraft={id:pendingDraft};pendingDraft=null;pendingFingerprint=null;renderDraftReady();busyControls();store();status('分章草稿已完成，请点击「载入待审阅草稿」。当前输入已保留。')}
   else if(allowPendingDraft&&pending?.status==='error'){selectedResult=pendingDraft;pendingDraft=null;pendingFingerprint=null;busyControls();store();status(pending.error||'草稿任务失败，可在制作交付中恢复原任务。',true);drawResult()}
  }catch(error){status('读取任务失败：'+error.message+'。当前输入与已有结果保持不变。',true)}
  finally{polling=false}
 }
 async function loadTopics(){const control=$('topics-load');control.disabled=true;try{status('正在读取公开热榜…');const data=await api('/api/investigation/topics');$('topics').replaceChildren(node('p',`${data.source||'公开热榜'} · 抓取时间 ${data.fetched_at||'未提供'}；热榜只用于选题，不代表报道内容已核实。`,'small'));for(const item of data.items||[]){const row=node('div',undefined,'toolbar');row.append(node('span',item.title),button('带入选题',()=>{$('topic').value=item.title;$('hot-relevance').value=`${data.source||'公开热榜'}，抓取时间 ${data.fetched_at||'未提供'}。原链接：${item.url||''}；事实待核对。`;store();status('已带入选题，请收集原始来源后写稿。')},'secondary'));$('topics').append(row)}status('热榜已读取。请选择有事实入口和素材支持的选题。')}catch(error){status('热榜读取失败：'+error.message,true)}finally{control.disabled=false}}
 function setup(){
  const gaps=node('details',undefined,'notice');gaps.id='project-gaps';gaps.hidden=true;$('coverage').after(gaps);const projectDownloads=node('div',undefined,'downloads');projectDownloads.id='project-downloads';$('project-download-host').append(projectDownloads);
  const demo=node('div',undefined,'notice');demo.id='demo-info';demo.hidden=true;demo.append(node('span','当前为短篇功能演示，不作为目标长片验收。 '),button('转为正式项目',()=>{spec.demo_mode=false;$('target-minutes').value='10';store();$('demo-info').hidden=true;status('已转为正式项目：目标 10 分钟，请补足稿件与真实素材。')},'secondary'));$('coverage').before(demo);
  for(const [id,[label]]of Object.entries(modes))$('narrative-mode').append(new Option(label,id));
  const mode=select([['investigation','调查长片 · 真实视频承担叙事'],['explainer','机制讲解 · 可使用图解为主']],'investigation',value=>{spec.mode=value});mode.id='production-mode';$('narrative-mode').parentElement.after(field('内容方式',mode));
  const topics=node('div');topics.id='topics';const topicsButton=button('读取公开热榜',loadTopics,'secondary');topicsButton.id='topics-load';$('topics-tools').append(topicsButton,topics);
  const importPanel=node('div',undefined,'card');importPanel.id='media-import-panel';importPanel.hidden=true;const grid=node('div',undefined,'grid');const path=input('',null,()=>{});path.id='media-path';path.placeholder='例如 D:\\素材\\事件原片.mp4';const kind=select([...Object.entries(kinds).filter(([id])=>id!=='diagram'),['audio','音频素材']],'video',()=>{});kind.id='media-kind';const source=select(knownSourceOptions(),'',()=>{});source.id='media-source';const description=input('',300,()=>{});description.id='media-description';grid.append(field('本机文件完整路径',path),field('素材类型',kind),field('来源关联',source),field('素材内容说明',description));const importButton=button('校验并导入素材',importMedia,'secondary');importButton.id='media-import';importPanel.append(grid,importButton);$('assets').before(importPanel);
  const picker=node('div',undefined,'card');picker.id='library-picker';picker.hidden=true;const pending=node('div',undefined,'notice');pending.id='library-pending';pending.hidden=true;$('assets').before(pending,picker);$('add-asset').after(button('从资源库选择',openResourcePicker,'secondary'));
  $('add-asset').onclick=()=>{$('media-source').replaceChildren(...knownSourceOptions().map(([id,label])=>new Option(label,id)));importPanel.hidden=false;$('media-path').focus()};
  for(const id of ['topic','hot-relevance','target-minutes','project-title'])$(id).addEventListener('input',store);$('narrative-mode').onchange=()=>{$('narrative-help').textContent=modes[$('narrative-mode').value][1];store()};$('story-backend').onchange=store;$('speech-source').onchange=()=>{store();renderChapters();systemVoiceNotice()};$('voice-preset').onchange=store;$('voice-preview').onclick=previewVoice;
  $('add-source').onclick=()=>{if(spec.sources.length>=24)return;spec.sources.push({id:uid('src',spec.sources),title:'',url:'',published_at:'',content:'',status:'unreviewed'});renderSources();renderChapters();store()};
  $('add-chapter').onclick=()=>{if(spec.chapters.length>=12)return;const chapter={id:uid('ch',spec.chapters),title:'新章节',summary:''};spec.chapters.push(chapter);selectedChapter=chapter.id;selectedScene='';renderChapters();coverage();store()};
  CharacterPicker.mount($('character-library-picker'),actor=>{if(actionBusy)throw Error('请等待当前操作结束');if(!actor.voice_id)throw Error('请先在角色库为此角色绑定音色');if(cast.some(r=>r.name===actor.name))throw Error('本片已有同名角色，请保留当前版本或先移除后带入');if(cast.length>=16)throw Error('本片最多 16 个说话角色');backupDraft('带入角色 '+actor.name);spec.character_links||={};spec.character_links[actor.name]={id:actor.id,revision:actor.revision};cast.push({name:actor.name,preset:actor.voice_id});spec.backends={tts:'local',asr:'local'};renderAll();store();status('已带入角色与音色版本。外貌参考保留在工程，长片画面仍使用本片登记的素材。')},status,fingerprint);
  $('add-character').onclick=()=>{if(cast.length>=16)return;let index=cast.length+1;while(cast.some(role=>role.name===`角色${index}`))index++;cast.push({name:`角色${index}`,preset:$('voice-preset').value||library.default_preset_id||library.presets[0]?.id||''});renderCast();renderChapters();store()};
  for(const operation of ['draft','save','preview','render'])$(operation).onclick=()=>submit(operation);$('refresh').onclick=poll;
  $('manual-edit').onclick=()=>flow.show('production',{focus:true});$('review-next').onclick=()=>flow.show('delivery',{focus:true});
  $('result-selector').onchange=()=>{for(const media of $('jobs').querySelectorAll('video,audio'))media.pause();selectedResult=$('result-selector').value;drawResult();store()};
  $('example').onclick=async()=>{if(actionBusy)return;const before=fingerprint();try{const data=await api('/api/investigation/example');checkProject(data);if(before!==fingerprint())throw Error('载入示例期间草稿有修改，已保留当前内容。请再次载入。');backupDraft('载入功能示例');pendingDraft=null;readyDraft=null;applyProject(data);renderDraftReady();busyControls();$('project-more').open=false;flow.show('production');status('已载入短篇功能示例，用于体验流程；不是 10 分钟调查成片。')}catch(error){status(error.message,true)}};

  $('export').onclick=()=>{try{store();const blob=new Blob([JSON.stringify(spec,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=download(url,'');link.download='investigation-storyboard.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){status(error.message,true)}};
  $('import').onchange=async()=>{const before=fingerprint();try{const file=$('import').files[0];if(!file)return;if(file.size>500000)throw Error('项目 JSON 应小于 500 KB。');const data=JSON.parse(await file.text());checkProject(data);if(before!==fingerprint())throw Error('读取文件期间草稿有修改，已保留当前输入，请再次导入。');backupDraft('导入项目 JSON');pendingDraft=null;readyDraft=null;applyProject(data);renderDraftReady();busyControls();$('project-more').open=false;flow.show('production');status('JSON 已载入为新的编辑项目；素材需要重新登记。')}catch(error){status(error.message,true)}finally{$('import').value=''}};

 }
 async function init(){
  setup();flow=WorkflowStages({onchange:()=>store()});const params=new URLSearchParams(location.search);allowPendingDraft=!params.has('project')&&!params.has('resource');
  try{const saved=JSON.parse(StudioStorage.local.getItem(storageKey)||StudioStorage.local.getItem(legacyKey)||'null');if(saved?.storyboard){pendingDraft=saved.pendingDraft||null;pendingFingerprint=saved.pendingFingerprint||null;readyDraft=saved.readyDraft||null;submittedSnapshots=saved.submittedSnapshots||{};selectedChapter=saved.selectedChapter||'';selectedScene=saved.selectedScene||'';selectedResult=saved.selectedResult||'';applyProject({...saved,job_id:saved.jobId});flow.show(saved.stage||'research')}else renderAll()}
  catch{renderAll();status('上次草稿无法读取，可以导入项目 JSON 或载入示例。',true)}
  renderDraftReady();busyControls();try{const backups=JSON.parse(StudioStorage.local.getItem(storageKey+'-backups')||StudioStorage.local.getItem(legacyKey+'-backups')||'[]');if(Array.isArray(backups)&&backups.length)offerBackup(backups.at(-1))}catch{}
  api('/api/voice-library').then(value=>{library=value;const chosen=spec.voice_preset_id||'';$('voice-preset').replaceChildren(...presetOptions('跟随工作台默认音色').map(([id,label])=>new Option(label,id)));if(chosen&&!library.presets.some(row=>row.id===chosen))$('voice-preset').append(new Option(chosen+' · 未找到',chosen));$('voice-preset').value=chosen;if(!document.activeElement?.closest('#chapters,#characters')){renderCast();renderChapters()}}).catch(error=>status('音色库读取失败：'+error.message+'。稿件仍可编辑。',true));
  api('/api/investigation/health').then(health=>{$('environment').textContent=(health.ready?'制作环境已就绪。':'制作环境仍需配置。')+' '+(health.message||(health.checks||[]).filter(check=>!check.ready).map(check=>check.name+'：'+check.message).join('；'))}).catch(error=>{$('environment').textContent='无法读取制作环境：'+error.message});
  if(params.has('project')){
   try{
    const requested=params.get('project');if(!/^investigation-[a-f0-9]{10}$/.test(requested))throw Error('调查项目编号无效。');
    if(jobId===requested)status('已恢复此工程的浏览器草稿。需要重新载入已保存快照时，可在制作交付中选择「载入此项目」。');
    else await loadProject(requested);
    const url=new URL(location.href);url.searchParams.delete('project');history.replaceState(null,'',url.pathname+url.search+url.hash);allowPendingDraft=!params.has('resource');
   }catch(error){failNavigation('无法载入指定工程：'+error.message)}
  }
  if(params.has('resource'))await chooseResource(params.get('resource'));
  await poll();setInterval(()=>{if(!document.hidden)poll()},3000);window.addEventListener('pageshow',()=>poll());window.addEventListener('pagehide',store);document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll()});
 }
 init();
})();
