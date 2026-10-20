(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
// On a product's own page (/shop/<slug>) the panel is already in the page:
// this fills it in place instead of drawing the grid.
var single=box.getAttribute('data-product');
if(RT.preview){box.innerHTML='<p style="color:var(--muted)">Your products appear here once your site is live.</p>';return;}
function field(f){var req=f.required?' required':'';var l='<label class="cz-label">'+RT.esc(f.label||f.key)+'</label>';
if(f.type==='textarea')return '<div>'+l+'<textarea class="cz-field" data-k="'+RT.esc(f.key)+'"'+req+'></textarea></div>';
if(f.type==='select'){var o=(f.options||[]).map(function(x){return '<option>'+RT.esc(x)+'</option>';}).join('');return '<div>'+l+'<select class="cz-field" data-k="'+RT.esc(f.key)+'"'+req+'>'+o+'</select></div>';}
var ty=(['email','number','tel','date'].indexOf(f.type)>=0)?f.type:'text';return '<div>'+l+'<input class="cz-field" type="'+ty+'" data-k="'+RT.esc(f.key)+'"'+req+' /></div>';}
// A variant is one pick from each required pick-one group, with its own stock,
// price and picture (server: services/variants.py). Without a row, a pick is
// priced and stocked by its options, as before variants existed.
function axes(p){return (p.option_groups||[]).filter(function(g){return g.select_type==='single'&&g.required;});}
function variantFor(p,ids){var ax=axes(p);if(!ax.length||!(p.variants||[]).length)return null;var picks=[];
for(var i=0;i<ax.length;i++){var hit=(ax[i].options||[]).filter(function(o){return ids.indexOf(String(o.id))>=0;});if(hit.length!==1)return null;picks.push(String(hit[0].id));}
var key=picks.sort().join();for(var j=0;j<p.variants.length;j++){if((p.variants[j].option_ids||[]).map(String).sort().join()===key)return p.variants[j];}return null;}
function live(p){return (p.variants||[]).filter(function(v){return v.status==='active';});}
// An option is sold out when it has run out itself, or when every combination
// it is part of has.
function optGone(p,g,o){if(p.fulfillment!=='physical')return false;var vs=live(p).filter(function(v){return (v.option_ids||[]).map(String).indexOf(String(o.id))>=0;});
if(vs.length&&axes(p).indexOf(g)>=0)return vs.every(function(v){return out(v.inventory);});return out(o.inventory);}
function optsHtml(p){return (p.option_groups||[]).map(function(g){
return '<div class="cz-opt-group" data-group="'+RT.esc(g.id)+'" data-single="'+(g.select_type==='single'?'1':'')+'" data-required="'+(g.required?'1':'')+'"><label class="cz-label">'+RT.esc(g.name)+(g.required?' *':'')+'</label><div class="cz-opts">'+
(g.options||[]).map(function(o){var dc=o.price_delta_cents||0;var d=dc?(' '+(dc>0?'+':'−')+RT.money(Math.abs(dc),p.currency)):'';
var gone=optGone(p,g,o);
return '<button type="button" class="cz-opt" data-opt="'+RT.esc(o.id)+'" data-delta="'+dc+'"'+(gone?' disabled':'')+'>'+RT.esc(o.name)+d+(gone?' · sold out':'')+'</button>';}).join('')+'</div></div>';}).join('');}
function out(v){return v!=null&&v<=0;}
function soldOut(p){if(p.fulfillment!=='physical')return false;if(out(p.inventory))return true;
var vs=live(p);return !!(vs.length&&axes(p).length&&vs.every(function(v){return out(v.inventory);}));}
function stars(n){n=Math.round(n||0);var s='';for(var i=1;i<=5;i++)s+=(i<=n?'★':'☆');return s;}
var REVIEWS=[],rseq=0;
// One shared product-detail overlay (acts like a product page).
var ov=document.createElement('div');ov.className='cz-pd';ov.hidden=true;
ov.innerHTML='<div class="cz-pd__panel"><button class="cz-pd__x" aria-label="Close">×</button><div class="cz-pd__grid"><div class="cz-pd__media" data-media></div><div class="cz-pd__info" data-info></div></div><div class="cz-pd__reviews" data-reviews></div></div>';
document.body.appendChild(ov);
function hideDetail(){ov.hidden=true;document.body.style.overflow=document.querySelector('.cz-bag:not([hidden])')?'hidden':'';}
function dismiss(){if(history.state&&history.state.czpd)history.back();else hideDetail();}
ov.querySelector('.cz-pd__x').addEventListener('click',dismiss);
ov.addEventListener('click',function(e){if(e.target===ov)dismiss();});
window.addEventListener('popstate',function(){if(!ov.hidden)hideDetail();});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!ov.hidden)dismiss();});
// A product's own reviews when it has any; otherwise what clients say about the store.
function reviewHtml(r){return '<figure class="cz-review"><div class="cz-review__stars">'+stars(r.rating)+(r.verified?' <span class="cz-review__verified">Verified purchase</span>':'')+'</div><blockquote>'+RT.esc(r.body)+'</blockquote><figcaption>'+RT.esc(r.author_name)+'</figcaption>'+
(r.owner_reply?'<div class="cz-review__reply"><b>Reply from the store</b> '+RT.esc(r.owner_reply)+'</div>':'')+'</figure>';}
function rlistHtml(title,avg,n,list){return '<h3 class="cz-pd__rtitle">'+title+' <span class="cz-pd__rstars">'+stars(avg)+'</span><span class="cz-pd__rn">'+n+' review'+(n>1?'s':'')+'</span></h3>'+
'<div class="cz-pd__rlist">'+list.map(reviewHtml).join('')+'</div>';}
// The summary is the product's rating over every approved review — what its card
// and structured data say — not the first 50 (verified first) that the list shows.
function productReviewsHtml(p,list){return rlistHtml('Reviews',p.rating_avg,p.rating_count||list.length,list);}
function reviewsHtml(){if(!REVIEWS.length)return '';
var avg=REVIEWS.reduce(function(a,r){return a+(r.rating||0);},0)/REVIEWS.length;
return rlistHtml('What clients say',avg,REVIEWS.length,REVIEWS);}
// "Subscribe": the product on a schedule. Signing in and checking out happen
// on the account page (/account), which opens the subscription checkout.
function subHtml(p){var iv=(p.subscription_intervals||[]).filter(function(i){return i==='week'||i==='month';});
if(!iv.length||RT.preview)return '';var save=p.subscription_discount_bps?(' and save '+(p.subscription_discount_bps/100)+'%'):'';
return '<div class="cz-pd__sub"><label class="cz-label" for="cz-every">Or subscribe'+save+'</label><div class="cz-bag__row">'+
'<select class="cz-field" id="cz-every" data-every>'+iv.map(function(i){return '<option value="'+i+'">Every '+i+'</option>';}).join('')+'</select>'+
'<button type="button" class="cz-btn cz-btn--ghost" data-sub>Subscribe</button></div></div>';}
function pics(p){var l=(p.images||[]).map(function(i){return {url:i.url,alt:i.alt||''};});
if(!l.length&&p.image_url)l=[{url:p.image_url,alt:''}];return l;}
// `root` is the panel on a product's own page; the overlay otherwise.
function openDetail(p,root){
var R=root||ov,inline=R!==ov,media=R.querySelector('[data-media]'),list=pics(p);
media.innerHTML='<div class="cz-pd__shot"></div>'+(list.length>1?'<div class="cz-pd__thumbs">'+list.map(function(x,i){
return '<button type="button" class="cz-pd__thumb" data-img="'+i+'" aria-label="Picture '+(i+1)+'"><img src="'+RT.esc(RT.url(x.url))+'" alt="'+RT.esc(x.alt)+'" /></button>';}).join('')+'</div>':'');
var shot=media.querySelector('.cz-pd__shot'),shownImg;
function showImg(u){if(u===shownImg)return;shownImg=u;
shot.innerHTML=u?'<img src="'+RT.esc(u)+'" alt="'+RT.esc(p.name)+'" />':'<div class="cz-pd__noimg"></div>';
media.querySelectorAll('.cz-pd__thumb').forEach(function(t){t.classList.toggle('is-on',RT.url(list[+t.getAttribute('data-img')].url)===u);});}
media.querySelectorAll('.cz-pd__thumb').forEach(function(t){t.addEventListener('click',function(){showImg(RT.url(list[+t.getAttribute('data-img')].url));});});
showImg(list.length?RT.url(list[0].url):'');
var priceHtml;if(p.discount_percent&&p.discounted_price_cents!=null){priceHtml='<span class="cz-pd__was">'+RT.money(p.price_cents,p.currency)+'</span>'+RT.money(p.discounted_price_cents,p.currency)+'<span class="cz-pd__off">'+p.discount_percent+'% off</span>';}else{priceHtml=p.price_cents?RT.money(p.price_cents,p.currency):'Free';}
var booking=p.fulfillment==='booking';
var info=R.querySelector('[data-info]'),hn=inline?'h1':'h2';
info.innerHTML=(p.category?'<div class="cz-eyebrow">'+RT.esc(p.category)+'</div>':'')+
'<'+hn+' class="cz-pd__name">'+RT.esc(p.name)+'</'+hn+'>'+
'<div class="cz-pd__price">'+priceHtml+'</div>'+
(p.description?'<p class="cz-pd__desc">'+RT.esc(p.description)+'</p>':'')+

optsHtml(p)+((p.fulfillment==='service'||booking)?(p.intake_fields||[]).map(field).join(''):'')+
(booking?'<div><label class="cz-label">Preferred time</label><input class="cz-field" type="datetime-local" data-when /></div>':'')+
'<div class="cz-pd__buy"><label class="cz-label">Quantity</label><input class="cz-field cz-pd__qty" type="number" min="1" value="1"'+((p.fulfillment==='physical'&&p.inventory>0)?' max="'+p.inventory+'"':'')+' data-qty />'+
(booking?'<input class="cz-field" type="email" data-email placeholder="Your email" /><input class="cz-field" type="text" data-name placeholder="Your name" />':'')+
'<p class="cz-msg" data-quote></p><button class="cz-btn cz-btn--solid cz-btn--block" data-go></button><p class="cz-msg" data-status></p></div>'+
subHtml(p);
var sb=info.querySelector('[data-go]'),msg=info.querySelector('[data-status]'),gone=soldOut(p);
// Local estimate only: same half-up integer math as the server's apply_discount_cents,
// so it agrees to the cent. The authoritative figure is the server quote below.
// A variant's own price replaces the product price and its options' changes.
function unit(){var v=variantFor(p,chosen()),own=v&&v.price_cents!=null,cov=own?(v.option_ids||[]).map(String):[];
var s=own?v.price_cents:(p.price_cents||0);info.querySelectorAll('.cz-opt--on').forEach(function(b){if(cov.indexOf(b.getAttribute('data-opt'))<0)s+=parseInt(b.getAttribute('data-delta'),10)||0;});
s=Math.max(0,s);if(p.discount_percent)s=Math.floor((s*(100-p.discount_percent)+50)/100);return s;}
function qn(){return Math.max(1,parseInt(info.querySelector('[data-qty]').value,10)||1);}
function verb(){return booking?'Request — ':'Add to bag — ';}
function chosen(){var ids=[];info.querySelectorAll('.cz-opt--on').forEach(function(b){ids.push(b.getAttribute('data-opt'));});return ids;}
// Ask the server what this cart will actually cost — tax and shipping included —
// and show THAT before the buyer commits. Sequence-numbered so a slow answer for
// an earlier selection can't overwrite a newer one; any failure keeps the estimate.
var qseq=0,qtimer=null,qbox=info.querySelector('[data-quote]');
function quote(){var seq=++qseq;RT.post('/quote',{items:[{product_id:p.id,quantity:qn(),selected_option_ids:chosen()}]}).then(function(q){
if(seq!==qseq||!q||q.total_cents==null)return;var l=(q.lines||[])[0];if(l&&l.reason)return;
if(l&&l.available===false){sb.disabled=true;sb.textContent='Out of stock';if(qbox)qbox.textContent='Not enough in stock for that choice. Try a lower quantity or another option.';return;}
var cur=q.currency||p.currency,parts=[];
if(!booking){sb.textContent=verb()+RT.money(q.subtotal_cents,cur);if(qbox)qbox.textContent='';return;}
if(q.tax_cents>0)parts.push('Tax '+RT.money(q.tax_cents,cur));
if(q.shipping_cents>0)parts.push('Shipping '+RT.money(q.shipping_cents,cur));
sb.textContent=verb()+RT.money(q.total_cents,cur);
if(qbox)qbox.textContent=parts.length?('Subtotal '+RT.money(q.subtotal_cents,cur)+' · '+parts.join(' · ')):'';
}).catch(function(){});}
function refresh(){var v=variantFor(p,chosen()),phys=p.fulfillment==='physical';
if(v&&v.image_url)showImg(RT.url(v.image_url));
if(v&&v.status!=='active'){sb.disabled=true;sb.textContent='Unavailable';if(qbox)qbox.textContent='We don\u2019t sell that combination.';return;}
if(gone||(phys&&v&&out(v.inventory))){sb.disabled=true;sb.textContent='Sold out';if(qbox)qbox.textContent='';return;}
// The lower of the product's own count and the combination's: both limit the sale.
var qi=info.querySelector('[data-qty]'),caps=phys?[p.inventory,v&&v.inventory].filter(function(n){return n>0;}):[],cap=caps.length?Math.min.apply(null,caps):null;
if(cap)qi.max=cap;else qi.removeAttribute('max');
sb.disabled=false;sb.textContent=verb()+RT.money(unit()*qn(),p.currency);if(qbox)qbox.textContent='';clearTimeout(qtimer);qtimer=setTimeout(quote,250);}
info.querySelectorAll('.cz-opt-group').forEach(function(g){var single=g.getAttribute('data-single')==='1';g.querySelectorAll('.cz-opt').forEach(function(o){o.addEventListener('click',function(){if(single){g.querySelectorAll('.cz-opt').forEach(function(x){x.classList.remove('cz-opt--on');});o.classList.add('cz-opt--on');}else o.classList.toggle('cz-opt--on');refresh();});});});
info.querySelector('[data-qty]').addEventListener('input',refresh);refresh();
sb.addEventListener('click',function(){
var ok=true;info.querySelectorAll('.cz-opt-group').forEach(function(g){if(g.getAttribute('data-required')==='1'&&!g.querySelector('.cz-opt--on'))ok=false;});
if(!ok){msg.textContent='Please choose the required options';msg.className='cz-msg err';return;}
var optIds=chosen();
var ans={},missing=null;(p.intake_fields||[]).forEach(function(f){var el=info.querySelector('[data-k="'+f.key+'"]');if(el){ans[f.key]=el.value;if(f.required&&!String(el.value).trim()&&!missing)missing=f.label||f.key;}});
if(missing){msg.textContent='Please answer: '+missing;msg.className='cz-msg err';return;}
// Everything but a booking goes in the bag; the bag checks out as one order.
var cart=window.__CAPPE_CART__;
if(!booking&&cart){var labels=[];info.querySelectorAll('.cz-opt--on').forEach(function(b){labels.push(b.textContent);});
cart.add({product_id:p.id,title:p.name,quantity:qn(),selected_option_ids:optIds,options_label:labels.join(', '),intake_answers:ans,
fulfillment:p.fulfillment,requires_approval:!!p.requires_approval,currency:p.currency,est_unit_cents:unit()});
dismiss();return;}
var email=(info.querySelector('[data-email]')||{value:''}).value.trim();
if(!email){msg.textContent='Email required';msg.className='cz-msg err';return;}
var item={product_id:p.id,quantity:qn(),intake_answers:ans,selected_option_ids:optIds};
if(booking){var w=info.querySelector('[data-when]').value;if(!w){msg.textContent='Pick a time';msg.className='cz-msg err';return;}item.starts_at=w;}
sb.disabled=true;msg.textContent='Placing order…';msg.className='cz-msg';
RT.post('/orders',{customer_email:email,customer_name:info.querySelector('[data-name]').value.trim(),items:[item],success_url:location.href,cancel_url:location.href}).then(function(res){if(res&&res.checkout_url){msg.textContent='Redirecting to secure checkout…';window.location=res.checkout_url;return;}window.location='/order/'+encodeURIComponent(res.order_token);
}).catch(function(e){sb.disabled=false;refresh();msg.textContent=e.message;msg.className='cz-msg err';});});
var subBtn=info.querySelector('[data-sub]');if(subBtn)subBtn.addEventListener('click',function(){
var ok=true;info.querySelectorAll('.cz-opt-group').forEach(function(g){if(g.getAttribute('data-required')==='1'&&!g.querySelector('.cz-opt--on'))ok=false;});
if(!ok){msg.textContent='Please choose the required options';msg.className='cz-msg err';return;}
window.location='/account?subscribe='+encodeURIComponent(p.id)+'&every='+encodeURIComponent(info.querySelector('[data-every]').value)+
'&qty='+qn()+'&opts='+encodeURIComponent(chosen().join(','));});
// The overlay is shared: a slow answer for a product opened earlier must not land under this one.
var rv=R.querySelector('[data-reviews]'),seq=++rseq;rv.innerHTML=reviewsHtml();
if(p.rating_count)RT.get('/reviews?product_id='+encodeURIComponent(p.id)).then(function(list){if(seq===rseq&&list&&list.length)rv.innerHTML=productReviewsHtml(p,list);}).catch(function(){});
if(inline)return;
ov.querySelector('.cz-pd__panel').scrollTop=0;ov.hidden=false;document.body.style.overflow='hidden';
// The address bar shows the product's own page while it's open: shareable,
// and Back closes it.
if(!(history.state&&history.state.czpd))history.pushState({czpd:1},'',p.url||location.href);
}
// A card is a link to the product's page, opened in the overlay on a plain
// click; a new-tab click, a crawler or no script follows the link.
function card(p){var c=document.createElement(p.url?'a':'button');if(p.url)c.href=p.url;else c.type='button';c.className='cz-product';
var iu=RT.url(p.image_url);var img=iu?'<img class="cz-product__img" src="'+RT.esc(iu)+'" alt="" />':'<div class="cz-product__img"></div>';
var price;if(p.discount_percent&&p.discounted_price_cents!=null){price='<span class="cz-pd__was">'+RT.money(p.price_cents,p.currency)+'</span>'+RT.money(p.discounted_price_cents,p.currency);}else{price=p.price_cents?RT.money(p.price_cents,p.currency):'Free';}
var rated=p.rating_count?'<span class="cz-product__rating" aria-label="'+p.rating_avg+' out of 5">'+stars(p.rating_avg)+' <span>'+p.rating_count+'</span></span>':'';
c.innerHTML=img+'<div class="cz-product__body"><h3>'+RT.esc(p.name)+'</h3>'+rated+'<div class="cz-product__foot"><span class="cz-price">'+price+'</span>'+(soldOut(p)?'<span class="cz-product__opts">Sold out</span>':((p.option_groups||[]).length?'<span class="cz-product__opts">Options</span>':''))+'</div></div>';
c.addEventListener('click',function(e){if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||e.button>0)return;e.preventDefault();openDetail(p);});return c;}
// Search engines read a list page as links to the products; each product's
// own page (/shop/<slug>) carries its full Product data, ratings included.
function productData(list){if(RT.preview)return;list=list.filter(function(p){return p.url;});if(!list.length)return;try{
var data={'@context':'https://schema.org','@type':'ItemList',itemListElement:list.slice(0,50).map(function(p,i){
return {'@type':'ListItem',position:i+1,url:location.origin+p.url,name:p.name};})};
var sc=document.createElement('script');sc.type='application/ld+json';sc.textContent=JSON.stringify(data).replace(/</g,'\\u003c');document.head.appendChild(sc);}catch(e){}}
function grid(list){var g=document.createElement('div');g.className='cz-store-grid';list.forEach(function(p){g.appendChild(card(p));});return g;}
Promise.all([RT.get('/products'),RT.get('/reviews').catch(function(){return [];})]).then(function(r){
var items=r[0]||[];REVIEWS=r[1]||[];
if(single){var mine=items.filter(function(x){return x.slug===single;})[0];if(mine)openDetail(mine,box.querySelector('.cz-pd__panel'));return;}
productData(items);
if(!items.length){box.innerHTML='<p style="color:var(--muted)">No products yet.</p>';return;}box.innerHTML='';
var cats=[],byCat={};items.forEach(function(p){var k=(p.category||'').trim();if(!(k in byCat)){byCat[k]=[];cats.push(k);}byCat[k].push(p);});
if(cats.filter(function(k){return k;}).length===0){box.appendChild(grid(items));return;}
cats.sort(function(a,b){if(!a)return 1;if(!b)return -1;return 0;});
cats.forEach(function(k){if(k){var h=document.createElement('h3');h.className='cz-store-cat';h.textContent=k;box.appendChild(h);}box.appendChild(grid(byCat[k]));});
}).catch(function(){if(!single)box.innerHTML='<p style="color:var(--muted)">Unable to load products.</p>';});})();