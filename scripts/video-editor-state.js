/* Pure plan and recovery operations shared by the sequence editor and CPU tests. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.VideoEditorState=value})(typeof globalThis==='object'?globalThis:this,()=>{
'use strict';
const skills=new Set(['ffmpeg-skill','video-use','agent-caption','video-subtitle-translator','video-dubbing','app-demo-agent','browser-video-recording','remotion','hyperframes','imagegen']);
function check(value,{empty=false}={}){
 if(!value||typeof value!=='object'||Array.isArray(value)||typeof value.title!=='string'||typeof value.source!=='string'||!Array.isArray(value.steps)||value.steps.length>12||(!empty&&!value.steps.length))throw Error('方案需要工程名称、素材路径和 1–12 个步骤');
 for(const s of value.steps)if(!s||!skills.has(s.skill)||!s.options||typeof s.options!=='object'||Array.isArray(s.options))throw Error('方案包含无法识别的制作步骤');
 return structuredClone(value);
}
function clean(value){const result=check(value);result.source=result.source.trim();for(const s of result.steps)for(const [k,v]of Object.entries(s.options))if(v===''||Array.isArray(v)&&!v.length)delete s.options[k];return result}
function fingerprint(value){if(Array.isArray(value))return '['+value.map(fingerprint).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+fingerprint(value[k])).join(',')+'}';return JSON.stringify(value)}
function comparable(value){
 const request=clean(value),path=value=>typeof value==='string'&&(/^[a-z]:[\\/]/i.test(value)||value.startsWith('\\\\'))?value.replace(/\\/g,'/').toLowerCase():value;
 request.title=request.title.trim();request.source=path(request.source);
 for(const {options:o}of request.steps){for(const key of ['source','image_file','subtitle_file','music'])if(key in o)o[key]=path(o[key]);for(const shot of o.screenshots||[])shot.path=path(shot.path)}
 return request;
}
function samePlan(a,b){try{return fingerprint(comparable(a))===fingerprint(comparable(b))}catch{return false}}
function planDuration(steps,sourceDuration){let duration=Number(sourceDuration)>0?Number(sourceDuration):null;for(const {skill,options:o}of steps){if(o.source)duration=null;if(skill==='remotion')duration=Number(o.duration)||6;else if(skill==='browser-video-recording')duration=(o.screenshots||[]).reduce((n,s)=>n+(Number(s.duration)||2),0)||null;else if(['hyperframes','imagegen'].includes(skill))duration=null;else if(['ffmpeg-skill','video-use'].includes(skill)){if(o.cuts?.length)duration=o.cuts.reduce((n,c)=>n+Math.max(0,Number(c.end)-Number(c.start)),0);else if(skill==='video-use')duration=null;if(duration!==null)duration/=Number(o.speed)||1}}return Number.isFinite(duration)&&duration>0?duration:null}
function read(storage,key){const raw=storage.getItem(key);if(!raw)return null;try{const value=JSON.parse(raw);if(value.version!==1)throw Error('Unknown draft version');check(value.request,{empty:true});return value}catch(error){
 // Never silently overwrite the only copy of a damaged or newer draft.
 storage.setItem(key+':recovery:'+Date.now(),raw);throw Error('本机草稿无法读取，原始内容已备份；可从恢复文件检查。');
}}
function write(storage,key,value){check(value.request,{empty:true});storage.setItem(key,JSON.stringify({...value,version:1,savedAt:Date.now()}))}
return {check,clean,fingerprint,samePlan,planDuration,read,write};
});
