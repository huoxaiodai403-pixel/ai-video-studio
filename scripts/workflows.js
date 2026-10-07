(()=>{
 const buttons=[...document.querySelectorAll('[data-flow-filter]')],cards=[...document.querySelectorAll('[data-flow-category]')],status=document.getElementById('workflow-filter-status');
 for(const button of buttons)button.addEventListener('click',()=>{const filter=button.dataset.flowFilter;for(const other of buttons)other.setAttribute('aria-pressed',String(other===button));let visible=0;for(const card of cards){card.hidden=filter!=='all'&&card.dataset.flowCategory!==filter;if(!card.hidden)visible++}status.textContent=`${visible} 条工作流 · ${button.textContent}`});
})();
