/* Registered reference images; ordered IDs are sent to the local image API. */
window.ImageReferences = (() => {
  const storageKey = 'ai-video-image-references-v1';
  let references = [], selected = [], loaded = false, loading;
  const el = id => document.getElementById(id);
  try { const saved = JSON.parse(localStorage.getItem(storageKey) || '[]'); if (Array.isArray(saved)) selected = [...new Set(saved.filter(id => typeof id === 'string'))].slice(0, 4); } catch (_) {}
  const message = text => { el('reference-status').textContent = text; };
  const supported = () => el('backend').value === 'local' && document.querySelector('[data-group="image"][data-key="engine"]')?.value === 'flux2-klein-4b';
  function safePreview(value) { try { const url = new URL(value, location.origin); return url.origin === location.origin && (url.pathname.startsWith('/outputs/') || url.pathname === '/api/image-references/preview') ? url.href : ''; } catch (_) { return ''; } }
  function persist() { try { localStorage.setItem(storageKey, JSON.stringify(selected)); } catch (_) {} }
  function button(text, action, disabled = false) { const node = document.createElement('button'); node.type = 'button'; node.className = 'secondary'; node.textContent = text; node.disabled = disabled; node.onclick = action; return node; }
  function thumbnail(row) { const img = document.createElement('img'); img.src = safePreview(row.preview_url); img.alt = row.name; img.loading = 'lazy'; return img; }
  function select(id) { if (!supported()) return message('参考图编辑仅支持本地 FLUX.2 klein 4B；请先切换引擎。'); if (selected.includes(id)) return; if (selected.length >= 4) return message('最多选择 4 张参考图，请先移除一张。'); selected.push(id); persist(); render(); message('已加入本次参考图。顺序会保留到生成任务。'); }
  function render() {
    const allowed = supported();
    el('reference-mode').textContent = allowed ? '本次可使用 0–4 张参考图；不选图片时为文生图。图 1、图 2 的顺序与下面一致。' : '当前引擎不支持参考图输入。请切换到“本地模型 + FLUX.2 klein 4B”，或移除已选参考图后生成。';
    el('reference-upload').disabled = !allowed; el('reference-files').disabled = !allowed;
    el('reference-count').textContent = `${selected.length} / 4 张已选`;
    const picked = el('reference-selected'); picked.replaceChildren();
    selected.forEach((id, index) => {
      const row = references.find(item => item.id === id), card = document.createElement('div'); card.className = 'reference-card';
      const title = document.createElement('strong'); title.textContent = `图 ${index + 1} · ${row?.name || '参考图暂不可用'}`; card.append(title);
      if (row) { card.append(thumbnail(row)); const size = document.createElement('span'); size.className = 'small'; size.textContent = `${row.width} × ${row.height}`; card.append(size); }
      const actions = document.createElement('div'); actions.className = 'reference-actions';
      const move = delta => { [selected[index], selected[index + delta]] = [selected[index + delta], selected[index]]; persist(); render(); };
      actions.append(button('前移', () => move(-1), index === 0), button('后移', () => move(1), index === selected.length - 1), button('移除', () => { selected.splice(index, 1); persist(); render(); })); card.append(actions); picked.append(card);
    });
    if (!selected.length) { const empty = document.createElement('p'); empty.className = 'small'; empty.textContent = '尚未选择参考图。可上传角色、场景或物件，再从图库中选择。'; picked.append(empty); }
    const library = el('reference-library'); library.replaceChildren();
    for (const row of references) { const card = document.createElement('div'); card.className = 'reference-card'; const name = document.createElement('span'); name.textContent = row.name; card.append(thumbnail(row), name, button(selected.includes(row.id) ? '已选择' : '用于本次生成', () => select(row.id), !allowed || selected.includes(row.id))); library.append(card); }
    if (loaded && !references.length) library.textContent = '图库为空，上传图片或将已完成的生成图存入图库。';
  }
  async function refresh() { if (loading) return loading; loading = Creation.api('/api/image-references').then(data => { references = data.references; loaded = true; render(); return data; }).catch(error => { message('参考图库读取失败：' + error.message); throw error; }).finally(() => { loading = null; }); return loading; }
  async function upload() {
    const files = [...el('reference-files').files]; if (!supported()) return message('请先选择本地 FLUX.2 klein 4B。'); if (!files.length) return message('请先选择 PNG、JPEG 或 WebP 图片。');
    el('reference-upload').disabled = true;
    try { for (let index = 0; index < files.length; index++) { const file = files[index]; if (file.size > 12 * 1024 * 1024) throw Error(file.name + ' 超过 12 MB'); if (!/\.(png|jpe?g|webp)$/i.test(file.name)) throw Error(file.name + ' 不是支持的图片格式'); message(`正在登记 ${index + 1} / ${files.length}：${file.name}`); const base64 = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(Error('读取图片失败')); reader.readAsDataURL(file); }); const data = await Creation.api('/api/image-references', { name: file.name, base64 }); references = data.references; loaded = true; if (selected.length < 4 && !selected.includes(data.reference.id)) selected.push(data.reference.id); persist(); render(); } el('reference-files').value = ''; message('图片已存入图库。已选图最多 4 张，其余可在图库中复用。'); } catch (error) { message('上传未完成：' + error.message + '。此前成功登记的图片已保留。'); } finally { render(); }
  }
  function referenceIds() { if (selected.length && !supported()) throw Error('已选参考图仅支持本地 FLUX.2 klein 4B。请切换引擎或移除参考图；不会忽略图片继续生成。'); if (selected.length && !loaded) throw Error('参考图库尚未载入，请刷新图库后生成。'); if (selected.some(id => !references.some(row => row.id === id))) throw Error('已选参考图已失效，请移除后重新选择。'); return [...selected]; }
  async function saveJob(jobId) { const data = await Creation.api('/api/image-references', { job_id: jobId }); references = data.references; loaded = true; render(); message('生成图已存入参考图库，可在后续镜头中选择并复用。'); return data.reference; }
  el('reference-upload').onclick = upload;
  el('reference-refresh').onclick = () => refresh().then(() => message('图库已刷新。')).catch(() => {});
  el('reference-clear').onclick = () => { selected = []; persist(); render(); message('已清空本次选择，图库文件仍保留。'); };
  el('backend').addEventListener('change', render);
  document.addEventListener('creation-engine-changed', render); document.addEventListener('creation-settings-changed', render);
  async function applyNavigation() {
    const params = new URLSearchParams(location.search), reference = params.get('reference'), requestedEngine = params.get('engine');
    if (reference === null && requestedEngine === null) return;
    try {
      if (reference !== null && (!/^img-[a-f0-9]{24}$/.test(reference) || !references.some(row => row.id === reference))) throw Error('指定参考图不存在或已失效，请从图库重新选择。');
      const engine = reference !== null ? 'flux2-klein-4b' : requestedEngine;
      if (!(Creation.inventory.image_engines || []).some(row => row.id === engine)) throw Error('指定图像引擎不存在，请从模型库重新选择。');
      const control = document.querySelector('[data-group="image"][data-key="engine"]');
      if (!control) throw Error('图像参数尚未就绪，请刷新页面。');
      if (reference !== null) {
        // Preserve the previous selection before replacing it with the explicitly requested image.
        localStorage.setItem(storageKey + '-before-navigation', JSON.stringify({saved_at:new Date().toISOString(),selected}));
        selected = [reference]; persist();
      }
      el('backend').value = 'local'; el('backend').dispatchEvent(new Event('change', {bubbles:true}));
      control.value = engine; control.dispatchEvent(new Event('change', {bubbles:true}));
      render();
      message(reference !== null ? `已载入参考图「${references.find(row => row.id === reference).name}」，本次使用本地 FLUX.2 klein 4B；未修改全局默认参数。` : '已选择本次本地图像引擎；未修改全局默认参数。');
    } catch (error) { message('无法带入图库选择：' + error.message); }
  }
  const ready = Creation.ready.then(async () => { render(); await refresh(); await applyNavigation(); }); ready.catch(() => {});
  return { ready, referenceIds, refresh, saveJob, safePreview };
})();
