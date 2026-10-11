/* Pure storyboard state operations for generation, novel and production editors. */
(()=>{
 'use strict';
 const clone=value=>JSON.parse(JSON.stringify(value));
 function merge(base,extra){const result=clone(base||{});for(const [key,value]of Object.entries(extra||{})){if(['__proto__','constructor','prototype'].includes(key))continue;result[key]=value&&typeof value==='object'&&!Array.isArray(value)?merge(result[key]&&typeof result[key]==='object'?result[key]:{},value):clone(value)}return result}
 function check(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||!Array.isArray(value.scenes)||value.scenes.length>12)throw Error('分镜应包含最多 12 个 scenes。');
  const draft=clone(value),ids=new Set();
  for(const key of ['title','source_text','voice_reference'])if(draft[key]!==undefined&&draft[key]!==null&&typeof draft[key]!=='string')throw Error(key+' 应为文本。');
  for(const scene of draft.scenes){if(!scene||typeof scene!=='object'||Array.isArray(scene)||typeof scene.narration!=='string')throw Error('每个镜头都需要文字旁白 narration。');if(!scene.id)scene.id=nextId(draft.scenes);if(!/^[A-Za-z0-9_-]{1,40}$/.test(scene.id)||ids.has(scene.id))throw Error('镜头编号应唯一，且只包含 1–40 位字母、数字、下划线或短横线。');ids.add(scene.id);for(const key of ['subject','style','motion_prompt'])if(scene[key]!==undefined&&typeof scene[key]!=='string')throw Error('镜头 '+key+' 应为文本。')}
  if(draft.characters!==undefined&&(!draft.characters||typeof draft.characters!=='object'||Array.isArray(draft.characters)))throw Error('角色配置应为 characters 对象。');
  if(Object.entries(draft.characters||{}).some(([name,voice])=>!name.trim()||name.length>50||!voice||typeof voice!=='object'||Array.isArray(voice)))throw Error('角色需要有效名称和音色配置。');
  if(draft.settings!==undefined&&(!draft.settings||typeof draft.settings!=='object'||Array.isArray(draft.settings)))throw Error('settings 应为本次参数对象。');
  for(const key of ['models','image','motion','output','voice','story'])if(draft.settings&&Object.hasOwn(draft.settings,key)&&(!draft.settings[key]||typeof draft.settings[key]!=='object'||Array.isArray(draft.settings[key])))throw Error('settings.'+key+' 应为参数对象。');
  for(const scene of draft.scenes)if(scene.voice!==undefined&&(!scene.voice||typeof scene.voice!=='object'||Array.isArray(scene.voice)))throw Error('镜头 voice 应为音色参数对象。');
  if(draft.backends!==undefined&&(!draft.backends||typeof draft.backends!=='object'||Array.isArray(draft.backends)||Object.entries(draft.backends).some(([key,value])=>!['tts','asr','image','video'].includes(key)||!['local','online'].includes(value))))throw Error('模型来源只支持 local 或 online。');
  if(draft.render_mode!==undefined&&!['illustrated','whiteboard'].includes(draft.render_mode))throw Error('制作模式只支持 illustrated 或 whiteboard。');
  return draft;
 }
 function nextId(scenes){const ids=new Set(scenes.map(scene=>scene?.id));let index=1;while(ids.has('scene'+String(index).padStart(2,'0')))index++;return 'scene'+String(index).padStart(2,'0')}
 function restoreSettings(defaults,saved){const result=merge(defaults,saved);for(const [kind,engine]of [['image','qwen-image-2512'],['motion','wan2.2-5b']])if(saved?.[kind]&&!Object.hasOwn(saved[kind],'engine')&&['width','height','steps','seed'].every(key=>Object.hasOwn(saved[kind],key)))result[kind].engine=engine;if(saved?.voice&&!Object.hasOwn(saved.voice,'engine')&&['reference','emotion','intensity','speed'].every(key=>Object.hasOwn(saved.voice,key)))result.voice.engine='index-tts';return result}
 function stable(value){if(Array.isArray(value))return '['+value.map(stable).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+stable(value[key])).join(',')+'}';return JSON.stringify(value)}
 function mergeGeneratedPlan(base,edited,incoming){
  // Only one server revision consisting solely of generated-media attachment
  // can be rebased automatically. Authored or reviewed changes still conflict.
  if(!base||!edited||!incoming||!base.id||base.id!==edited.id||base.id!==incoming.id||
     !Number.isInteger(base.revision)||edited.revision!==base.revision||incoming.revision!==base.revision+1||
     !Array.isArray(base.shots)||!Array.isArray(edited.shots)||!Array.isArray(incoming.shots))return null;
  const omit=(value,keys)=>Object.fromEntries(Object.entries(value).filter(([key])=>!keys.includes(key)));
  if(stable(omit(base,['revision','updated_at','shots']))!==stable(omit(incoming,['revision','updated_at','shots']))||
     base.shots.length!==incoming.shots.length)return null;
  const fields=['status','asset_path'],changed=new Map(),prior=new Map(base.shots.map(shot=>[shot.id,shot]));
  if(prior.size!==base.shots.length||new Set(edited.shots.map(shot=>shot.id)).size!==edited.shots.length)return null;
  for(let i=0;i<base.shots.length;i++){
   const old=base.shots[i],next=incoming.shots[i];
   if(stable(omit(old,fields))!==stable(omit(next,fields)))return null;
   if(stable(old)!==stable(next)){
    if(next.status!=='generated'||typeof next.asset_path!=='string'||!next.asset_path)return null;
    changed.set(old.id,next);
   }
  }
  if(!changed.size)return null;
  const result=clone(edited),globalFields=['style','character','voice_id','speech_backend','image_backend'];
  const globalChanged=globalFields.some(key=>edited[key]!==base[key]);
  const shotFields=['narration','visual','action','camera','duration','reference','voice_id'];
  for(const shot of result.shots){
   const old=prior.get(shot.id),generated=changed.get(shot.id);
   if(!old||!generated||['status','asset_path','review'].some(key=>shot[key]!==old[key]))continue;
   shot.asset_path=generated.asset_path;
   shot.status=generated.status;
   if(globalChanged||shotFields.some(key=>shot[key]!==old[key])){
    shot.status='needs-fix';
    const note='【待复查】创作内容或全片设定已修改，保留的关联素材为旧版本，请重新审看后确认。';
    if(!(shot.review||'').includes(note))shot.review=[shot.review,note].filter(Boolean).join('\n');
   }
  }
  result.revision=incoming.revision;result.updated_at=incoming.updated_at;
  return result;
 }
 const api={clone,merge,check,nextId,restoreSettings,mergeGeneratedPlan,fingerprint:stable};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else window.StoryboardState=api;
})();
