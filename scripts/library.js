(() => {
  'use strict';
  const $ = id => document.getElementById(id), gallery = location.pathname === '/gallery', audioLibrary = location.pathname === '/audio-library';
  const assetView = gallery || audioLibrary, params = new URLSearchParams(location.search);
  const names = {image:'图片',video:'视频',audio:'音频',document:'文档',speech:'配音',motion:'动态镜头',whiteboard:'白板视频',investigation:'热点长片',enhance:'增强视频',asr:'字幕',story:'小说分镜',music:'配乐',sfx:'音效','image-reference':'参考图片'};
  const statuses = {done:'已完成',draft:'草稿',preview:'预览',queued:'排队中',running:'制作中',error:'未完成'};
  let status = 'done', rows = [], requestNumber = 0, detailRequest = 0;
  const element = (tag, text, className) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if(className)e.className=className; return e; };
  function localUrl(url) { try { const u = new URL(url, location.origin); return u.origin === location.origin && /^\/(outputs|api|image|motion|speech|music|whiteboard|investigation|novel|production|subtitles|enhance)(\/|\?|$)/.test(u.pathname+u.search) ? u.pathname+u.search : ''; } catch { return ''; } }
  async function api(path, body) { const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const result = await response.json(); if(!response.ok)throw new Error(result.error || '读取失败，请稍后刷新'); return result; }
  const dateText = value => { if(!value)return '时间未记录';const date = new Date(typeof value === 'number' ? value * 1000 : value); return Number.isNaN(date.valueOf()) ? '时间未记录' : date.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); };
  const typeText = row => names[row.workflow] || names[row.kind] || names[row.media_type] || '工程';
  function action(label, url) { const a = element('a',label,'hub-button secondary'); a.href=url; return a; }
  function updateUrl(item) { const q = new URLSearchParams(location.search); item ? q.set('item',item) : q.delete('item'); history.replaceState(null,'',location.pathname+(q.size?'?'+q:'')); }
  async function favorite(row,button) { button.disabled=true; try { const data=await api('/api/library/metadata',{id:row.id,favorite:!row.favorite}); Object.assign(row,data.item); button.textContent=row.favorite?'★ 已收藏':'☆ 收藏';button.setAttribute('aria-pressed',String(row.favorite)); if($('library-favorite').checked)await refresh(); } catch(e){$('library-status').textContent=e.message;} finally {button.disabled=false;} }
  function card(row) {
    const box=element('article',null,'library-card'), preview=element('button',null,'library-preview'); preview.type='button';preview.setAttribute('aria-label','查看 '+row.title);
    const thumb=localUrl(row.thumbnail_url || (row.media_type==='image'?row.preview_url:''));
    if(thumb){const img=element('img');img.src=thumb;img.alt='';img.loading='lazy';preview.append(img);}else preview.append(element('span',({audio:'♫',video:'▶',document:'▤'})[row.media_type]||'◇','media-symbol'));
    preview.onclick=()=>openDetail(row.id); const body=element('div',null,'library-card-body'), title=element('button',row.title,'library-card-title');title.type='button';title.onclick=preview.onclick;
    body.append(title,element('p',typeText(row)+' · '+dateText(row.created_at)));
    if(row.tags?.length)body.append(element('p',row.tags.join(' · ')));
    const bottom=element('div',null,'card-bottom'), fav=element('button',row.favorite?'★ 已收藏':'☆ 收藏','favorite-button');fav.type='button';fav.setAttribute('aria-pressed',String(!!row.favorite));fav.onclick=()=>favorite(row,fav);
    bottom.append(element('span',statuses[row.status]||row.status,'library-badge '+row.status),fav);body.append(bottom);box.append(preview,body);return box;
  }
  async function refresh() {
    const n=++requestNumber, q=new URLSearchParams({view:assetView?'assets':'products',status,kind:$('library-kind').value,q:$('library-search').value.trim()});
    if($('library-favorite').checked)q.set('favorite','1');$('library-status').textContent='正在读取…';$('library-status').classList.remove('library-error');
    try { const data=await api('/api/library?'+q);if(n!==requestNumber)return; rows=data.items.filter(row=>!gallery||['image','video'].includes(row.media_type)).filter(row=>!audioLibrary||row.media_type==='audio');$('library-grid').replaceChildren(...rows.map(card));$('library-empty').hidden=!!rows.length;$('library-status').textContent=`共 ${rows.length} 项${assetView?'可复用素材':'作品与工程'}`; }
    catch(e){if(n===requestNumber){$('library-status').textContent=e.message;$('library-status').classList.add('library-error');}}
  }
  async function openDetail(id) {
    const n=++detailRequest;
    try {const row=(await api('/api/library/item?id='+encodeURIComponent(id))).item;if(n!==detailRequest)return; const host=$('detail-content');host.replaceChildren();const title=element('h2',row.title);title.id='detail-title';
      const details=[typeText(row),statuses[row.status]||row.status,dateText(row.created_at)]; if(row.width&&row.height)details.push(`${row.width} × ${row.height}`);if(row.duration_seconds)details.push(`${Number(row.duration_seconds).toFixed(1)} 秒`);if(row.size_bytes)details.push((row.size_bytes/1024/1024).toFixed(1)+' MB');
      host.append(title,element('p',details.join(' · '),'detail-meta'));
      if(row.error)host.append(element('p',row.error,'library-error'));
      else if(row.phase)host.append(element('p',row.phase,'detail-meta'));
      const preview=localUrl(row.preview_url),player=element('div',null,'detail-player'),mediaKind=row.status==='preview'&&row.thumbnail_url?'image':row.media_type;if(preview&&['image','audio','video'].includes(mediaKind)){const media=element(mediaKind==='image'?'img':mediaKind);media.src=preview;if(mediaKind==='image')media.alt=row.title;else {media.controls=true;media.preload='metadata';}player.append(media);}host.append(player);
      const links=element('div',null,'hub-actions'),download=localUrl(row.download_url);if(download){const a=action('下载文件',download);a.download='';links.append(a);}
      const source=localUrl(row.source_url);if(source)links.append(action(/[?&](project|draft)=/.test(source)?'继续编辑工程':'打开创作工具',source));
      if(row.status==='done'&&['image','video'].includes(row.media_type)){links.append(action('用于热点长片','/investigation?resource='+encodeURIComponent(row.id)));}
      if(row.media_type==='audio'&&row.workflow==='music')links.append(action('用作长片背景音乐','/investigation?resource='+encodeURIComponent(row.id)));
      if(row.media_type==='image'&&preview){
        const ref=element('button','作为生图参考','hub-button secondary');ref.onclick=async()=>{try{ref.disabled=true;let reference=row.reference_id;if(!reference&&/^[a-f0-9]{12}$/.test(row.project_id||'')){const saved=await api('/api/image-references',{job_id:row.project_id});reference=saved.reference?.id||saved.id;}
          if(!reference)throw new Error('这张图片尚未登记为参考图，请先下载后在图库导入。');location.href='/image?reference='+encodeURIComponent(reference);
        }catch(e){message.textContent=e.message;ref.disabled=false;}};
        if(row.reference_id||/^[a-f0-9]{12}$/.test(row.project_id||''))links.append(ref);
        if(row.absolute_path)links.append(action('制作动态镜头','/motion?'+new URLSearchParams({image:row.absolute_path,preview})));
      }
      host.append(links);const files=element('div',null,'detail-deliverables');for(const file of row.deliverables||[]){const url=localUrl(file.url);if(url&&url!==download){const a=element('a',file.label||'附件');a.href=url;a.download='';files.append(a);}}host.append(files);
      const edit=element('form',null,'detail-edit'),nameLabel=element('label','作品名称'),name=element('input'),tagLabel=element('label','标签（逗号分隔）'),tags=element('input');name.value=row.title;name.maxLength=200;name.required=true;tags.value=(row.tags||[]).join('，');nameLabel.append(name);tagLabel.append(tags);const save=element('button','保存名称与标签','hub-button secondary');save.type='submit';const message=element('p',null,'detail-meta');message.setAttribute('role','status');edit.append(nameLabel,tagLabel,save,message);
      edit.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{const updated=(await api('/api/library/metadata',{id:row.id,title:name.value.trim(),tags:tags.value.split(/[,，]/).map(v=>v.trim()).filter(Boolean)})).item;title.textContent=updated.title;message.textContent='已保存';await refresh();}catch(e){message.textContent=e.message;}finally{save.disabled=false;}};host.append(edit);
      if(!$('library-detail').open)$('library-detail').showModal();updateUrl(id);
    }catch(e){$('library-status').textContent=e.message;$('library-status').classList.add('library-error');}
  }
  $('library-detail').addEventListener('close',()=>{for(const m of $('detail-content').querySelectorAll('audio,video')){m.pause();m.removeAttribute('src');m.load();}$('detail-content').replaceChildren();updateUrl(null);});
  for(const button of document.querySelectorAll('[data-status]'))button.onclick=()=>{status=button.dataset.status;document.querySelectorAll('[data-status]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));refresh();};
  $('library-filters').onsubmit=e=>{e.preventDefault();refresh();};$('library-kind').onchange=refresh;$('library-favorite').onchange=refresh;$('refresh-library').onclick=refresh;
  const types=gallery?['image','video']:audioLibrary?['music','sfx','speech']:['image','video','audio','document','whiteboard','investigation','motion','speech','music','sfx','story','asr','enhance'];for(const kind of types)$('library-kind').append(new Option(names[kind],kind));
  if(assetView){$('project-tabs').hidden=true;$('library-title').textContent=gallery?'图库与视频素材':'音乐与音频库';$('library-description').textContent=gallery?'集中查看已生成画面与导入的参考图，直接带入图像创作、动态镜头或长片。':'试听和整理配音、背景音乐与音效。背景音乐可以直接带入长片工作流。';$('create-link').textContent=gallery?'生成图片':'生成音乐或音效';$('create-link').href=gallery?'/image':'/music';document.title=$('library-title').textContent+' · AI STUDIO';}
  if(gallery){$('gallery-upload').hidden=false;$('upload-image').onchange=async()=>{const file=$('upload-image').files[0];if(!file)return;const msg=$('upload-message');try{if(file.size>12*1024*1024)throw new Error('图片不能超过 12 MB');if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('请选择 PNG、JPG 或 WebP 图片');msg.textContent='正在导入参考图片…';const base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('无法读取图片'));reader.readAsDataURL(file);});await api('/api/image-references',{name:file.name,base64});msg.textContent='已导入图库，可作为参考图使用';await refresh();}catch(e){msg.textContent=e.message;}finally{$('upload-image').value='';}};}
  refresh();if(params.get('item'))openDetail(params.get('item'));
})();
