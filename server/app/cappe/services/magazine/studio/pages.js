(function(){
// A paged story's pages (services/magazine/studio/render.py): turned a spread
// at a time (a page at a time on a phone) with the arrows, the keys or a
// swipe, and the folio says which pages show. Without it the strip still
// scrolls sideways and snaps.
var strip=document.querySelector('[data-lyt-strip]');if(!strip)return;
var prev=document.querySelector('[data-lyt-prev]'),next=document.querySelector('[data-lyt-next]'),folio=document.querySelector('[data-lyt-folio]');
var total=strip.querySelectorAll('.lyt-paper').length,phone=window.matchMedia('(max-width:699px)');
function stops(){var els=phone.matches?strip.querySelectorAll('.lyt-paper'):strip.querySelectorAll('.lyt-slot'),base=strip.getBoundingClientRect().left-strip.scrollLeft;
return [].map.call(els,function(el){return {x:Math.round(el.getBoundingClientRect().left-base),el:el};});}
function at(list){var best=0;list.forEach(function(s,i){if(Math.abs(s.x-strip.scrollLeft)<Math.abs(list[best].x-strip.scrollLeft))best=i;});return best;}
function show(){var list=stops();if(!list.length)return;var i=at(list),el=list[i].el;
var ns=[].map.call(el.classList.contains('lyt-paper')?[el]:el.querySelectorAll('.lyt-paper'),function(p){return +p.getAttribute('data-lyt-n');});
if(folio)folio.textContent=(ns.length>1?'Pages '+ns[0]+'–'+ns[ns.length-1]:'Page '+ns[0])+' of '+total;
if(prev)prev.hidden=i===0;if(next)next.hidden=i===list.length-1;}
function go(d){var list=stops(),i=at(list)+d;if(i<0||i>=list.length)return;strip.scrollTo({left:list[i].x,behavior:'smooth'});}
if(prev)prev.addEventListener('click',function(){go(-1);});
if(next)next.addEventListener('click',function(){go(1);});
document.addEventListener('keydown',function(e){var t=e.target;if(e.defaultPrevented||e.metaKey||e.ctrlKey||e.altKey)return;
if(t&&(t.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)))return;
if(e.key==='ArrowRight'){e.preventDefault();go(1);}else if(e.key==='ArrowLeft'){e.preventDefault();go(-1);}});
var tick=0;strip.addEventListener('scroll',function(){cancelAnimationFrame(tick);tick=requestAnimationFrame(show);},{passive:true});
window.addEventListener('resize',show);show();
})();
