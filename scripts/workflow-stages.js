/* Small, page-owned stages. The editor remains responsible for its data. */
(()=>{
 'use strict';
 window.WorkflowStages=function({root=document.querySelector('main'),onchange=()=>{}}={}){
  const buttons=[...root.querySelectorAll('[data-workflow-step]')];
  const panels=buttons.map(button=>document.getElementById(button.dataset.workflowStep));
  let current=buttons[0]?.dataset.workflowStep;
  function show(id,{focus=false,notify=true}={}){
   const index=buttons.findIndex(button=>button.dataset.workflowStep===id);if(index<0)return;
   current=id;buttons.forEach((button,i)=>{button.setAttribute('aria-current',i===index?'step':'false');button.setAttribute('aria-controls',panels[i].id);panels[i].hidden=i!==index});
   if(focus){const heading=panels[index].querySelector('h2');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true})}panels[index].scrollIntoView({block:'start',behavior:'instant'})}
   if(notify)onchange(id);
  }
  function reveal(control){if(!control)return;const panel=panels.find(item=>item.contains(control));if(panel)show(panel.id);for(let parent=control.parentElement;parent&&parent!==root;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;control.focus();control.scrollIntoView({block:'center',behavior:'instant'})}
  buttons.forEach((button,index)=>{button.type='button';button.addEventListener('click',()=>show(button.dataset.workflowStep));button.addEventListener('keydown',event=>{if(event.altKey||event.ctrlKey||event.metaKey)return;const offset={ArrowLeft:-1,ArrowRight:1}[event.key];const target=event.key==='Home'?0:event.key==='End'?buttons.length-1:offset===undefined?null:(index+offset+buttons.length)%buttons.length;if(target!==null){event.preventDefault();show(buttons[target].dataset.workflowStep);buttons[target].focus()}})});
  root.addEventListener('keydown',event=>{if(event.key!=='Escape')return;const details=event.target.closest('details[open]');if(details&&root.contains(details)){event.preventDefault();event.stopPropagation();details.open=false;details.querySelector('summary')?.focus()}});
  root.addEventListener('invalid',event=>reveal(event.target),true);
  show(current,{notify:false});
  return{show,reveal,get current(){return current},validate(scope=root){for(const control of scope.querySelectorAll('input,textarea,select'))if(!control.disabled&&control.willValidate&&!control.checkValidity()){reveal(control);control.reportValidity();return false}return true}};
 };
})();
