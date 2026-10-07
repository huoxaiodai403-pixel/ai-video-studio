(() => {
 'use strict';
 const host=document.getElementById('model-library-grid'), status=document.getElementById('model-library-status'); let category='all', models=[];
 const text=(tag,value,cls)=>{const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;};
 const info={
  'flux2-klein-4b':['FLUX.2 klein 4B','快速生图、参考图编辑。可带入最多 4 张参考图，适合反复调整人物和场景。'],
  'qwen-image-2512':['Qwen-Image 2512','文本生成插画与场景，适合从描述开始创作。当前接入为文本生图。'],
  'wan2.2-a14b':['Wan2.2 A14B','从首帧生成动态镜头，适合较复杂的主体动作。生成等待时间较长。'],
  'wan2.2-5b':['Wan2.2 5B','较快生成短镜头，适合先试动作和镜头构图。'],
  'ace-step-1.5':['ACE-Step 1.5','生成背景音乐，可在音乐库试听，再用于长片配乐。'],
  'stable-audio-3-sfx':['Stable Audio 3','生成环境声和短音效，当前在 CPU 上运行。']
 };
 async function api(url){const r=await fetch(url);const d=await r.json();if(!r.ok)throw new Error(d.error||'状态读取失败');return d;}
 function render(){host.replaceChildren();for(const m of models.filter(m=>category==='all'||m.category===category)){const card=text('article','','hub-card');card.append(text('span',({image:'图像创作',motion:'动态视频',voice:'配音与角色',music:'音乐与音效',text:'文稿与字幕'})[m.category],'model-kind'),text('h2',m.name),text('p',m.description),text('p',m.state||(m.ready?'组件文件齐全':'尚未安装完整'),m.ready?'model-available':''));
  if(m.components?.length){const details=document.createElement('details'),list=document.createElement('ul');details.className='model-components';details.append(text('summary','查看组件状态'));for(const row of m.components)list.append(text('li',row));details.append(list);card.append(details);}
  const links=text('div','','hub-actions'),a=text('a',m.action||'打开创作工具','hub-button secondary');a.href=m.url;links.append(a);card.append(links);host.append(card);}}
 document.querySelectorAll('[data-category]').forEach(button=>button.onclick=()=>{category=button.dataset.category;document.querySelectorAll('[data-category]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();});
 async function load(){const failures=[];const work=[
  (async()=>{const d=await api('/api/creation');for(const [key,cat,url]of[['image_engines','image','/image'],['motion_engines','motion','/motion']])for(const m of d[key]||[]){const [name,description]=info[m.id]||[m.name,'本机创作引擎'];models.push({...m,category:cat,name,description,url:cat==='image'?url+'?engine='+encodeURIComponent(m.id):url,action:cat==='image'?'用此模型创作':'打开动态镜头',components:m.components.map(c=>(c.exists?'已安装 · ':'缺失 · ')+c.name)});}
   for(const [kind,name,description,url]of[['tts_dir','IndexTTS 2','保留的参考音色配音引擎，可在配音工具中选择。','/speech'],['asr_dir','Qwen3-ASR','把语音转成字幕与文字稿。','/subtitles'],['align_dir','Qwen3 ForcedAligner','为文稿和语音对齐时间轴，用于制片字幕。','/production']]){const m=d.models.find(x=>x.kind===kind);models.push({name,description,category:kind==='tts_dir'?'voice':'text',ready:!!(m?.exists&&m.bytes),state:m?.exists&&m.bytes?'已找到模型目录':'未找到已配置目录',url});}
  })(),
  (async()=>{const d=await api('/api/music');for(const m of d.engines){const [name,description]=info[m.id]||[m.name,'本机音频引擎'];models.push({...m,name,description,category:'music',url:'/music',action:'打开音乐与音效',components:m.details});}})(),
  (async()=>{const d=await api('/api/story/status');models.push({name:d.model||'本地编剧',description:'协助把小说或主题整理成文稿与分镜，可在小说工作流中选择。',category:'text',ready:d.ready,state:d.ready?'服务已连接 · 已找到所选模型':d.message,url:'/novel',action:'打开小说工作流'});})(),
  ...[['qwen3-custom','Qwen3-TTS · 固定音色','适合稳定的中文解说和角色台词；先到音色库试听并选择。'],['qwen3-design','Qwen3-TTS · 声音设计','用文字描述音色和表达方式，生成后可保存为固定角色。'],['qwen3-clone','Qwen3-TTS · 音色克隆','从参考语音提取音色，在配音工具中调整语速与表达。']].map(([engine,name,description])=>(async()=>{const d=await api('/api/voice-library/qwen-status?engine='+engine);models.push({name,description,ready:d.ready,category:'voice',url:engine==='qwen3-custom'?'/voices':'/speech',action:engine==='qwen3-custom'?'挑选角色音色':'打开配音工具',components:d.checks.map(c=>c.name+' · '+c.message)});})())
 ];const results=await Promise.allSettled(work);results.forEach(r=>{if(r.status==='rejected')failures.push(r.reason.message);});models.sort((a,b)=>['image','motion','voice','music','text'].indexOf(a.category)-['image','motion','voice','music','text'].indexOf(b.category));render();status.textContent=`已读取 ${models.length} 个模型入口`+(failures.length?'；部分状态未能读取：'+failures.join('；'):'');}
 load();
})();
