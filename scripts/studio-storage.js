/* Browser drafts belong to a checkout, even when another checkout reuses its port. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; return; }
  const scope = root.document.documentElement.dataset.studioStorageScope;
  root.StudioStorage = {
    local: api.scoped(() => root.localStorage, scope),
    session: api.scoped(() => root.sessionStorage, scope)
  };
  root.document.addEventListener('DOMContentLoaded', () => {
    let legacy;
    try { legacy = {local: api.legacy(root.localStorage), session: api.legacy(root.sessionStorage)}; }
    catch { return; } // The editors report storage errors without losing in-page input.
    if (!legacy.local.length && !legacy.session.length) return;
    const main = root.document.querySelector('main');
    if (!main) return;
    const section = root.document.createElement('details');
    section.className = 'panel';
    const summary = root.document.createElement('summary');
    summary.textContent = '旧浏览器草稿备份';
    const text = root.document.createElement('p');
    text.textContent = '发现未标明工作台归属的旧草稿，已保留原文，没有自动带入。已保存的工程请从“我的作品”继续；未保存内容可下载备份后核对。';
    const button = root.document.createElement('button');
    button.type = 'button'; button.textContent = '下载旧草稿备份';
    button.onclick = () => {
      try {
        const data = {schema: 1, scope, local: api.legacy(root.localStorage), session: api.legacy(root.sessionStorage)};
        const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
        const link = root.document.createElement('a');
        link.href = url; link.download = 'studio-legacy-browser-drafts.json'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch { text.textContent = '浏览器备份读取失败，原草稿未改动；请保留此浏览器，稍后重试。'; }
    };
    section.append(summary, text, button); main.append(section);
  });
})(typeof globalThis === 'object' ? globalThis : this, () => {
  'use strict';
  function scoped(resolve, scope) {
    const prefix = /^[a-f0-9]{24}$/.test(scope || '') ? `avs:${scope}:` : null;
    function storage() { if (!prefix) throw Error('工作台草稿身份缺失，请重新打开页面。'); return resolve(); }
    function keys() {
      const target = storage(), result = [];
      for (let i = 0; i < target.length; i++) { const key = target.key(i); if (key?.startsWith(prefix)) result.push(key.slice(prefix.length)); }
      return result;
    }
    return {
      getItem: key => storage().getItem(prefix + key),
      setItem: (key, value) => storage().setItem(prefix + key, value),
      removeItem: key => storage().removeItem(prefix + key),
      key: index => keys()[index] ?? null,
      get length() { return keys().length; },
      matches: (event, key) => Boolean(prefix && (event.key === null || event.key === prefix + key))
    };
  }
  function legacy(storage) {
    const result = [];
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (/^(ai-video-|ai-studio-|studio-|director-|voice-library-)/.test(key || '')) result.push({key, raw: storage.getItem(key)});
    }
    return result;
  }
  return {scoped, legacy};
});
