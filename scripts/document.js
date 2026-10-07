document.getElementById('print-doc').onclick=()=>window.print();
fetch('/api/services').then(r=>r.json()).then(d=>{document.getElementById('services').textContent=`千问生图：${d.comfyui.ready?'就绪':'未启动'} · 配音：${d.tts.ready?'就绪':'未启动'}`}).catch(()=>{document.getElementById('services').textContent='服务状态暂不可用'});
