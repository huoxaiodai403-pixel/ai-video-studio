/* Opt-in behavior for shared components; no page data or task handlers. */
(()=>{
 'use strict';
 function keepFocusedFieldVisible(body){
  const field=document.activeElement;
  if(!body.closest('dialog[open]')||!body.contains(field)||!body.clientHeight)return;
  const viewport=body.getBoundingClientRect(),rect=field.getBoundingClientRect();
  const padding=parseFloat(getComputedStyle(body).scrollPaddingTop)||0;
  const top=viewport.top+body.clientTop+padding,bottom=viewport.top+body.clientTop+body.clientHeight-padding;
  const offset=rect.top<top||rect.height>bottom-top?rect.top-top:rect.bottom>bottom?rect.bottom-bottom:0;
  if(Math.abs(offset)>1)body.scrollBy({top:offset,behavior:'instant'});
 }
 const observer=new ResizeObserver(entries=>{
  for(const {target} of entries)keepFocusedFieldVisible(target);
 });
 for(const body of document.querySelectorAll('.form-dialog .dialog-body'))observer.observe(body);
})();
