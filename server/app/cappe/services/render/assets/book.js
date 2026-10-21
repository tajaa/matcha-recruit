(function(){
// A story's pages, turned left and right (services/magazine/pages.py
// book_html). The pages are CSS columns of the book's height that run off to
// the right; a "spread" is the book's width. This script turns spreads with
// the arrow buttons, the arrow / Page keys and a swipe (it settles a swipe on
// the nearest spread), keeps the reader's place when the window changes, and
// says which pages are showing.
var box=document.querySelector('[data-mz-book]');if(!box)return;
var book=box.querySelector('.mz-book'),pages=box.querySelector('.mz-pages'),prev=box.querySelector('[data-mz-prev]'),next=box.querySelector('[data-mz-next]'),folio=box.querySelector('[data-mz-folio]');
var still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
var cur=0,resizing=null,settle=null;
function width(){return book.clientWidth||1;}
function perSpread(){var n=parseInt(getComputedStyle(pages).columnCount,10);return n>1?n:1;}
function spreads(){return Math.max(1,Math.round(book.scrollWidth/width()));}
function at(){return Math.min(spreads()-1,Math.round(book.scrollLeft/width()));}
function show(){var i=at(),n=spreads(),per=perSpread(),total=n*per,first=i*per+1,last=Math.min(total,first+per-1);
if(!resizing)cur=i;
prev.hidden=i<=0;next.hidden=i>=n-1;
folio.textContent=n>1?(first===last?'Page '+first:'Pages '+first+'–'+last)+' of '+total:'';}
function go(i){i=Math.max(0,Math.min(spreads()-1,i));book.scrollTo({left:i*width(),behavior:still?'auto':'smooth'});}
prev.addEventListener('click',function(){go(at()-1);});
next.addEventListener('click',function(){go(at()+1);});
document.addEventListener('keydown',function(e){var t=e.target,tag=t&&t.tagName;
if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||(t&&t.isContentEditable)||e.metaKey||e.ctrlKey||e.altKey)return;
if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();go(at()+1);}
else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();go(at()-1);}});
// A swipe or a trackpad stops wherever it stops: settle it on a spread.
book.addEventListener('scroll',function(){show();if(resizing)return;clearTimeout(settle);settle=setTimeout(function(){
var i=at();if(Math.abs(book.scrollLeft-i*width())>2)go(i);},140);},{passive:true});
// The window changed size: stay on the spread being read.
window.addEventListener('resize',function(){clearTimeout(resizing);
resizing=setTimeout(function(){resizing=null;show();},250);book.scrollLeft=cur*width();show();});
// A subscriber's part arriving adds pages.
if(window.ResizeObserver)new ResizeObserver(function(){show();}).observe(pages);
show();
})();
