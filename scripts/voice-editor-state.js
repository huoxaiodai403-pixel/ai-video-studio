/* Raw form recovery deliberately keeps incomplete numbers and missing references. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.VoiceEditorState=value})(typeof globalThis==='object'?globalThis:this,()=>{
  'use strict';
  const object=value=>value&&typeof value==='object'&&!Array.isArray(value);
  function check(value) {
    if(!object(value)||value.version!==1)throw Error('无法识别音色草稿版本');
    for(const key of ['editor','previous'])if(value[key]!=null){
      const row=value[key];
      if(!object(row)||!object(row.fields)||!object(row.voice)||!Object.values(row.fields).every(v=>typeof v==='string')||
         row.id!=null&&typeof row.id!=='string'||row.revision!=null&&typeof row.revision!=='string')throw Error('音色草稿内容不完整');
    }
    for(const key of ['fixed','previousFixed'])if(value[key]!=null&&(!object(value[key])||typeof value[key].job!=='string'||!object(value[key].fields)||!Object.values(value[key].fields).every(v=>typeof v==='string')))throw Error('角色草稿内容不完整');
    return structuredClone(value);
  }
  function read(storage,key) {
    const raw=storage.getItem(key);if(raw===null)return {version:1};
    try{return check(JSON.parse(raw))}catch(error){throw Object.assign(Error('已有草稿无法读取，已停止自动覆盖；可先导出原始内容。'),{raw})}
  }
  function write(storage,key,value){storage.setItem(key,JSON.stringify(check(value)))}
  return {check,read,write};
});
