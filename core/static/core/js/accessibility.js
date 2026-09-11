document.addEventListener('DOMContentLoaded', function () {
  let active = null, returnFocus = null, inerted = [];
  const visible = el => Boolean(el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  const focusables = el => Array.from(el.querySelectorAll('a[href],button:not([disabled]),input:not([type="hidden"]):not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')).filter(visible);
  function check() {
    const next = Array.from(document.querySelectorAll('[data-a11y-dialog]')).filter(visible).pop() || null;
    if (next === active) return;
    inerted.forEach(el => el.inert=false); inerted=[];
    if (!next) { active=null; if(returnFocus && returnFocus.isConnected) returnFocus.focus(); returnFocus=null; return; }
    returnFocus = document.activeElement; active=next;
    let branch=next;
    while(branch.parentElement && branch.parentElement!==document.documentElement) {
      Array.from(branch.parentElement.children).forEach(el => { if(el!==branch && !el.inert && !['SCRIPT','STYLE','LINK'].includes(el.tagName)){el.inert=true;inerted.push(el);} });
      if(branch.parentElement===document.body) break;
      branch=branch.parentElement;
    }
    (focusables(next)[0] || next).focus();
  }
  new MutationObserver(check).observe(document.body,{subtree:true,attributes:true,attributeFilter:['style','class','hidden']});
  document.addEventListener('keydown', function(event){
    if(!active || event.key!=='Tab') return;
    const nodes=focusables(active); if(!nodes.length){event.preventDefault();active.focus();return;}
    const first=nodes[0],last=nodes[nodes.length-1];
    if(event.shiftKey && (document.activeElement===first || !active.contains(document.activeElement))){event.preventDefault();last.focus();}
    else if(!event.shiftKey && (document.activeElement===last || !active.contains(document.activeElement))){event.preventDefault();first.focus();}
  });
});
