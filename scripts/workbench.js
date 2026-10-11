/* Shared navigation only: page controls and their handlers stay in place. */
(()=>{
 const main=document.querySelector('main');if(!main)return;
 if(!main.id)main.id='workbench-main';main.tabIndex=-1;
 const skip=document.querySelector('.workbench-skip')||document.createElement('a');skip.className='workbench-skip';skip.href='#'+main.id;skip.textContent='跳到主要内容';if(!skip.isConnected)document.body.prepend(skip);
 const oldNav=main.querySelector('nav[aria-label="工作台导航"]'),heading=main.querySelector('h1');
 const title=({'/':'工作台','/home':'工作台','/workflows':'工作流','/generation':'生成工坊'})[location.pathname]||heading?.textContent||'工作台';
 const navigationTitle=()=>['/','/home'].includes(location.pathname)&&location.hash==='#tools'?'创作工具':title;
 // The server owns navigation markup and route grouping. No second menu catalog.
 const sidebar=document.querySelector('#workbench-nav[data-shell="server"]');
 if(!sidebar)return;
 const nav=sidebar.querySelector('nav'),foot=sidebar.querySelector('.sidebar-footer');
 for(const [rel,href,type,sizes] of [['icon','/assets/brand/studio-mark.svg?v=2','image/svg+xml','any'],['alternate icon','/assets/brand/studio-mark.ico?v=2','image/x-icon','16x16 32x32 48x48']]){
  const icon=document.createElement('link');icon.rel=rel;icon.href=href;icon.type=type;icon.sizes=sizes;document.head.append(icon);
 }
 function renderNav(){
  const home=['/','/home'].includes(location.pathname),current=home?(location.hash==='#tools'?'tools':'home'):sidebar.dataset.currentGroup;
  for(const a of nav.querySelectorAll('.nav-primary')){
   const selected=a.dataset.navGroup===current;a.classList.toggle('is-active',selected);
   const exact=selected&&(a.pathname===location.pathname&&a.hash===location.hash||current==='home'&&location.pathname==='/'&&!location.hash);
   if(exact)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');
  }
  const mobileToggle=document.querySelector('.nav-toggle');if(mobileToggle)mobileToggle.textContent='☰  AI STUDIO · '+navigationTitle();
 }
 renderNav();window.addEventListener('hashchange',renderNav);oldNav?.remove();
 const help=sidebar.querySelector('.nav-help');
 document.addEventListener('click',event=>{if(help?.open&&!help.contains(event.target))help.open=false});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&help?.open){event.preventDefault();help.open=false;help.querySelector('summary').focus()}});
 const toggle=document.querySelector('.nav-toggle')||document.createElement('button');toggle.className='nav-toggle';toggle.textContent='☰  AI STUDIO · '+navigationTitle();toggle.setAttribute('aria-label','展开导航');toggle.setAttribute('aria-controls','workbench-nav');toggle.setAttribute('aria-expanded','false');if(!toggle.isConnected)document.body.prepend(toggle);
 const shade=document.querySelector('.nav-shade')||document.createElement('button');shade.className='nav-shade';shade.tabIndex=-1;shade.setAttribute('aria-label','关闭导航');if(!shade.isConnected)document.body.append(shade);
 const mobile=window.matchMedia('(max-width:700px)');let drawerOpen=false,mainWasInert=false;
 function setNav(open,{returnFocus=true,animate=true}={}){
  open=Boolean(open&&mobile.matches);
  if(open&&!drawerOpen){mainWasInert=main.inert;main.inert=true}
  if(!open&&drawerOpen)main.inert=mainWasInert;
  const wasOpen=drawerOpen;drawerOpen=open;
  if(!animate)document.body.classList.remove('nav-motion');
  else if(wasOpen!==open&&!window.matchMedia('(prefers-reduced-motion:reduce)').matches)document.body.classList.add('nav-motion');
  document.body.classList.toggle('nav-open',open);sidebar.inert=mobile.matches&&!open;
  toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'收起导航':'展开导航');
  if(open)(nav.querySelector('.nav-primary.is-active')||nav.querySelector('a'))?.focus({preventScroll:true});
  else if(wasOpen&&returnFocus&&mobile.matches)toggle.focus();
 }
 sidebar.addEventListener('transitionend',event=>{if(event.target===sidebar&&event.propertyName==='transform')document.body.classList.remove('nav-motion')});
 toggle.onclick=()=>setNav(!drawerOpen);shade.onclick=()=>setNav(false);
 sidebar.addEventListener('click',e=>{
  const link=e.target.closest('a');if(!link)return;
  const destination=new URL(link.href,location.href),sameDocument=destination.origin===location.origin&&destination.pathname===location.pathname&&destination.search===location.search;
  const wasOpen=drawerOpen;setNav(false,{returnFocus:link.target==='_blank'||sameDocument});
  if(wasOpen&&sameDocument&&destination.hash)requestAnimationFrame(()=>{
   let target;try{target=document.getElementById(decodeURIComponent(destination.hash.slice(1)))}catch{return}
   if(target){if(!target.hasAttribute('tabindex'))target.tabIndex=-1;target.focus({preventScroll:true})}
  });
 });
 mobile.addEventListener('change',()=>{
  const sidebarHadFocus=sidebar.contains(document.activeElement);setNav(false,{returnFocus:false,animate:false});
  if(mobile.matches&&sidebarHadFocus)toggle.focus();
  else if(!mobile.matches&&document.activeElement===toggle)main.focus({preventScroll:true});
 });setNav(false,{animate:false});
 document.addEventListener('keydown',e=>{
  if(!drawerOpen||e.defaultPrevented)return;
  if(e.key==='Escape'){e.preventDefault();setNav(false);return}
  if(e.key==='Tab'){
   const focusable=[toggle,...sidebar.querySelectorAll('a[href],button:not([disabled]),summary,[tabindex="0"]')].filter(el=>el.getClientRects().length&&(!el.closest('details:not([open])')||el.tagName==='SUMMARY'));
   const index=focusable.indexOf(document.activeElement),next=e.shiftKey?index-1:index+1;
   if(index<0||next<0||next>=focusable.length){e.preventDefault();focusable[e.shiftKey?focusable.length-1:0]?.focus()}
  }
 });
 const status=document.getElementById('services');
 let runtimePending=false;async function health(){if(runtimePending)return;runtimePending=true;try{const response=await fetch('/api/runtime');if(!response.ok)throw Error('unavailable');const runtime=await response.json();foot.querySelector('.status-dot').classList.add('ready');foot.querySelector('.health').textContent='工作台已连接';foot.title='工作台 v'+runtime.version+(runtime.edition==='friend'?'；可使用在线服务、系统配音与 CPU 渲染。':'；各项能力请在在线服务与本地模型中查看。')}catch{foot.querySelector('.status-dot').classList.remove('ready');foot.querySelector('.health').textContent='工作台连接中断'}finally{runtimePending=false}}health();setInterval(health,30000);
 // Overview pages only read service status; this does not load or start a model.
 if(document.body.dataset.workbenchServices==='true'&&status){let pending=false;async function check(){if(pending)return;pending=true;try{const r=await fetch('/api/services');if(!r.ok)throw Error('HTTP '+r.status);const s=await r.json();status.textContent=`千问生图：${s.comfyui?.ready?'就绪':'未启动'} · 配音：${s.tts?.ready?'就绪':s.tts?.starting?'正在加载':'未启动'}`}catch(e){status.textContent='服务状态读取失败：'+e.message}finally{pending=false}}check();setInterval(check,15000)}
 // Keep editor progress local; the catalog owns browsing the complete history.
 // Never rebuild, move or remove media/control nodes owned by a page's polling code.
 const histories={'/image':['jobs','image'],'/motion':['jobs','motion'],'/speech':['jobs','speech'],'/music':['jobs','music'],'/subtitles':['jobs','asr'],'/enhance':['enhance-jobs','enhance'],'/investigation':['jobs','investigation'],'/novel':['novel-jobs','video'],'/production':['jobs','video']};
 const history=histories[location.pathname],host=history&&document.getElementById(history[0]);
 if(host&&!host.hasAttribute('data-managed-history')){
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
