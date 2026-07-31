(function(){
var editing=null,origText='',cancelEdit=false,dragging=false,dragFrom=-1,downY=0,downIdx=-1,moved=false,dropLine=null;
var elDrag=null,elResize=null,rdir='',selEl=null,curBp='d',gx=0,gy=0,sx=0,sy=0,sw=0,sh=0,gg=null,pid=0;
var themeMode=false; // theme drawer open (Form mode only) — clicks probe a region instead of selecting
var restrictMode=false; // Form mode: keep hover+click-select for the form<->preview sync, but
                         // suppress canvas-only affordances (inline edit, drag-reorder, element drag/resize)
// Region -> selector map for theme highlight-sync. Kept in lockstep with the
// ThemeRegion union in useThemeBridge.ts.
var THEME_REGION_SEL={
  brand:'.cz-btn--solid,.cz-brand',
  accent:'.cz-btn--solid,.cz-brand,.cz-stat__num',
  headingFont:'h1,h2,h3',
  bodyFont:'body',
  radius:'.cz-btn,.cz-card,.cz-plan,.cz-quote,.cz-bento-cell',
  mode:'body',
  container:'.cz-wrap',
  gutter:'.cz-wrap',
  sectionPad:'main>section:first-of-type,main>[data-cz-block]:first-of-type',
  gap:'.cz-cards,.cz-plans,.cz-grid-img,.cz-quote-grid',
  cardPad:'.cz-card,.cz-plan,.cz-quote,.cz-bento-cell',
  cardBorder:'.cz-card,.cz-plan,.cz-quote,.cz-bento-cell',
  headerPad:'.cz-header',
  brandSize:'.cz-header',
  footerPad:'.cz-footer'
};
var THEME_HL_MAX=6;
function clearThemeHl(){var hs=document.querySelectorAll('.cz-theme-hl');for(var i=0;i<hs.length;i++)hs[i].classList.remove('cz-theme-hl');}
function highlightTheme(region){
  clearThemeHl();
  var sel=THEME_REGION_SEL[region];if(!sel)return;
  var els=[].slice.call(document.querySelectorAll(sel)).slice(0,THEME_HL_MAX);
  for(var i=0;i<els.length;i++)els[i].classList.add('cz-theme-hl');
  // Scroll the first match into view — but never for whole-page targets (body),
  // where "scrolling into view" would just yank the preview to the top.
  if(els[0]&&els[0]!==document.body&&els[0].scrollIntoView)els[0].scrollIntoView({block:'center',behavior:'smooth'});
}
// Reverse direction: clicking a page element while the theme drawer is open
// probes which region governs it, so the parent can jump the drawer there.
// Checked most-specific first — broad containers (body) would match everything.
var THEME_PROBE_ORDER=['brand','headingFont','cardPad','headerPad','footerPad','gap'];
function probeThemeRegion(el){
  for(var k=0;k<THEME_PROBE_ORDER.length;k++){
    var region=THEME_PROBE_ORDER[k];
    var matches=document.querySelectorAll(THEME_REGION_SEL[region]);
    for(var i=0;i<matches.length;i++){if(matches[i]===el||matches[i].contains(el)){post({type:'cz-theme-probe',region:region});return;}}
  }
  var inSection=el.closest&&el.closest('[data-cz-block]');
  post({type:'cz-theme-probe',region:inSection?'sectionPad':'bodyFont'});
}
function post(m){try{window.parent.postMessage(m,'*');}catch(e){}}
// Char-offset of (node,offset) within root's flattened textContent — walks text
// nodes in document order so a selection inside nested markup (rare in a field,
// but e.g. a <b> wrapper) still resolves to the plain-text offset the server's
// field string uses.
function textOffset(root,node,offset){
  var walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,null);
  var total=0,n;
  while((n=walker.nextNode())){if(n===node)return total+offset;total+=n.textContent.length;}
  return total;
}
// A live (non-collapsed) text selection wholly inside `el`, or null. Verifies
// the extracted substring matches root text at the computed offset — Selection
// API + TreeWalker can disagree on edge cases (BR, collapsed whitespace); when
// they do, degrade to whole-field selection rather than ship a wrong range.
function detectRange(el){
  var sel=window.getSelection&&window.getSelection();
  if(!sel||!sel.rangeCount||sel.isCollapsed)return null;
  var range=sel.getRangeAt(0);
  if(!el.contains(range.startContainer)||!el.contains(range.endContainer))return null;
  var raw=sel.toString();
  if(!raw)return null;
  var start=textOffset(el,range.startContainer,range.startOffset);
  var full=el.textContent||'';
  if(full.slice(start,start+raw.length)!==raw)return null;
  // Clamp text+end TOGETHER — reporting text.slice(0,300) but end=start+raw.length
  // (the UNCLAMPED length) desyncs them: the server's exact-match anchor check
  // (`actual[start:end] == text`) then fails on length alone for anything over
  // 300 chars and silently falls back to a re-anchor/stale read instead.
  var txt=raw.length>300?raw.slice(0,300):raw;
  return {start:start,end:start+txt.length,text:txt};
}
// Selection persistence across a collapsing click: a second click inside a
// field the user already range-selected collapses the browser Selection, and
// without this a naive re-check would downgrade to "whole field selected" —
// discarding the highlight the user is still looking at. Keyed per
// (block,field-or-element) so switching fields always starts fresh.
var lastRangeKey=null,lastRange=null;
function rangeKey(block,field,element){return block+'|'+(field||'')+'|'+(element||'');}
function detectRangeOrKeep(el,block,field,element){
  var key=rangeKey(block,field,element);
  var r=detectRange(el);
  if(r){lastRangeKey=key;lastRange=r;return r;}
  if(key===lastRangeKey&&lastRange)return lastRange;
  lastRangeKey=key;lastRange=null;
  return null;
}
// Shared by the click handler and the mouseup/selectionchange listeners below
// (Selection-API events fire on `document`, not the field — drag-select can
// end with the pointer outside the field, and keyboard shift+arrow selection
// never fires a click at all). Posts nothing when there's no live range AND
// no kept one — a plain collapsed click elsewhere is handled by the click
// listener itself, not this path.
function maybePostFieldSelection(el){
  if(!el||themeMode||editing)return;
  var block=el.closest&&el.closest('[data-cz-block]');if(!block)return;
  var i=parseInt(block.getAttribute('data-cz-block'),10);
  var isCanvasEl=el.classList&&el.classList.contains('cz-el');
  var kind=el.getAttribute('data-cz-kind')||'text';
  if(kind!=='text')return;
  if(isCanvasEl){
    var cid=el.getAttribute('data-cz-field');if(!cid)return;
    var cr=detectRangeOrKeep(el,i,null,cid);
    if(cr)postSelection(el,'text',i,null,cr.start,cr.end,cr.text,cid);
  } else {
    var field=el.getAttribute('data-cz-field');if(!field)return;
    var fr=detectRangeOrKeep(el,i,field,null);
    if(fr)postSelection(el,'text',i,field,fr.start,fr.end,fr.text);
  }
}
// Selection contract for Merlin (highlight-driven precision design): posted
// alongside the legacy cz-select on every field/element click, additive —
// cz-select still drives block highlight + the floating inspector anchor.
// `field` is a set_field-style dot path (see BLOCK_FIELDS server-side);
// `element` is a freeform-canvas element id (addressed via canvas_update, a
// different op entirely) — mutually exclusive, never both set.
function postSelection(el,kind,block,field,start,end,text,element){
  var r=el.getBoundingClientRect();
  post({type:'cz-selection',block:block,field:field||null,element:element||null,kind:kind,
        start:start,end:end,text:text,rect:{top:r.top,left:r.left,width:r.width,height:r.height}});
}
function blocks(){return [].slice.call(document.querySelectorAll('main>[data-cz-block]'));}
function blockEl(i){return document.querySelector('[data-cz-block="'+i+'"]');}
function idxOf(el){var b=el&&el.closest?el.closest('[data-cz-block]'):null;return b?parseInt(b.getAttribute('data-cz-block'),10):-1;}
function clearHandles(){var hs=document.querySelectorAll('.cz-cv-h');for(var i=0;i<hs.length;i++)hs[i].parentNode.removeChild(hs[i]);}
function addHandles(el){clearHandles();var ds=['nw','n','ne','e','se','s','sw','w'];for(var i=0;i<ds.length;i++){var h=document.createElement('div');h.className='cz-cv-h';h.setAttribute('data-dir',ds[i]);el.appendChild(h);}}
function clearSel(){var s=document.querySelectorAll('.cz-selected,.cz-el-sel');for(var i=0;i<s.length;i++)s[i].classList.remove('cz-selected','cz-el-sel');clearHandles();selEl=null;}
function highlight(i){clearSel();var el=blockEl(i);if(el)el.classList.add('cz-selected');}
function selectEl(el){clearSel();el.classList.add('cz-el-sel');selEl=el;addHandles(el);}
function postSelectEl(el){var r=el.getBoundingClientRect();post({type:'cz-select',block:idxOf(el),field:el.getAttribute('data-cz-id'),rect:{top:r.top,left:r.left,width:r.width,height:r.height}});}
function clamp(v,lo,hi){return Math.max(lo,Math.min(hi,v));}
function gridInfo(el){var w=el.closest&&el.closest('.cz-cv-wrap');if(!w)return null;var cs=getComputedStyle(w);var cols=parseInt(cs.getPropertyValue('--cv-cols'),10)||12;var rh=parseFloat(cs.getPropertyValue('--cv-rowh'))||24;return {cols:cols,rowH:rh,cellW:(w.clientWidth/cols)||1};}
function pos(el){var p=(curBp==='m')?'m':'d';return {x:parseInt(el.getAttribute('data-'+p+'x'),10)||0,y:parseInt(el.getAttribute('data-'+p+'y'),10)||0,w:parseInt(el.getAttribute('data-'+p+'w'),10)||1,h:parseInt(el.getAttribute('data-'+p+'h'),10)||1};}
function setPos(el,x,y,w,h){el.style.gridColumn=(x+1)+'/span '+w;el.style.gridRow=(y+1)+'/span '+h;var p=(curBp==='m')?'m':'d';el.setAttribute('data-'+p+'x',x);el.setAttribute('data-'+p+'y',y);el.setAttribute('data-'+p+'w',w);el.setAttribute('data-'+p+'h',h);}
document.addEventListener('mouseover',function(e){if(themeMode||editing||dragging||elDrag||elResize)return;var b=e.target.closest&&e.target.closest('[data-cz-block]');if(b)b.classList.add('cz-hover');});
document.addEventListener('mouseout',function(e){var b=e.target.closest&&e.target.closest('[data-cz-block]');if(b)b.classList.remove('cz-hover');});
document.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('a');if(a)e.preventDefault();
  if(editing&&editing.contains(e.target))return;
  if(moved){moved=false;return;}
  if(themeMode){probeThemeRegion(e.target);return;}
  var ce=e.target.closest&&e.target.closest('.cz-el');
  var b=e.target.closest&&e.target.closest('[data-cz-block]');if(!b)return;
  var i=parseInt(b.getAttribute('data-cz-block'),10);
  if(ce){
    if(ce!==selEl){selectEl(ce);postSelectEl(ce);}
    // A `.cz-el` is a freeform-canvas element: its `data-cz-field` carries the
    // element id (canvas_update's `el`), NOT a set_field dot path — post it as
    // `element`, not `field`, so the server doesn't try to resolve it as one.
    var cid=ce.getAttribute('data-cz-field');
    if(cid){
      var ck=ce.getAttribute('data-cz-kind')||'text';
      var cr=ck==='text'?detectRangeOrKeep(ce,i,null,cid):null;
      postSelection(ce,ck,i,null,cr?cr.start:null,cr?cr.end:null,cr?cr.text:(ce.textContent||'').slice(0,300),cid);
    }
    return;
  }
  var f=e.target.closest&&e.target.closest('[data-cz-field]');
  var r=b.getBoundingClientRect();
  highlight(i);
  post({type:'cz-select',block:i,field:f?f.getAttribute('data-cz-field'):undefined,rect:{top:r.top,left:r.left,width:r.width,height:r.height}});
  if(f){
    var fk=f.getAttribute('data-cz-kind')||'text';
    var fr=fk==='text'?detectRangeOrKeep(f,i,f.getAttribute('data-cz-field'),null):null;
    postSelection(f,fk,i,f.getAttribute('data-cz-field'),fr?fr.start:null,fr?fr.end:null,fr?fr.text:(f.textContent||'').slice(0,300));
  } else {
    postSelection(b,'element',i,null,null,null,null);
  }
},true);
// Range capture beyond a plain click: a drag-select that ends with the
// pointer outside the field (mouseup target != the field) never reaches the
// click handler's range check, and keyboard shift+arrow selection never
// fires a click at all. Debounced — selectionchange fires on every caret
// tick during a drag, and this only needs the settled result.
document.addEventListener('mouseup',function(e){
  var f=e.target.closest&&e.target.closest('[data-cz-field]');
  if(f)maybePostFieldSelection(f);
});
var _scTimer=null;
document.addEventListener('selectionchange',function(){
  clearTimeout(_scTimer);
  _scTimer=setTimeout(function(){
    var sel=window.getSelection&&window.getSelection();
    if(!sel||!sel.rangeCount||sel.isCollapsed)return;
    var node=sel.anchorNode;
    var el=node&&(node.nodeType===1?node:node.parentElement);
    var f=el&&el.closest&&el.closest('[data-cz-field]');
    if(f)maybePostFieldSelection(f);
  },120);
});
document.addEventListener('dblclick',function(e){
  if(themeMode||restrictMode)return;
  var f=e.target.closest&&e.target.closest('[data-cz-field]');if(!f)return;
  // Images (hero/split art, canvas image elements) must never become
  // contenteditable — typing into one posts cz-edit with the field's real
  // dot path and the typed TEXT as `value`, which useCanvasBridge.ts then
  // writes onto an image field, corrupting it with junk text. Buttons keep
  // inline label editing (pre-existing behavior for canvas buttons).
  if((f.getAttribute('data-cz-kind')||'text')==='image')return;
  e.preventDefault();
  if(editing&&editing!==f)editing.blur();
  clearHandles();
  editing=f;origText=f.innerText;cancelEdit=false;
  f.setAttribute('contenteditable','true');f.classList.add('cz-editing');
  post({type:'cz-editing-start'});f.focus();
});
document.addEventListener('keydown',function(e){
  if(!editing)return;
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();editing.blur();}
  else if(e.key==='Escape'){cancelEdit=true;editing.blur();}
});
document.addEventListener('blur',function(e){
  if(!editing||e.target!==editing)return;
  var f=editing;editing=null;
  f.removeAttribute('contenteditable');f.classList.remove('cz-editing');
  var i=idxOf(f),field=f.getAttribute('data-cz-field');
  if(cancelEdit){f.innerText=origText;cancelEdit=false;}
  else{var v=f.innerText.replace(/\s+$/,'');if(v!==origText)post({type:'cz-edit',block:i,field:field,value:v});}
  if(selEl===f)addHandles(f);
  post({type:'cz-editing-end'});
},true);
document.addEventListener('pointerdown',function(e){
  if(editing||themeMode||restrictMode)return;
  var h=e.target.closest&&e.target.closest('.cz-cv-h');
  if(h&&selEl){e.preventDefault();gg=gridInfo(selEl);if(!gg)return;elResize=selEl;rdir=h.getAttribute('data-dir');var p=pos(selEl);sx=p.x;sy=p.y;sw=p.w;sh=p.h;gx=e.clientX;gy=e.clientY;moved=false;downIdx=-1;dragging=false;pid=e.pointerId;try{selEl.setPointerCapture(pid);}catch(_){}return;}
  var ce=e.target.closest&&e.target.closest('.cz-el');
  if(ce){gg=gridInfo(ce);if(!gg)return;if(ce!==selEl){selectEl(ce);postSelectEl(ce);}elDrag=ce;var q=pos(ce);sx=q.x;sy=q.y;sw=q.w;sh=q.h;gx=e.clientX;gy=e.clientY;moved=false;downIdx=-1;dragging=false;pid=e.pointerId;try{ce.setPointerCapture(pid);}catch(_){}return;}
  var b=e.target.closest&&e.target.closest('[data-cz-block]');if(!b)return;
  downIdx=parseInt(b.getAttribute('data-cz-block'),10);downY=e.clientY;moved=false;dragFrom=downIdx;dragging=false;
});
function startedMove(e){if(moved)return true;if(Math.abs(e.clientX-gx)<4&&Math.abs(e.clientY-gy)<4)return false;moved=true;document.body.classList.add('cz-cv-grabbing');post({type:'cz-editing-start'});return true;}
document.addEventListener('pointermove',function(e){
  if(elDrag){
    if(!startedMove(e))return;
    var dx=Math.round((e.clientX-gx)/gg.cellW),dy=Math.round((e.clientY-gy)/gg.rowH);
    setPos(elDrag,clamp(sx+dx,0,gg.cols-sw),Math.max(0,sy+dy),sw,sh);e.preventDefault();return;
  }
  if(elResize){
    if(!startedMove(e))return;
    var cx=Math.round((e.clientX-gx)/gg.cellW),cy=Math.round((e.clientY-gy)/gg.rowH);
    var x=sx,y=sy,w=sw,h=sh;
    if(rdir.indexOf('e')>=0)w=clamp(sw+cx,1,gg.cols-sx);
    if(rdir.indexOf('s')>=0)h=Math.max(1,sh+cy);
    if(rdir.indexOf('w')>=0){var nx=clamp(sx+cx,0,sx+sw-1);w=sw+(sx-nx);x=nx;}
    if(rdir.indexOf('n')>=0){var ny=clamp(sy+cy,0,sy+sh-1);h=sh+(sy-ny);y=ny;}
    setPos(elResize,x,y,w,h);e.preventDefault();return;
  }
  if(downIdx<0||editing)return;
  if(!dragging){if(Math.abs(e.clientY-downY)<6)return;dragging=true;moved=true;document.body.classList.add('cz-dragging');post({type:'cz-editing-start'});}
  showDrop(targetIdx(e.clientY));e.preventDefault();
},{passive:false});
function targetIdx(y){var bs=blocks(),to=bs.length;for(var k=0;k<bs.length;k++){var r=bs[k].getBoundingClientRect();if(y<r.top+r.height/2){to=k;break;}}return to;}
function showDrop(to){removeDrop();var bs=blocks();dropLine=document.createElement('div');dropLine.className='cz-drop';var main=document.querySelector('main');if(to>=bs.length)main.appendChild(dropLine);else main.insertBefore(dropLine,bs[to]);}
function removeDrop(){if(dropLine&&dropLine.parentNode)dropLine.parentNode.removeChild(dropLine);dropLine=null;}
document.addEventListener('pointerup',function(e){
  var el=elDrag||elResize;
  if(el){
    try{el.releasePointerCapture(pid);}catch(_){}
    if(moved){var p=pos(el);post({type:elDrag?'cz-elem-move':'cz-elem-resize',block:idxOf(el),id:el.getAttribute('data-cz-id'),bp:curBp,pos:p});document.body.classList.remove('cz-cv-grabbing');post({type:'cz-editing-end'});}
    elDrag=null;elResize=null;setTimeout(function(){moved=false;},0);return;
  }
  if(dragging){
    var to=targetIdx(e.clientY);removeDrop();document.body.classList.remove('cz-dragging');
    var dest=to>dragFrom?to-1:to;
    if(dest!==dragFrom)post({type:'cz-reorder',from:dragFrom,to:dest});
    post({type:'cz-editing-end'});dragging=false;setTimeout(function(){moved=false;},0);
  }
  downIdx=-1;
});
// Drag an external image (an asset-library thumbnail, a chat-generated image)
// onto a section to set it as that section's background — a native HTML5
// drag, NOT the pointer-based drag-reorder above (that's for reordering
// sections, entirely within this frame; this drag originates in the PARENT
// document, so only the standard dragover/drop events fire in here at all).
var dropTargetEl=null;
function clearDropTarget(){if(dropTargetEl){dropTargetEl.classList.remove('cz-drop-target');dropTargetEl=null;}}
document.addEventListener('dragover',function(e){
  // Not gated on restrictMode (Form mode) — setting a section's background is
  // orthogonal to the canvas-only affordances that flag suppresses (freeform
  // element drag/resize, inline text edit), and works from either mode.
  if(themeMode)return;
  var b=e.target.closest&&e.target.closest('[data-cz-block]');
  if(!b){clearDropTarget();return;}
  e.preventDefault();
  if(b!==dropTargetEl){clearDropTarget();dropTargetEl=b;b.classList.add('cz-drop-target');}
});
document.addEventListener('dragleave',function(e){
  // Only clear when the pointer actually left the highlighted block (not a
  // bubbled leave from a child element re-entering a sibling).
  if(dropTargetEl&&(!e.relatedTarget||!dropTargetEl.contains(e.relatedTarget)))clearDropTarget();
});
document.addEventListener('drop',function(e){
  if(themeMode)return;
  var b=e.target.closest&&e.target.closest('[data-cz-block]');
  clearDropTarget();
  if(!b||!e.dataTransfer)return;
  e.preventDefault();
  var url=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');
  if(!url)return;
  post({type:'cz-drop-image',block:idxOf(b),url:url});
});
window.addEventListener('message',function(e){
  var d=e.data||{};
  if(d.type==='cz-highlight'){highlight(d.block);if(d.scroll){var _hb=blockEl(d.block);if(_hb&&_hb.scrollIntoView)_hb.scrollIntoView({block:'center',behavior:'smooth'});}}
  else if(d.type==='cz-clear')clearSel();
  else if(d.type==='cz-bp')curBp=(d.bp==='m')?'m':'d';
  else if(d.type==='cz-elem-highlight'){var el=document.querySelector('.cz-el[data-cz-id="'+d.id+'"]');if(el)selectEl(el);}
  else if(d.type==='cz-theme-highlight')highlightTheme(d.region);
  else if(d.type==='cz-theme-clear')clearThemeHl();
  else if(d.type==='cz-theme-open')themeMode=true;
  else if(d.type==='cz-theme-close'){themeMode=false;clearThemeHl();}
  else if(d.type==='cz-mode')restrictMode=(d.mode==='form');
});
post({type:'cz-ready'});
})();