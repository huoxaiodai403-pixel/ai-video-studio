(() => {
  'use strict';
  const buttons = [...document.querySelectorAll('[data-flow-filter]')];
  const cards = [...document.querySelectorAll('[data-flow-category]')];
  const status = document.getElementById('workflow-filter-status');
  if (!status || !buttons.length) return;

  function select(filter, remember = false) {
    const selected = buttons.find(button => button.dataset.flowFilter === filter) || buttons[0];
    filter = selected.dataset.flowFilter;
    for (const button of buttons) button.setAttribute('aria-pressed', String(button === selected));
    let visible = 0;
    for (const card of cards) {
      card.hidden = filter !== 'all' && card.dataset.flowCategory !== filter;
      if (!card.hidden) visible++;
    }
    status.textContent = visible + ' 条工作流 · ' + selected.textContent;
    if (remember) {
      const url = new URL(location.href);
      if (filter === 'all') url.searchParams.delete('category');
      else url.searchParams.set('category', filter);
      url.hash = '';
      history.replaceState(null, '', url.pathname + url.search);
    }
  }

  for (const button of buttons) button.addEventListener('click', () => select(button.dataset.flowFilter, true));
  const target = cards.find(card => '#' + card.id === location.hash);
  const initial = new URLSearchParams(location.search).get('category') || target?.dataset.flowCategory || 'all';
  select(initial);
})();
