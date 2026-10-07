/* Source-based tools shared by the directing desk and novel scene editor. */
window.Director=(()=>{
 const api=Creation.api;let data;
 const ready=api('/api/director').then(d=>data=d);
 const node=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e};
 function select(rows,empty){const s=node('select');if(empty)s.append(new Option(empty,''));for(const row of rows)s.append(new Option(row.title,row.id));return s}
 function label(parent,text,element){const l=node('label',text);l.append(element);parent.append(l);return element}
 function input(parent,text,value='',area=false){const e=node(area?'textarea':'input');e.value=value;return label(parent,text,e)}
 function cameraEditor(parent,initial,onApply,compact=false){
   const form=node('div'),grid=node('div');grid.className='control-grid';form.append(grid);
   const camera=label(grid,'运镜方法',select(data.cameras));camera.value=initial.camera||'dolly-in';
   const fields={};const defs=compact?[['action','本镜人物动作'],['end','结束构图'],['invariants','保持不变']]:[['subject','主体与环境'],['action','人物动作'],['framing','景别、机位与镜头'],['direction','摄影机方向与路线'],['speed','运动速度'],['target','摄影目标'],['start','起始构图'],['end','结束构图'],['stability','稳定方式'],['invariants','保持不变']];
   for(const [key,title]of defs)fields[key]=input(grid,title,initial[key]||'');
   const tip=node('p');tip.className='small';
   const update=()=>{const row=data.cameras.find(r=>r.id===camera.value);tip.textContent=row.tip};camera.onchange=update;update();
   const button=node('button',compact?'应用到本镜（替换运镜文本）':'生成镜头提示词');button.type='button';
   const message=node('p');message.setAttribute('role','status');button.onclick=async()=>{try{button.disabled=true;if(compact&&!fields.action.value.trim())throw Error('请先填写需要保留的人物动作，避免与旧运镜混在一起');const values={camera:camera.value,...Object.fromEntries(Object.entries(fields).map(([k,e])=>[k,e.value]))};const result=await api('/api/director/camera',values);onApply(result.prompt,values);message.textContent='已应用；请检查动作、路线和结束构图。'}catch(e){message.textContent=e.message}finally{button.disabled=false}};
   form.append(tip,button,message);parent.append(form);
 }
 function mountScene(card,scene,onApply){const details=node('details');details.append(node('summary','运镜词典 · 为这个镜头选择方法'));details.append(node('p','从上方原提示词提取需要保留的人物动作，填入下方；应用会替换运镜文本，旁白与画面描述保持不变。'));cameraEditor(details,scene.camera_plan||{action:'',invariants:'人物外貌、服装与场景保持一致'},onApply,true);card.append(details)}
 function methodSelect(parent,identity=''){const s=label(parent,'导演方法（用于 AI 编剧；原文分段不调用）',select(data.templates,'默认编剧'));s.id='director-method';s.value=identity;const detail=node('p');detail.className='small';const update=()=>detail.textContent=data.templates.find(r=>r.id===s.value)?.description||'可先选择一种方法；小说事实与分镜格式保持优先。';s.onchange=update;update();parent.append(detail);return s}
 async function desk(){await ready;const $=id=>document.getElementById(id);$('catalog-count').textContent=`22 种运镜 · ${data.templates.length} 个视频模板 · 12 种图片玩法 · 案例库 ${data.case_count} 条`;
   cameraEditor($('camera-editor'),{speed:'缓慢匀速',invariants:'人物外貌、服装与场景保持一致'},prompt=>$('camera-output').value=prompt);
   const save=(name,text)=>{const u=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'})),a=node('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
   for(const kind of ['templates','recipes']){const box=$(kind),picker=label(box,kind==='templates'?'选择视频方法':'选择图片玩法',select(data[kind]));const info=node('p'),details=node('pre');box.append(info,details);const topic=input(box,kind==='templates'?'视频主题':'本次编辑目标','',true),extra=input(box,'补充要求（时长、画幅、路线或文字内容）','');const keep=kind==='recipes'?input(box,'必须保留','人物身份、未指定修改的物体与构图'):null;
     const out=input(box,'可编辑简报','',true);out.style.minHeight='220px';const build=node('button','生成创作简报'),copy=node('button','复制简报'),download=node('button','下载简报'),status=node('p');status.setAttribute('role','status');
     const update=()=>{const row=data[kind].find(r=>r.id===picker.value);info.textContent=row.description||('需要参考：'+row.references);details.textContent=kind==='templates'?row.structure.join('\n'):row.instruction;out.value=''};picker.onchange=update;update();
     build.onclick=async()=>{try{out.value=(await api('/api/director/brief',{kind,id:picker.value,subject:topic.value,extra:extra.value,keep:keep?.value||''})).prompt;status.textContent='简报已生成，可修改后复制或下载。'}catch(e){status.textContent=e.message}};
     copy.onclick=async()=>{try{if(!out.value)throw Error('请先生成简报');await navigator.clipboard.writeText(out.value);status.textContent='已复制'}catch(e){status.textContent=e.message}};download.onclick=()=>{if(out.value)save(kind+'-brief.txt',out.value);else status.textContent='请先生成简报'};box.append(build,copy,download,status);
     if(kind==='templates'){const use=node('button','在小说编剧中使用此方法');use.onclick=()=>{sessionStorage.setItem('director-method',picker.value);location.href='/novel'};box.append(use)}
   }
   $('send-motion').onclick=()=>{if(!$('camera-output').value){$('director-status').textContent='请先生成镜头提示词';return}sessionStorage.setItem('director-motion',$('camera-output').value);location.href='/motion'};
   $('copy-camera').onclick=async()=>{try{if(!$('camera-output').value)throw Error('请先生成镜头提示词');await navigator.clipboard.writeText($('camera-output').value);$('director-status').textContent='已复制'}catch(e){$('director-status').textContent=e.message}};
 }
 return {ready,mountScene,methodSelect,desk};
})();
