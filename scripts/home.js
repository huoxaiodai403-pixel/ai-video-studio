(() => {
  'use strict';
  const button = document.getElementById('refresh-overview');
  const status = document.getElementById('task-overview-status');
  const list = document.getElementById('recent-products');
  const empty = document.getElementById('recent-empty');
  if (!button || !status || !list || !empty) return;
  const emptyTitle = document.getElementById('recent-empty-title');
  const emptyDescription = document.getElementById('recent-empty-description');
  const emptyAction = document.getElementById('recent-empty-action');
  const cacheKey = 'studio-home-recent-v1';
  const recentLimit = 3;
  const editorParameters = {'/generation':['plan', 'id'], '/whiteboard':['project'], '/investigation':['project'], '/novel':['draft'], '/production':['project']};
  if (document.documentElement.dataset.studioEdition === 'friend') {
    for (const path of ['/investigation', '/novel', '/production']) delete editorParameters[path];
  }
  const states = {done:'已生成', queued:'排队中', running:'制作中', error:'需处理', draft:'草稿', preview:'样片'};
  const workflows = {image:'图像', motion:'短镜头', generation:'生成工坊', whiteboard:'手绘白板', investigation:'调查长片', video:'视频制作', enhance:'视频增强', speech:'配音', music:'配乐', sfx:'音效', asr:'字幕', story:'编剧'};
  let pending = false;
  let loaded = false;
  let lastRead = 0;
  let signature = '';

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function localUrl(value) {
    if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return null;
    try {
      const url = new URL(value, location.origin);
      return url.origin === location.origin ? url.pathname + url.search + url.hash : null;
    } catch (_) { return null; }
  }
  function editor(item) {
    for (const value of [item.edit_url, item.source_url]) {
      const candidate = localUrl(value);
      if (!candidate) continue;
      const url = new URL(candidate, location.origin);
      const parameters = editorParameters[url.pathname];
      const parameter = parameters?.find(key => url.searchParams.get(key));
      if (parameter) return {url:candidate, identity:url.pathname + '?' + parameters[0] + '=' + encodeURIComponent(url.searchParams.get(parameter))};
    }
    return null;
  }
  function editorUrl(item) {
    return editor(item)?.url || null;
  }
  function dateText(value) {
    if (!value) return '时间未记录';
    const date = new Date(typeof value === 'number' ? value * 1000 : value);
    return Number.isNaN(date.valueOf()) ? '时间未记录' : date.toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
  }
  function recentProjects(items) {
    const stamp = item => {
      const value = item.created_at;
      if (!value) return 0;
      const time = new Date(typeof value === 'number' ? value * 1000 : value).valueOf();
      return Number.isNaN(time) ? 0 : time;
    };
    const projects = new Map();
    for (const item of [...items].sort((a, b) => stamp(b) - stamp(a))) {
      // Group only a resumable project identity, never a general tool URL.
      const key = editor(item)?.identity || 'item:' + item.id;
      if (!projects.has(key)) projects.set(key, item);
    }
    return [...projects.values()].slice(0, recentLimit);
  }
  function displayItems(items) {
    const fields = ['id','title','project_id','status','workflow','created_at','thumbnail_url','source_url','edit_url','error'];
    return items.map(item => Object.fromEntries(fields.map(key => [key, item[key] ?? null])));
  }
  function validItems(items) {
    return Array.isArray(items) && items.every(item => item && typeof item.id === 'string' && item.id.length > 0);
  }
  function readTime() {
    return new Date(lastRead).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit', hour12:false});
  }
  function showEmpty(failed = false) {
    list.hidden = true;
    empty.hidden = false;
    emptyTitle.textContent = failed ? '工程记录暂时无法读取' : '还没有工程记录';
    emptyDescription.textContent = failed ? '可以重试读取，或从上方开始新的创作。' : '从一个主题、故事或参考素材开始，保存后就能在这里继续。';
    emptyAction.textContent = failed ? '打开作品库 →' : '开始第一份创作 →';
    emptyAction.href = failed ? '/library' : '/generation';
  }
  function showItems(items) {
    const nextSignature = JSON.stringify(items);
    if (signature !== nextSignature) {
      list.replaceChildren(...items.map(render));
      signature = nextSignature;
    }
    if (items.length) { list.hidden = false; empty.hidden = true; }
    else showEmpty();
  }
  function restoreCache() {
    try {
      const cached = JSON.parse(sessionStorage.getItem(cacheKey) || 'null');
      if (!cached || cached.version !== 1 || !validItems(cached.items) || cached.items.length > recentLimit || !Number.isFinite(cached.readAt) || cached.readAt <= 0) return;
      showItems(displayItems(recentProjects(cached.items)));
      lastRead = cached.readAt;
      loaded = true;
    } catch (_) { /* A storage restriction must not prevent a live library read. */ }
  }
  function saveCache(items) {
    try { sessionStorage.setItem(cacheKey, JSON.stringify({version:1, readAt:lastRead, items})); }
    catch (_) { /* The current page remains usable when session storage is unavailable. */ }
  }
  function render(item) {
    const row = element('li', null, 'dashboard-project-row');
    const thumb = localUrl(item.thumbnail_url);
    const visual = element('div', null, 'dashboard-product-visual');
    if (thumb) {
      const image = element('img');
      image.src = thumb;
      image.alt = '';
      image.loading = 'lazy';
      image.width = 48;
      image.height = 48;
      image.addEventListener('error', () => { visual.replaceChildren(element('span', workflows[item.workflow] || '工程')); }, {once:true});
      visual.append(image);
    } else {
      visual.append(element('span', workflows[item.workflow] || '工程'));
    }
    const body = element('div', null, 'dashboard-product-body');
    const heading = element('h3');
    const detail = element('a', item.title || item.project_id || '未命名工程');
    detail.href = '/library?item=' + encodeURIComponent(item.id);
    detail.title = item.title || item.project_id || '未命名工程';
    heading.append(detail);
    body.append(heading);
    const metadata = element('p', (workflows[item.workflow] || '工程') + ' · ' + dateText(item.created_at), 'dashboard-product-meta');
    if (item.error) {
      metadata.append(element('span', ' · ' + item.error, 'dashboard-product-error'));
      metadata.title = item.error;
    }
    body.append(metadata);
    const state = element('span', states[item.status] || '状态待确认', 'dashboard-state');
    state.dataset.state = Object.hasOwn(states, item.status) ? item.status : 'unknown';
    if (item.error) state.title = item.error;
    const actions = element('div', null, 'dashboard-product-actions');
    actions.append(state);
    const edit = editorUrl(item);
    const link = element('a', edit ? '继续编辑 →' : '查看作品 →');
    link.href = edit || detail.href;
    actions.append(link);
    row.append(visual, body, actions);
    return row;
  }
  async function refresh() {
    if (pending) return;
    pending = true;
    button.disabled = true;
    button.textContent = '刷新中…';
    list.setAttribute('aria-busy', 'true');
    status.classList.remove('is-error');
    status.textContent = loaded ? '显示本次会话暂存记录（' + readTime() + ' 读取）· 正在刷新…' : '正在读取工程记录…';
    try {
      const response = await fetch('/api/library?view=products&status=all', {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (!validItems(data.items)) throw new Error('工程数据格式不正确');
      const recent = displayItems(recentProjects(data.items));
      showItems(recent);
      loaded = true;
      lastRead = Date.now();
      saveCache(recent);
      status.textContent = (recent.length ? '最近 ' + recent.length + ' 个工程' : '暂无工程记录') + ' · 已更新 ' + readTime();
    } catch (error) {
      status.classList.add('is-error');
      if (!loaded) { list.replaceChildren(); showEmpty(true); }
      status.textContent = '刷新失败：' + error.message + '。' + (loaded ? '保留 ' + readTime() + ' 读取的暂存记录，可重试。' : '请重试读取。');
    } finally {
      pending = false;
      button.disabled = false;
      button.textContent = '刷新';
      list.setAttribute('aria-busy', 'false');
    }
  }
  button.addEventListener('click', refresh);
  restoreCache();
  refresh();
})();
