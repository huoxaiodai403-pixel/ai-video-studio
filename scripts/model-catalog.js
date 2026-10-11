/* The resource library and local settings use the same read-only inventory. */
window.ModelCatalog = (() => {
  'use strict';
  const node = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; };
  const descriptions = {
    'flux2-klein-4b':'快速生图和参考图编辑，适合反复调整人物与场景。',
    'qwen-image-2512':'从文本描述创作插画与场景。',
    'wan2.2-a14b':'从首帧生成动态镜头，适合较复杂的主体动作。',
    'wan2.2-5b':'生成短镜头，先试动作和镜头构图。',
    'ace-step-1.5':'生成背景音乐，试听后作为作品配乐。',
    'stable-audio-3-sfx':'生成环境声和短音效，当前工作流使用 CPU。'
  };
  const category = model => ({'图像生成':'image','视频生成':'motion','音乐与音效':'music','编剧与分镜':'text'})[model.group] || (['asr_dir','align_dir'].includes(model.id) ? 'text' : 'voice');
  function mount({hostId, statusId, refreshId, optionalGroups = false}) {
    const host = document.getElementById(hostId), status = document.getElementById(statusId), refresh = document.getElementById(refreshId);
    const search = document.getElementById('model-search'), availability = document.getElementById('model-availability'), count = document.getElementById('model-result-count');
    let models = [], selected = 'all', loading = false, loaded = false;
    const expanded = new Set();
    function card(model) {
      const item = node('article', undefined, 'model-card'); item.dataset.modelId = model.id;
      item.append(node('span', model.status || (model.ready ? model.system ? '系统语音可用' : '文件齐全 · 待试运行' : '待准备'), 'status-pill' + (model.ready ? ' success' : '')));
      item.append(node('h3', model.name), node('p', descriptions[model.id] || model.description, 'model-description'));
      item.append(node('p', model.cpu === true ? 'CPU 可运行' : model.cpu === false ? '使用显卡推理' : '按所选模型准备环境', 'field-help'));
      if (model.bytes) item.append(node('p', `已检测文件 ${(model.bytes / 1024 ** 3).toFixed(2)} GB`, 'field-help'));
      if (model.details?.length) {
        const details = node('details'), list = node('ul'); details.append(node('summary', '组件与安装状态'));
        for (const text of model.details) list.append(node('li', text));
        details.append(list); item.append(details);
      }
      const actions = node('div', undefined, 'model-actions'), use = node('a', model.ready ? '进入创作 →' : '查看准备方法 →', model.ready ? 'button secondary' : 'model-guide');
      let action = model.action;
      if (model.group === '图像生成') action = '/image?' + new URLSearchParams({engine:model.id, backend:'local'});
      use.href = model.ready ? action : '/plan'; actions.append(use);
      if (model.ready && !model.system) { const manage = node('a', '运行参数'); manage.href = '/runtime-settings'; actions.append(manage); }
      item.append(actions); return item;
    }
    function render() {
      host.replaceChildren();
      const query = search.value.trim().toLocaleLowerCase(), state = availability.value;
      host.classList.toggle('model-resource-grid', !optionalGroups || Boolean(query) || selected !== 'all' || state !== 'all');
      const filtered = models.filter(model => (selected === 'all' || category(model) === selected) && (state === 'all' || model.ready === (state === 'ready')) && (!query || [model.name, model.description, model.id].join(' ').toLocaleLowerCase().includes(query)));
      count.textContent = `${filtered.length} 项符合当前条件`;
      if (!filtered.length) { const empty = node('div', undefined, 'model-empty'); empty.append(node('h2', '没有匹配的能力'), node('p', '调整关键词或状态筛选，查看其他可选能力。')); host.append(empty); return; }
      if (!optionalGroups || query || selected !== 'all' || state !== 'all') { for (const model of filtered) host.append(card(model)); return; }
      const ready = filtered.filter(model => model.ready);
      if (ready.length) {
        const section = node('section', undefined, 'model-ready'), grid = node('div', undefined, 'model-cards');
        section.append(node('h2', '当前可用的能力')); for (const model of ready) grid.append(card(model));
        section.append(grid); host.append(section);
      }
      for (const group of [...new Set(filtered.filter(model => !model.ready).map(model => model.group))]) {
        const remaining = filtered.filter(model => !model.ready && model.group === group), detail = node('details', undefined, 'model-optional');
        detail.open = expanded.has(group);
        const summary = node('summary'), label = node('span', group), note = node('span', `${remaining.length} 项可选 · 按需准备`, 'small'); summary.append(label, note);
        const grid = node('div', undefined, 'model-cards'); for (const model of remaining) grid.append(card(model));
        detail.append(summary, grid); detail.addEventListener('toggle', () => { if (detail.open) expanded.add(group); else expanded.delete(group); }); host.append(detail);
      }
    }
    search.addEventListener('input', () => { if (loaded) render(); }); availability.addEventListener('change', () => { if (loaded) render(); });
    document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
      selected = button.dataset.category;
      document.querySelectorAll('[data-category]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      if (loaded) render();
    }));
    async function load() {
      if (loading) return; const restoreFocus = document.activeElement === refresh;
      loading = true; refresh.disabled = true; refresh.setAttribute('aria-busy','true'); status.classList.remove('error');
      status.textContent = '正在读取本机能力…'; host.setAttribute('aria-busy', 'true');
      try {
        const response = await fetch('/api/local-models', {signal:AbortSignal.timeout(20000)}), result = await response.json();
        if (!response.ok || !Array.isArray(result.models)) throw Error(result.error || '返回的能力清单无法读取');
        models = result.models.sort((a,b) => Number(b.ready)-Number(a.ready)); loaded = true;
        status.textContent = `${models.filter(model => model.ready).length} 项可用 · ${models.length} 项可选能力`; render();
      } catch (error) {
        status.classList.add('error'); status.textContent = '读取失败：' + error.message + (loaded ? '。仍显示上次结果，可刷新重试。' : '。请刷新重试。');
        if (!loaded) { host.replaceChildren(); count.textContent = '尚未取得能力清单'; }
      } finally {
        loading = false; refresh.disabled = false; refresh.setAttribute('aria-busy','false'); host.setAttribute('aria-busy', 'false');
        if (restoreFocus && document.activeElement === document.body) refresh.focus({preventScroll:true});
      }
    }
    refresh.addEventListener('click', load); load();
  }
  return {mount};
})();
