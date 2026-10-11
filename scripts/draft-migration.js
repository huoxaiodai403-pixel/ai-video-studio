/* Preserve legacy friend drafts when an existing installation joins the single app. */
(function(root,factory){const migrate=factory();if(typeof module==='object'&&module.exports)module.exports=migrate;else{try{migrate(root.StudioStorage.local);migrate(root.StudioStorage.session,true)}catch{ /* Original entries are never removed. */ }}})(typeof globalThis==='object'?globalThis:this,()=>{
 'use strict';
 return function migrate(storage,session=false){
  const copied=[],kept=[];
  const keys=Array.from({length:storage.length},(_,index)=>storage.key(index));
  for(const key of keys){
   let target;
   if(/^ai-video-sequence-v1-friend-/.test(key))target=key.replace('v1-friend-','v1-full-');
   else if(/^(ai-video-tool-|ai-studio-(investigation|novel|production)-|ai-video-voices-v1-)/.test(key)&&key.includes('-friend'))target=key.replace('-friend','-development');
   else continue;
   if(storage.getItem(target)!==null){kept.push(key);continue}
   const raw=storage.getItem(key);
   storage.setItem(target,session&&key.endsWith(':active')?raw.replace('-friend','-development'):raw);
   copied.push(target);
  }
  return {copied,kept};
 };
});
