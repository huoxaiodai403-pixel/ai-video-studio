/* Shared role import controls; all editors keep their own project snapshots. */
(()=>{'use strict';
 window.CharacterPicker={mount(host,apply,feedback,context=()=>null){
  const row=document.createElement('div');row.className='toolbar';
  const label=document.createElement('label');label.className='form-field';label.textContent='从角色库带入';
  const select=document.createElement('select');label.append(select);
  const use=document.createElement('button');use.type='button';use.className='secondary';use.textContent='带入本片';
  const refresh=document.createElement('button');refresh.type='button';refresh.className='quiet';refresh.textContent='刷新角色';
  const link=document.createElement('a');link.href='/characters';link.target='_blank';link.rel='noopener';link.textContent='管理角色库 →';
  row.append(label,use,refresh,link);host.append(row);let loading=false;
  async function api(url){const response=await fetch(url),value=await response.json();if(!response.ok)throw Error(value.error||'角色读取失败');return value}
  async function load(){if(loading)return;loading=true;use.disabled=true;refresh.disabled=true;try{const chosen=select.value,result=await api('/api/characters');select.replaceChildren(new Option('选择已保存角色',''),...result.characters.map(r=>new Option(r.name+' · '+(r.project||'未分组')+' · 版本 '+r.revision,r.id)));if([...select.options].some(o=>o.value===chosen))select.value=chosen}catch(error){feedback(error.message,true)}finally{loading=false;use.disabled=false;refresh.disabled=false}}
  use.onclick=async()=>{if(!select.value)return;const identity=select.value,before=context();use.disabled=true;try{const actor=await api('/api/characters?id='+encodeURIComponent(identity));if(context()!==before)throw Error('读取角色期间稿件已有修改，当前输入保留；请再次带入');await apply(actor)}catch(error){feedback(error.message,true)}finally{use.disabled=false;if(document.activeElement===document.body)use.focus({preventScroll:true})}};
  refresh.onclick=load;load();
 }};
})();
