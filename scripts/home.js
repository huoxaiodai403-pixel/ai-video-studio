(()=>{
 const button=document.getElementById('refresh-overview'),status=document.getElementById('task-overview-status'),list=document.getElementById('recent-products');let pending=false;
 const states={done:'已完成',queued:'排队中',running:'进行中',error:'需处理',draft:'草稿',preview:'预览'};
 const workflows={image:'图像',motion:'短镜头',whiteboard:'手绘白板',investigation:'调查长片',video:'视频制作',enhance:'视频增强',speech:'配音',music:'配乐',sfx:'音效',asr:'字幕',story:'编剧'};
 function localUrl(value){if(typeof value!=='string'||!value.startsWith('/')||value.startsWith('//'))return null;try{const u=new URL(value,location.origin);return u.origin===location.origin?u.pathname+u.search+u.hash:null}catch(_){return null}}
 function render(item){
  const row=document.createElement('li');row.className='hub-product';
  const thumb=localUrl(item.thumbnail_url);if(thumb){const img=document.createElement('img');img.src=thumb;img.alt='';img.loading='lazy';row.append(img)}
  const body=document.createElement('div');body.className='hub-product-body';const title=document.createElement('h3');title.textContent=item.title||item.project_id||'未命名作品';body.append(title);
  const meta=document.createElement('p');meta.textContent=[workflows[item.workflow]||'作品',states[item.status]||'状态待确认',item.created_at?new Date(item.created_at*1000).toLocaleDateString('zh-CN'):null].filter(Boolean).join(' · ');body.append(meta);
  if(item.error){const note=document.createElement('p');note.textContent=item.error;body.append(note)}
  const a=document.createElement('a');a.href='/library?item='+encodeURIComponent(item.id);a.textContent='查看作品';body.append(a);row.append(body);return row;
 }
 async function refresh(){
  if(pending)return;pending=true;button.disabled=true;
  try{const r=await fetch('/api/library?view=products&status=all');if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!Array.isArray(data.items))throw Error('作品数据格式不正确');
   list.replaceChildren(...data.items.slice(0,6).map(render));status.textContent=data.items.length?`最近 ${Math.min(data.items.length,6)} 条记录 · 共 ${data.total??data.items.length} 条。完成状态表示交付文件已生成，内容仍需回看。`:'还没有作品记录。选择上方工作流或下方工具开始。';
  }catch(e){list.replaceChildren();status.textContent='暂时无法读取作品：'+e.message+'。仍可使用创作工具。'}finally{pending=false;button.disabled=false}
 }
 button.addEventListener('click',refresh);refresh();
})();
