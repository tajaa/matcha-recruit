(function(){
// A story's pages, turned left and right (services/magazine/pages.py
// book_html). The pages are CSS columns of the book's height that run off to
// the right; a "spread" is the book's width. This script turns spreads with
// the arrow buttons, the arrow / Page keys and a swipe, keeps the reader's
// place when the window changes, says which pages are showing, and marks the
// spread on the reader (data-mz-at; "0" is the matte cover, no gloss).
// A swipe that stops part-way turns the page it was heading for once it has
// gone a little way (FLICK of a spread), else springs back.
// A browser never counts the space after the last column, so fit() measures
// the pages and moves .mz-end to make them end on a whole spread.
// Keep in step with client/src/cappe/magazine/reader/book.ts, which does the
// same from outside the script-less preview frames.
var box=document.querySelector('[data-mz-book]');if(!box)return;
var book=box.querySelector('.mz-book'),pages=box.querySelector('.mz-pages'),story=pages.firstElementChild,end=box.querySelector('.mz-end'),prev=box.querySelector('[data-mz-prev]'),next=box.querySelector('[data-mz-next]'),folio=box.querySelector('[data-mz-folio]');
var still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
var FLICK=0.06,cur=0,n=1,count=1,resizing=null,settle=null;
function width(){return book.clientWidth||1;}
function perSpread(){var c=parseInt(getComputedStyle(pages).columnCount,10);return c>1?c:1;}
// Where the last column ends, from the story's own column pieces (measuring
// changes nothing, so the reader's place never moves).
function extent(){var r=story?story.getClientRects():[],b=book.getBoundingClientRect(),x=0;
for(var k=0;k<r.length;k++)x=Math.max(x,r[k].right-b.left+book.scrollLeft);return x||book.scrollWidth;}
function fit(){var w=width(),per=perSpread(),pad=parseFloat(getComputedStyle(book).paddingLeft)||0,x=extent();
n=Math.max(1,Math.ceil((x-1)/w));count=Math.max(1,Math.min(n*per,Math.round((x+pad)/(w/per))));
if(end)end.style.left=(n*w-pad-1)+'px';}
function clamp(i){return Math.max(0,Math.min(n-1,i));}
function at(){return clamp(Math.round(book.scrollLeft/width()));}
function show(){var i=at(),per=perSpread(),first=i*per+1,last=Math.min(count,first+per-1);
box.setAttribute('data-mz-at',String(i));
prev.hidden=i<=0;next.hidden=i>=n-1;
folio.textContent=n>1?(first===last?'Page '+first:'Pages '+first+'–'+last)+' of '+count:'';}
function go(i){cur=clamp(i);var to=cur*width();if(Math.abs(book.scrollLeft-to)>2)book.scrollTo({left:to,behavior:still?'auto':'smooth'});show();}
prev.addEventListener('click',function(){go(cur-1);});
next.addEventListener('click',function(){go(cur+1);});
document.addEventListener('keydown',function(e){var t=e.target,tag=t&&t.tagName;
if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||(t&&t.isContentEditable)||e.metaKey||e.ctrlKey||e.altKey)return;
if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();go(cur+1);}
else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();go(cur-1);}});
// Where the pages came to rest: on a spread (a turn we made ends there),
// or part-way through a swipe, to settle.
function rest(){var w=width(),off=book.scrollLeft-cur*w;
if(Math.abs(off)<=2){show();return;}
var to=Math.abs(off)>=w/2?Math.round(book.scrollLeft/w):Math.abs(off)>w*FLICK?cur+(off>0?1:-1):cur;go(to);}
book.addEventListener('scroll',function(){show();if(resizing)return;clearTimeout(settle);settle=setTimeout(rest,140);},{passive:true});
// The pages changed: measure again and stay on the spread being read.
function refit(){fit();book.scrollLeft=clamp(cur)*width();show();}
window.addEventListener('resize',function(){clearTimeout(resizing);
resizing=setTimeout(function(){resizing=null;refit();},250);refit();});
// Pictures, fonts and a subscriber's part arriving all add pages.
if(window.ResizeObserver&&story)new ResizeObserver(refit).observe(story);
window.addEventListener('load',refit);
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(refit);
refit();
})();
