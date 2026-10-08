/* Shared navigation only: page controls and their handlers stay in place. */
(()=>{
 const main=document.querySelector('main');if(!main)return;
 const oldNav=main.querySelector('nav:not(.service-nav)'),heading=main.querySelector('h1');
 const title=({'/':'工作台','/home':'工作台','/workflows':'工作流'})[location.pathname]||heading?.textContent||'工作台';
 const existing=new Map([...(oldNav?.querySelectorAll('a')||[])].map(a=>[a.getAttribute('href'),a]));
 const moduleIcons={
  home:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="4" rx="1.5"/><rect x="14" y="11" width="7" height="10" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
  library:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M9 4 6 9m9-5-3 5m8-5-3 5"/><path d="m10 12 5 3-5 3z"/>',
  assets:'<path d="M3 7V5a2 2 0 0 1 2-2h4l3 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 8h18m-14 9 3-3 3 3 3-4 2 4"/>',
  workflows:'<rect x="3" y="3" width="6" height="6" rx="1.5"/><rect x="15" y="3" width="6" height="6" rx="1.5"/><rect x="15" y="15" width="6" height="6" rx="1.5"/><path d="M9 6h6M6 9v7a2 2 0 0 0 2 2h7m3-9v6"/>',
  tools:'<path d="m14 6 4-3a2.1 2.1 0 0 1 3 3l-8 10-5-5 6-5Z"/><path d="m14 6 4 4M8 11l5 5-2 3a4 4 0 0 1-3 2H3c2-1 1-4 3-6l2-4Z"/>',
  settings:'<path d="m10 3-.6 2a7 7 0 0 0-1.6.9l-2-.5-2 3.4 1.4 1.6a7 7 0 0 0 0 1.9l-1.4 1.6 2 3.5 2-.5a7 7 0 0 0 1.6.9l.6 2.2h4l.6-2.2a7 7 0 0 0 1.6-.9l2 .5 2-3.5-1.4-1.6a7 7 0 0 0 0-1.9l1.4-1.6-2-3.4-2 .5a7 7 0 0 0-1.6-.9L14 3h-4Z"/><circle cx="12" cy="11.7" r="3"/>'
 };
 const groups=[
  {id:'home',name:'工作台',href:'/home',icon:'home',items:[]},
  {id:'library',name:'我的作品',href:'/library',icon:'library',items:[]},
  {id:'assets',name:'资源库',href:'/assets',icon:'assets',items:[['/gallery','图库'],['/audio-library','音频库'],['/voices','音色库'],['/model-library','模型库']]},
  {id:'workflows',name:'工作流',href:'/workflows',icon:'workflows',items:[['/whiteboard','手绘白板'],['/investigation','热点调查长片'],['/novel','小说转漫剧'],['/production','通用视频制作']]},
  {id:'tools',name:'创作工具',href:'/home#tools',icon:'tools',items:[['/image','图像创作'],['/motion','短镜头'],['/speech','配音与声音设计'],['/music','音乐与音效生成'],['/subtitles','语音转字幕'],['/enhance','视频增强与补帧']]},
  {id:'settings',name:'设置',href:'/settings',icon:'settings',items:[['/settings','在线服务'],['/models','本地模型'],['http://127.0.0.1:8188','ComfyUI'],['/learn','上手教程'],['/guide','使用说明'],['/director','运镜词典与方法'],['/plan','部署方案'],['/research','文章与项目参考']]}
 ];
 const sidebar=document.createElement('aside');sidebar.className='sidebar';sidebar.id='workbench-nav';
 sidebar.innerHTML='<a class="brand" href="/home"><img class="brand-mark" src="/assets/brand/studio-mark.svg" width="38" height="38" alt=""><span><strong>AI STUDIO</strong><small>视频创作工作台</small></span></a>';
 for(const [rel,href,type,sizes] of [['icon','/assets/brand/studio-mark.svg?v=2','image/svg+xml','any'],['alternate icon','/assets/brand/studio-mark.ico?v=2','image/x-icon','16x16 32x32 48x48'],['apple-touch-icon','/assets/brand/studio-mark.png?v=2','image/png','512x512']]){
  const icon=document.createElement('link');icon.rel=rel;icon.href=href;icon.type=type;icon.sizes=sizes;document.head.append(icon);
 }
 const nav=document.createElement('nav');nav.setAttribute('aria-label','工作台导航');
 function selectedGroup(){
  if(['/home','/'].includes(location.pathname)&&location.hash==='#tools')return 'tools';
  if(location.pathname==='/')return 'home';
  for(const g of groups)if(g.href===location.pathname)return g.id;
  return groups.find(g=>g.items.some(([href])=>href===location.pathname))?.id||'settings';
 }
 function link(href,label,icon,primary=false){
  // A category and its first child can share a destination but must remain separate DOM nodes.
  const key=primary?'primary:'+href:href,a=existing.get(key)||document.createElement('a');existing.set(key,a);
  a.href=href;a.replaceChildren();a.className=primary?'nav-primary':'nav-child';a.removeAttribute('aria-current');
  if(icon){const mark=document.createElementNS('http://www.w3.org/2000/svg','svg');mark.classList.add('nav-icon');mark.setAttribute('viewBox','0 0 24 24');mark.setAttribute('aria-hidden','true');mark.setAttribute('focusable','false');mark.innerHTML=moduleIcons[icon];a.append(mark)}
  const name=document.createElement('span');name.textContent=label;a.append(name);
  if(href.startsWith('http')){a.target='_blank';a.rel='noopener noreferrer';const ext=document.createElement('span');ext.className='external';ext.textContent='↗';ext.setAttribute('aria-hidden','true');a.append(ext)}
  else{a.removeAttribute('target');a.removeAttribute('rel')}
  return a;
 }
 function renderNav(){
  nav.replaceChildren();const current=selectedGroup();
  for(const g of groups){
   const section=document.createElement('div');section.className='nav-section'+(g.id===current?' is-active':'');
   const primary=link(g.href,g.name,g.icon,true);section.append(primary);
   const exact=location.pathname+location.hash;
   if(g.href===exact||(g.href===location.pathname&&!location.hash)||(g.id==='home'&&location.pathname==='/'&&location.hash!=='#tools')||(g.id==='tools'&&location.pathname==='/'&&location.hash==='#tools'))primary.setAttribute('aria-current','page');
   if(g.id===current&&g.items.length){
    const children=document.createElement('div');children.className='nav-children';children.setAttribute('aria-label',g.name+'分类');
    for(const [href,label]of g.items){const a=link(href,label);if(href===exact||href===location.pathname){a.setAttribute('aria-current','page');primary.removeAttribute('aria-current')}children.append(a)}
    section.append(children);
   }
   nav.append(section);
  }
 }
 renderNav();window.addEventListener('hashchange',renderNav);sidebar.append(nav);
 const foot=document.createElement('div');foot.className='sidebar-footer';foot.innerHTML='<span class="status-dot"></span><span class="health">正在检查服务</span><small>本地优先 · 支持在线接口</small>';sidebar.append(foot);oldNav?.remove();document.body.prepend(sidebar);
 const toggle=document.createElement('button');toggle.className='nav-toggle';toggle.textContent='☰  AI STUDIO · '+title;toggle.setAttribute('aria-label','展开导航');toggle.setAttribute('aria-controls','workbench-nav');toggle.setAttribute('aria-expanded','false');document.body.prepend(toggle);
 const shade=document.createElement('button');shade.className='nav-shade';shade.tabIndex=-1;shade.setAttribute('aria-label','关闭导航');document.body.append(shade);
 function setNav(open){document.body.classList.toggle('nav-open',open);toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'收起导航':'展开导航');if(open)(nav.querySelector('[aria-current]')||nav.querySelector('a'))?.focus()}
 toggle.onclick=()=>setNav(!document.body.classList.contains('nav-open'));shade.onclick=()=>setNav(false);
 nav.addEventListener('click',e=>{if(e.target.closest('a'))setNav(false)});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('nav-open')){setNav(false);toggle.focus()}});
 const status=document.getElementById('services');
 let runtimePending=false;async function health(){if(runtimePending)return;runtimePending=true;try{const response=await fetch('/api/runtime');if(!response.ok)throw Error('unavailable');const runtime=await response.json();foot.querySelector('.status-dot').classList.add('ready');foot.querySelector('.health').textContent='工作台已连接';foot.title='工作台 v'+runtime.version+'；各项能力请在在线服务与本地模型中查看。'}catch{foot.querySelector('.status-dot').classList.remove('ready');foot.querySelector('.health').textContent='工作台连接中断'}finally{runtimePending=false}}health();setInterval(health,30000);
 // Overview pages only read service status; this does not load or start a model.
 if(document.body.dataset.workbenchServices==='true'&&status){let pending=false;async function check(){if(pending)return;pending=true;try{const r=await fetch('/api/services');if(!r.ok)throw Error('HTTP '+r.status);const s=await r.json();status.textContent=`千问生图：${s.comfyui?.ready?'就绪':'未启动'} · 配音：${s.tts?.ready?'就绪':s.tts?.starting?'正在加载':'未启动'}`}catch(e){status.textContent='服务状态读取失败：'+e.message}finally{pending=false}}check();setInterval(check,15000)}
 // Keep editor progress local; the catalog owns browsing the complete history.
 // Never rebuild, move or remove media/control nodes owned by a page's polling code.
 const histories={'/image':['jobs','image'],'/motion':['jobs','motion'],'/speech':['jobs','speech'],'/music':['jobs','music'],'/subtitles':['jobs','asr'],'/enhance':['enhance-jobs','enhance'],'/whiteboard':['tasks','whiteboard'],'/investigation':['jobs','investigation'],'/novel':['novel-jobs','video'],'/production':['jobs','video']};
 const history=histories[location.pathname],host=history&&document.getElementById(history[0]);
 if(host){
  const bar=document.createElement('div');bar.className='workbench-results-summary';
  const note=document.createElement('p'),all=document.createElement('a');note.className='workbench-results-note';all.href='/library';all.textContent='查看全部作品 →';bar.append(note,all);host.before(bar);
  const idFrom=text=>String(text||'').match(/^\s*([a-z]+-[a-z0-9]+|[a-f0-9]{10,32})(?:\s*[·•:：]|\s*$)/i)?.[1];
  function rows(){const result=[];let flat=null;for(const child of host.children){
   if(child.tagName==='ARTICLE'||child.dataset.jobId){const first=child.querySelector('p'),id=child.dataset.jobId||idFrom(first?.textContent)||idFrom(child.querySelector('h3')?.textContent);const state=child.querySelector('.task-state,.tag,.job-status')?.textContent||first?.textContent||'';result.push({id,state,nodes:[child]});flat=null}
   else if(child.tagName==='P'&&idFrom(child.textContent)){flat={id:idFrom(child.textContent),state:child.textContent,nodes:[child]};result.push(flat)}
   else if(flat)flat.nodes.push(child);
  }return result}
  function update(){
   const context=[...document.querySelectorAll('#result,#message,#action-status,#novel-status,#enhance-status')].filter(e=>!host.contains(e)).map(e=>e.textContent).join('\n');
   const selected=new URLSearchParams(location.search).get('project'),current=main.dataset.currentProject||main.dataset.currentJobId;
   let recent=0,hidden=0;for(const row of rows()){
    const active=/\b(queued|running|rendering|generating)\b|排队中|已排队|运行中|生成中|处理中/.test(row.state);
    const terminal=!active&&/\b(done|error|failed|interrupted|saved|cancelled)\b|已完成|失败|已保存|已取消/.test(row.state);
    const playing=row.nodes.some(n=>[...n.querySelectorAll('audio,video'),...(n.matches('audio,video')?[n]:[])].some(m=>!m.paused&&!m.ended));
    const focused=row.nodes.some(n=>n.contains(document.activeElement));
    const protectedRow=row.id&&(row.id===selected||row.id===current||context.includes(row.id));
    const show=!terminal||recent++<3||protectedRow||playing||focused;
    for(const n of row.nodes)n.classList.toggle('workbench-history-hidden',!show);if(!show)hidden++;
   }
   const text='这里保留当前任务与最近结果。'+(hidden?`另有 ${hidden} 条历史记录可在作品页查看。`:'全部历史统一在作品页管理。');if(note.textContent!==text)note.textContent=text;
  }
  let scheduled=false;function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;update()})}
  new MutationObserver(schedule).observe(main,{childList:true,characterData:true,subtree:true,attributes:true,attributeFilter:['data-current-project','data-current-job-id']});
  host.addEventListener('play',schedule,true);host.addEventListener('pause',schedule,true);host.addEventListener('focusin',schedule);update();
 }
})();
