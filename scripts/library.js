(() => {
  'use strict';
  const friend = document.documentElement.dataset.studioEdition === 'friend';
  const $ = id => document.getElementById(id), gallery = location.pathname === '/gallery', audioLibrary = location.pathname === '/audio-library';
  const assetView = gallery || audioLibrary, params = new URLSearchParams(location.search);
  const names = {image:'图片',video:'视频',audio:'音频',document:'文档',speech:'配音',motion:'动态镜头',whiteboard:'白板视频',investigation:'热点长片',enhance:'增强视频',asr:'字幕',story:'小说分镜',music:'配乐',sfx:'音效',generation:'生成工坊','image-reference':'参考图片'};
  const statuses = {done:'已完成',draft:'草稿',preview:'样片 / 预览',queued:'排队中',running:'制作中',error:'失败'};
  let status = 'done', rows = [], requestNumber = 0, detailRequest = 0, appliedFilters = null;
  const cardNodes = new Map();
  const element = (tag, text, className) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if(className)e.className=className; return e; };
  function localUrl(url) { if(typeof url!=='string'||!url.trim())return '';try { const u = new URL(url, location.origin); if(friend && !/^\/(outputs|api|speech|whiteboard|generation)(\/|\?|$)/.test(u.pathname+u.search))return ''; return u.origin === location.origin && /^\/(outputs|api|image|motion|speech|music|whiteboard|investigation|novel|production|subtitles|enhance|generation)(\/|\?|$)/.test(u.pathname+u.search) ? u.pathname+u.search : ''; } catch { return ''; } }
  async function api(path, body) { const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const result = await response.json(); if(!response.ok)throw new Error(result.error || '读取失败，请稍后刷新'); return result; }
  const dateText = value => { if(!value)return '时间未记录';const date = new Date(typeof value === 'number' ? value * 1000 : value); return Number.isNaN(date.valueOf()) ? '时间未记录' : date.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); };
  const typeText = row => names[row.workflow] || names[row.kind] || names[row.media_type] || '工程';
  function continuationLabel(url) { const parsed=new URL(url,location.origin);return ['project','draft','plan','id'].some(key=>parsed.searchParams.get(key))?'继续编辑工程':'打开创作工具'; }
  function previewKind(row, url) { return /\.(png|jpe?g|webp|gif|avif|svg)$/i.test(new URL(url,location.origin).pathname)?'image':row.media_type; }
  function selectedFilters() { return {status,kind:$('library-kind').value,q:$('library-search').value.trim(),favorite:$('library-favorite').checked}; }
  function filterDescription(filters) { if(!filters)return '';return [assetView?'可复用素材':filters.status==='all'?'全部工程':statuses[filters.status]||filters.status,filters.kind==='all'?'全部类型':names[filters.kind]||filters.kind,filters.q?'搜索“'+filters.q+'”':'',filters.favorite?'仅收藏':''].filter(Boolean).join(' · '); }
  function resetFilters() { status=assetView?'done':'all';$('library-kind').value='all';$('library-search').value='';$('library-favorite').checked=false;document.querySelectorAll('[data-status]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.status===status)));refresh(); }
  function action(label, url) { const a = element('a',label,'hub-button secondary'); a.href=url; return a; }
  function jianyingPanel(row) {
    const panel=element('section',null,'jianying-panel'), heading=element('h3','送到剪映精修'), state=element('p','正在检查剪映与草稿组件…','detail-meta');
    panel.setAttribute('aria-label','剪映精修');state.setAttribute('role','status');
    panel.append(heading,element('p','生成草稿 → 在剪映中调整画面、声音与字幕 → 导出 MP4','jianying-steps'),state);
    const controls=element('div',null,'jianying-controls'),label=element('label','交接方式'),mode=element('select');
    for(const [value,text] of [['auto','自动选择'],['scenes','素材分轨'],['flattened','成片交接']])mode.append(new Option(text,value));
    label.append(mode);const generate=element('button','生成剪映草稿','hub-button primary'),open=element('button','打开剪映','hub-button secondary'),reload=element('button','刷新状态','hub-button secondary');
    for(const button of [generate,open,reload])button.type='button';generate.disabled=true;open.disabled=true;
    controls.append(label,generate,open,reload);panel.append(controls);
    const help=element('p',null,'detail-meta'),availability=element('p',null,'jianying-unavailable'),result=element('div',null,'jianying-result'),notice=element('p',null,'detail-meta');notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');
    availability.id='jianying-availability';availability.setAttribute('role','status');generate.setAttribute('aria-describedby',availability.id);
    panel.append(help,availability,result,notice,element('p','草稿已生成或剪映已打开，都不代表 MP4 已导出。完成精修后，请在剪映内导出到下方交付目录，再点“刷新状态”回收成片。','jianying-boundary'));
    const modeNames={scenes:'素材分轨',flattened:'成片交接',auto:'自动选择'};let installation=null,busy=false,latest=null;
    function explainMode(){help.textContent=({auto:'优先使用可编辑的镜头与独立声音；素材不足时交接已生成的成片。',scenes:'按现有镜头素材建立轨道，可分别调整画面、旁白与字幕。',flattened:'把已生成的成片放入剪映，原片内已混合的画面、声音或烧录字幕无法拆开。'})[mode.value];}
    function updateButtons(){
      let reason='';const project=installation?.project,reasons=project?.mode_reasons||{};
      if(!installation)reason=busy?'正在检查工程是否可交接…':'尚未获得工程状态，请刷新后再生成草稿。';
      else if(!installation.installed)reason='尚未检测到剪映。可让 Codex 询问并协助安装官方桌面版与桥接，完成后刷新状态。';
      else if(!installation.bridge_ready)reason='草稿组件未就绪，请先按工作台安装说明准备组件。';
      else if(!installation.editable_available)reason='尚未找到剪映草稿目录，请先打开剪映完成首次设置，再刷新状态。';
      else if(!project?.can_export)reason='当前工程还没有可交接的镜头素材或成片。'+[...new Set(Object.values(reasons).flat().filter(v=>typeof v==='string'))].join('；');
      else if(mode.value!=='auto'&&Array.isArray(project.available_modes)&&!project.available_modes.includes(mode.value))reason='当前工程暂不支持“'+modeNames[mode.value]+'”。'+(Array.isArray(reasons[mode.value])?reasons[mode.value].join('；'):'请尝试自动选择。');
      generate.disabled=busy||!!reason;generate.title=reason;availability.textContent=reason;availability.hidden=!reason;
      open.disabled=busy||!installation?.installed;reload.disabled=busy;mode.disabled=busy;
    }
    function pathField(labelText,value){if(!value)return;const group=element('label',labelText,'jianying-path'),field=element('input');field.value=value;field.readOnly=true;field.onclick=()=>field.select();group.append(field);result.append(group);}
    function showExport(value){
      latest=value||null;for(const video of result.querySelectorAll('video')){video.pause();video.removeAttribute('src');video.load();}result.replaceChildren();if(!latest)return;
      result.append(element('h4','已生成：'+(latest.draft_name||'剪映草稿')));
      result.append(element('p','交接方式：'+(modeNames[latest.mode]||latest.mode||'草稿'),'detail-meta'));
      if(latest.draft_name)result.append(element('p','打开剪映后，在首页选择“'+latest.draft_name+'”草稿继续编辑。','detail-meta'));
      pathField('剪映草稿位置',latest.draft_path);pathField('MP4 交付目录',latest.delivery_dir||latest.export_dir);
      const files=element('div',null,'detail-deliverables'),videos=element('div',null,'jianying-videos'),seen=new Set();
      for(const file of [{label:'交接清单',url:latest.manifest_url},...(Array.isArray(latest.files)?latest.files:[])]){
        const url=localUrl(file.url);if(!url||seen.has(url))continue;seen.add(url);
        if(file.kind==='video'){
          const item=element('section',null,'jianying-video'),title=element('h5',file.label||'剪映导出视频'),video=element('video');video.src=url;video.controls=true;video.preload='metadata';video.setAttribute('aria-label',file.label||'剪映导出视频预览');
          const metadata=[];if(Number.isFinite(file.duration)&&file.duration>0)metadata.push(file.duration.toFixed(1)+' 秒');if(Number.isFinite(file.bytes)&&file.bytes>0)metadata.push((file.bytes/1024/1024).toFixed(1)+' MB');
          if(file.verification?.visual_review==='pending'||file.verification?.audio_review==='pending')metadata.push('画面与声音待检查');
          const links=element('div',null,'hub-actions'),watch=action('打开成片',url),download=action('下载 MP4',url);watch.target='_blank';watch.rel='noopener noreferrer';download.download='';links.append(watch,download);
          item.append(title,video,element('p',metadata.join(' · '),'detail-meta'),links);videos.append(item);
        }else{const link=element('a',file.label||'草稿附件');link.href=url;link.download='';files.append(link);}
      }
      result.append(files);
      if(videos.childElementCount)result.append(element('h4','剪映导出成片'),videos);
      if(Array.isArray(latest.pending_files)&&latest.pending_files.length){
        const pending=element('div',null,'jianying-pending');pending.setAttribute('role','status');pending.append(element('p','以下文件仍在导出或尚不可播放。请等待剪映完成导出，再点“刷新状态”。'));
        const list=element('ul');for(const file of latest.pending_files){const item=element('li',typeof file.name==='string'?file.name:'正在写入的视频');if(typeof file.reason==='string'&&file.reason)item.append(element('span',' · '+file.reason));list.append(item);}pending.append(list);result.append(pending);
      }
      if(Array.isArray(latest.warnings)&&latest.warnings.length){const list=element('ul',null,'jianying-warnings');for(const warning of latest.warnings)list.append(element('li',String(warning)));result.append(list);}
    }
    async function load(){
      busy=true;updateButtons();state.textContent='正在检查剪映与草稿组件…';
      try{const data=await api('/api/jianying/status?'+new URLSearchParams({project_id:row.project_id}));if(!panel.isConnected)return;installation=data;
        const ready=!!data.bridge_ready;state.textContent=(data.installed?'已检测到剪映':'尚未检测到剪映')+' · '+(ready?'草稿组件已就绪':'草稿组件未就绪');
        if(!data.installed){const link=element('a','下载剪映官方桌面版');link.href='https://www.capcut.cn/';link.target='_blank';link.rel='noopener noreferrer';state.append(' · ',link);}
        if(!ready)state.append('。可对 Codex 说“安装剪映并配置桥接”；缺少客户端时会先征求你的同意。');
        showExport(data.last_export||data.project?.last_export);
      }catch(error){if(panel.isConnected){state.textContent=error.message;installation=null;}}finally{busy=false;updateButtons();}
    }
    generate.onclick=async()=>{busy=true;updateButtons();notice.classList.remove('library-error');notice.textContent='正在整理素材并生成剪映草稿，请稍候…';try{const data=await api('/api/jianying/export',{project_id:row.project_id,mode:mode.value});if(!panel.isConnected)return;showExport(data);notice.textContent='草稿已生成。打开剪映后选择上方草稿继续精修。';}catch(error){notice.textContent=error.message;notice.classList.add('library-error');}finally{busy=false;updateButtons();}};
    open.onclick=async()=>{busy=true;updateButtons();notice.classList.remove('library-error');notice.textContent='正在打开剪映…';try{const data=await api('/api/jianying/open',{project_id:row.project_id});if(!panel.isConnected)return;notice.textContent=data.message||'已启动剪映，请在首页选择生成的草稿。';}catch(error){notice.textContent=error.message;notice.classList.add('library-error');}finally{busy=false;updateButtons();}};
    reload.onclick=load;mode.onchange=()=>{explainMode();updateButtons();};explainMode();queueMicrotask(load);return panel;
  }
  function updateUrl(item) { const q = new URLSearchParams(location.search); item ? q.set('item',item) : q.delete('item'); history.replaceState(null,'',location.pathname+(q.size?'?'+q:'')); }
  async function favorite(row,button) { button.disabled=true; try { const data=await api('/api/library/metadata',{id:row.id,favorite:!row.favorite}); Object.assign(row,data.item); button.textContent=row.favorite?'★ 已收藏':'☆ 收藏';button.setAttribute('aria-pressed',String(row.favorite));button.setAttribute('aria-label',(row.favorite?'取消收藏 ':'收藏 ')+row.title); if($('library-favorite').checked)await refresh(); } catch(e){$('library-status').textContent='收藏未保存：'+e.message;$('library-status').classList.add('library-error');} finally {button.disabled=false;} }
  function card(row) {
    const box=element('article',null,'library-card'), preview=element('button',null,'library-preview');box.dataset.libraryId=row.id; preview.type='button';preview.dataset.cardAction='preview';preview.setAttribute('aria-label','查看 '+row.title);
    const thumb=localUrl(row.thumbnail_url || (row.media_type==='image'?row.preview_url:''));
    const symbol=()=>element('span',({audio:'♫',video:'▶',document:'▤'})[row.media_type]||'◇','media-symbol');
    if(thumb){const img=element('img');img.src=thumb;img.alt='';img.loading='lazy';img.onerror=()=>{img.replaceWith(symbol());};preview.append(img);}else preview.append(symbol());
    const mediaLabel=[names[row.media_type]||'工程',Number(row.duration_seconds)>0?Number(row.duration_seconds).toFixed(1)+' 秒':''].filter(Boolean).join(' · ');preview.append(element('span',mediaLabel,'library-media-label'));
    if(thumb&&row.media_type==='video'){const play=element('span','▶','library-play');play.setAttribute('aria-hidden','true');preview.append(play);}
    preview.onclick=()=>openDetail(row.id); const body=element('div',null,'library-card-body'), title=element('button',row.title,'library-card-title');title.type='button';title.dataset.cardAction='title';title.onclick=preview.onclick;
    body.append(title,element('p',typeText(row)+' · '+dateText(row.created_at)));
    if(row.tags?.length){const tags=element('p',null,'library-tags');for(const tag of row.tags.slice(0,3))tags.append(element('span',tag));if(row.tags.length>3)tags.append(element('span','+'+(row.tags.length-3)));body.append(tags);}
    const bottom=element('div',null,'card-bottom'), fav=element('button',row.favorite?'★ 已收藏':'☆ 收藏','favorite-button');fav.type='button';fav.dataset.cardAction='favorite';fav.setAttribute('aria-pressed',String(!!row.favorite));fav.setAttribute('aria-label',(row.favorite?'取消收藏 ':'收藏 ')+row.title);fav.onclick=()=>favorite(row,fav);
    bottom.append(element('span',statuses[row.status]||row.status,'library-badge '+row.status),fav);body.append(bottom);box.append(preview,body);return box;
  }
  function renderCards(items) {
    const grid=$('library-grid'),focused=document.activeElement,focusedId=focused?.closest('[data-library-id]')?.dataset.libraryId,focusedAction=focused?.dataset.cardAction;
    const ids=new Set(items.map(row=>row.id));
    for(const [id,entry] of cardNodes)if(!ids.has(id)){entry.node.remove();cardNodes.delete(id);}
    items.forEach((row,index)=>{const signature=JSON.stringify(row);let entry=cardNodes.get(row.id);if(!entry||entry.signature!==signature){const next={node:card(row),signature};if(entry)entry.node.replaceWith(next.node);entry=next;cardNodes.set(row.id,entry);}if(grid.children[index]!==entry.node)grid.insertBefore(entry.node,grid.children[index]||null);});
    if(focusedId&&!focused.isConnected){const next=cardNodes.get(focusedId)?.node.querySelector('[data-card-action="'+focusedAction+'"]');(next||$('refresh-library')).focus({preventScroll:true});}
  }
  function updateEmpty(filters) {
    $('library-empty').hidden=!!rows.length;if(rows.length)return;
    const filtered=filters.q||filters.kind!=='all'||filters.favorite;
    $('library-empty-title').textContent=filtered?'没有匹配的内容':filters.status==='done'&&!assetView?'还没有已完成作品':assetView?'这里还没有素材':'这个范围内暂无工程';
    $('library-empty-description').textContent=filtered?'调整关键词、类型或收藏条件，已有作品不会因筛选被删除。':assetView?'生成或导入第一份素材后，就可以在这里预览与复用。':'可以查看其他状态的工程，或开始一次新的创作。';
    $('empty-create-link').textContent=$('create-link').textContent;$('empty-create-link').href=$('create-link').href;
  }
  async function refresh() {
    const n=++requestNumber,filters=selectedFilters(),q=new URLSearchParams({view:assetView?'assets':'products',status:filters.status,kind:filters.kind,q:filters.q});
    if(filters.favorite)q.set('favorite','1');$('library-status').textContent='正在读取所选范围…';$('library-status').classList.remove('library-error');$('retry-library').hidden=true;$('library-grid').setAttribute('aria-busy','true');
    $('library-result-scope').textContent=appliedFilters?'当前仍显示上次结果：'+filterDescription(appliedFilters):'';
    try { const data=await api('/api/library?'+q);if(n!==requestNumber)return; rows=data.items.filter(row=>!gallery||['image','video'].includes(row.media_type)).filter(row=>!audioLibrary||row.media_type==='audio');appliedFilters=filters;renderCards(rows);updateEmpty(filters);$('library-status').textContent=`${rows.length} 项${assetView?'素材':'作品与工程'}`;$('library-result-scope').textContent='当前结果：'+filterDescription(filters); }
    catch(e){if(n===requestNumber){$('library-status').textContent='本次筛选未完成：'+e.message;$('library-status').classList.add('library-error');$('retry-library').hidden=false;$('library-result-scope').textContent=appliedFilters?'筛选尚未生效，仍显示上次成功结果：'+filterDescription(appliedFilters):'尚未取得目录数据，请重试。';if(!appliedFilters)$('library-empty').hidden=true;}}
    finally{if(n===requestNumber)$('library-grid').setAttribute('aria-busy','false');}
  }
  async function openDetail(id) {
    const n=++detailRequest;
    try {const row=(await api('/api/library/item?id='+encodeURIComponent(id))).item;if(n!==detailRequest)return; const host=$('detail-content');host.replaceChildren();const title=element('h2',row.title);title.id='detail-title';
      const details=[typeText(row),statuses[row.status]||row.status,dateText(row.created_at)]; if(row.width&&row.height)details.push(`${row.width} × ${row.height}`);if(row.duration_seconds)details.push(`${Number(row.duration_seconds).toFixed(1)} 秒`);if(row.size_bytes)details.push((row.size_bytes/1024/1024).toFixed(1)+' MB');
      host.append(title,element('p',details.join(' · '),'detail-meta'));
      if(row.error)host.append(element('p',row.error,'library-error'));
      else if(row.phase)host.append(element('p',row.phase,'detail-meta'));
      const preview=localUrl(row.preview_url),player=element('div',null,'detail-player'),mediaKind=preview?previewKind(row,preview):row.media_type;if(preview&&['image','audio','video'].includes(mediaKind)){const media=element(mediaKind==='image'?'img':mediaKind);media.src=preview;if(mediaKind==='image')media.alt=row.title;else {media.controls=true;media.preload='metadata';media.setAttribute('aria-label',row.title);if(mediaKind==='video'){media.playsInline=true;const poster=localUrl(row.thumbnail_url);if(poster)media.poster=poster;}}player.append(media);}host.append(player);
      if(!player.childElementCount)host.append(element('p',row.status==='running'||row.status==='queued'?'任务完成后会显示可预览成果。当前可返回创作工具查看进度。':'当前没有可直接播放的媒体，可下载已有文件或继续编辑工程。','detail-no-preview'));
      const links=element('div',null,'hub-actions detail-main-actions'),download=localUrl(row.download_url);if(download){const a=action(mediaKind==='video'?'下载视频':mediaKind==='audio'?'下载音频':'下载文件',download);a.download='';links.append(a);}
      const source=localUrl(row.source_url);if(source){const resume=action(continuationLabel(source),source);if(['draft','preview','error'].includes(row.status))resume.className='hub-button primary';links.prepend(resume);}
      if(!friend&&row.status==='done'&&['image','video'].includes(row.media_type)){links.append(action('用于热点长片','/investigation?resource='+encodeURIComponent(row.id)));}
      if(!friend&&row.media_type==='audio'&&row.workflow==='music')links.append(action('用作长片背景音乐','/investigation?resource='+encodeURIComponent(row.id)));
      if(!friend&&row.media_type==='image'&&preview){
        const ref=element('button','作为生图参考','hub-button secondary');ref.onclick=async()=>{try{ref.disabled=true;let reference=row.reference_id;if(!reference&&/^[a-f0-9]{12}$/.test(row.project_id||'')){const saved=await api('/api/image-references',{job_id:row.project_id});reference=saved.reference?.id||saved.id;}
          if(!reference)throw new Error('这张图片尚未登记为参考图，请先下载后在图库导入。');location.href='/image?reference='+encodeURIComponent(reference);
        }catch(e){message.textContent=e.message;ref.disabled=false;}};
        if(row.reference_id||/^[a-f0-9]{12}$/.test(row.project_id||''))links.append(ref);
        if(row.absolute_path)links.append(action('制作动态镜头','/motion?'+new URLSearchParams({image:row.absolute_path,preview})));
      }
      host.append(links);const files=element('div',null,'detail-deliverables');for(const file of row.deliverables||[]){const url=localUrl(file.url);if(url&&url!==download){const a=element('a',file.label||'附件');a.href=url;a.download='';files.append(a);}}host.append(files);
      if(!assetView&&row.media_type==='video'&&row.project_id&&row.collections?.includes('products')&&!row.temporary)host.append(jianyingPanel(row));
      const edit=element('form',null,'detail-edit'),nameLabel=element('label','作品名称'),name=element('input'),tagLabel=element('label','标签（逗号分隔）'),tags=element('input');name.value=row.title;name.maxLength=200;name.required=true;tags.value=(row.tags||[]).join('，');nameLabel.append(name);tagLabel.append(tags);const save=element('button','保存名称与标签','hub-button secondary');save.type='submit';const message=element('p',null,'detail-meta');message.setAttribute('role','status');edit.append(nameLabel,tagLabel,save,message);
      edit.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{const updated=(await api('/api/library/metadata',{id:row.id,title:name.value.trim(),tags:tags.value.split(/[,，]/).map(v=>v.trim()).filter(Boolean)})).item;title.textContent=updated.title;message.textContent='已保存';await refresh();}catch(e){message.textContent=e.message;}finally{save.disabled=false;}};const editSection=element('details',null,'detail-edit-section');editSection.append(element('summary','编辑作品名称与标签'),edit);host.append(editSection);
      if(!$('library-detail').open)$('library-detail').showModal();updateUrl(id);
    }catch(e){if(n===detailRequest){$('library-status').textContent='详情读取失败：'+e.message;$('library-status').classList.add('library-error');}}
  }
  $('library-detail').addEventListener('close',()=>{++detailRequest;for(const m of $('detail-content').querySelectorAll('audio,video')){m.pause();m.removeAttribute('src');m.load();}$('detail-content').replaceChildren();updateUrl(null);});
  for(const button of document.querySelectorAll('[data-status]'))button.onclick=()=>{status=button.dataset.status;document.querySelectorAll('[data-status]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));refresh();};
  $('library-filters').onsubmit=e=>{e.preventDefault();refresh();};$('library-kind').onchange=refresh;$('library-favorite').onchange=refresh;$('refresh-library').onclick=refresh;
  $('clear-library-filters').onclick=resetFilters;$('empty-reset-filters').onclick=resetFilters;$('retry-library').onclick=refresh;
  const types=gallery?['image','video']:audioLibrary?(friend?['audio','speech']:['music','sfx','speech']):friend?['image','video','audio','document','generation','whiteboard','speech']:['image','video','audio','document','generation','whiteboard','investigation','motion','speech','music','sfx','story','asr','enhance'];for(const kind of types)$('library-kind').append(new Option(names[kind],kind));
  if(assetView){$('project-tabs').hidden=true;$('library-title').textContent=gallery?'图库与视频素材':'音乐与音频库';$('library-description').textContent=gallery?'集中查看已生成画面与导入的参考图，直接带入图像创作、动态镜头或长片。':'试听和整理配音、背景音乐与音效。背景音乐可以直接带入长片工作流。';$('create-link').textContent=gallery?'生成图片':'生成音乐或音效';$('create-link').href=gallery?'/image':'/music';document.title=$('library-title').textContent+' · AI STUDIO';}
  if(friend&&assetView){$('library-description').textContent=gallery?'集中查看画面与导入的参考图片，供后续白板和动画创作使用。':'试听和整理配音及已有音频素材。';$('create-link').textContent=gallery?'创作白板视频':'生成配音';$('create-link').href=gallery?'/whiteboard':'/speech';}
  if(gallery){$('gallery-upload').hidden=false;$('upload-image').onchange=async()=>{const file=$('upload-image').files[0];if(!file)return;const msg=$('upload-message');try{if(file.size>12*1024*1024)throw new Error('图片不能超过 12 MB');if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('请选择 PNG、JPG 或 WebP 图片');msg.textContent='正在导入参考图片…';const base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('无法读取图片'));reader.readAsDataURL(file);});await api('/api/image-references',{name:file.name,base64});msg.textContent='已导入图库，可作为参考图使用';await refresh();}catch(e){msg.textContent=e.message;}finally{$('upload-image').value='';}};}
  refresh();if(params.get('item'))openDetail(params.get('item'));
})();
