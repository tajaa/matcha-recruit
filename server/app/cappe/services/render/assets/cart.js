(function(){
// The storefront bag. Products are added from the product panel (store.js);
// checkout sends the whole bag as one order. Prices shown here are the
// SERVER's (POST /quote) — the estimate is only a placeholder while it loads.
var RT=window.__CAPPE_RT__;if(!RT||RT.preview||!RT.slug)return;
var KEY='cz-cart:'+RT.slug,OKEY='cz-cart-order:'+RT.slug,CKEY='cz-cart-country:'+RT.slug,PKEY='cz-cart-promo:'+RT.slug,MAX_QTY=99;
function load(){try{var v=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(v)?v:[];}catch(e){return [];}}
var items=load(),quote=null,qseq=0,busy=false,shipTo=null;
try{shipTo=localStorage.getItem(CKEY)||null;}catch(e){}
var promoCode=null;try{promoCode=localStorage.getItem(PKEY)||null;}catch(e){}
function setPromo(c){promoCode=c||null;try{if(promoCode)localStorage.setItem(PKEY,promoCode);else localStorage.removeItem(PKEY);}catch(e){}}
// Country names in the buyer's language; the code if the browser can't.
var names=null;try{names=new Intl.DisplayNames([navigator.language||'en'],{type:'region'});}catch(e){}
function countryName(c){try{return (names&&names.of(c))||c;}catch(e){return c;}}
function persist(){try{localStorage.setItem(KEY,JSON.stringify(items));}catch(e){}}
function keyOf(l){return [l.product_id,(l.selected_option_ids||[]).slice().sort().join(','),JSON.stringify(l.intake_answers||{})].join('|');}
function count(){var n=0;items.forEach(function(i){n+=i.quantity||0;});return n;}

// ── header button ──
var bar=document.querySelector('.cz-bar'),btn=document.createElement('button');
btn.type='button';btn.className='cz-bagbtn';btn.setAttribute('aria-haspopup','dialog');
var hasStore=!!document.querySelector('.cz-store');
function paintButton(){var n=count();btn.innerHTML='Bag'+(n?' <span class="cz-bagbtn__n">'+n+'</span>':'');btn.setAttribute('aria-label','Your bag, '+n+' item'+(n===1?'':'s'));btn.hidden=!(hasStore||n);}
if(bar){bar.appendChild(btn);bar.classList.add('cz-has-bag');}
btn.addEventListener('click',function(){open();});

// ── drawer ──
var root=document.createElement('div');root.className='cz-bag';root.hidden=true;
root.innerHTML='<div class="cz-bag__scrim" data-close></div>'+
'<aside class="cz-bag__panel" role="dialog" aria-modal="true" aria-labelledby="czbag-title">'+
'<div class="cz-bag__head"><h2 id="czbag-title">Your bag</h2><button type="button" class="cz-pd__x" data-close aria-label="Close">×</button></div>'+
'<div class="cz-bag__lines" data-lines></div>'+
'<div class="cz-bag__foot" data-foot>'+
'<label class="cz-bag__ship" data-shipwrap hidden><span class="cz-label">Ship to</span>'+
'<select class="cz-field" data-ship aria-label="Ship to"></select></label><p class="cz-bag__shipnote" data-shipnote hidden></p>'+
'<div class="cz-bag__promo" data-promowrap hidden><div class="cz-bag__row">'+
'<input class="cz-field" data-promo placeholder="Promo code" maxlength="40" autocapitalize="characters" aria-label="Promo code" />'+
'<button type="button" class="cz-btn cz-btn--ghost" data-promo-apply>Apply</button></div><p class="cz-msg" data-promo-msg role="status"></p></div>'+
'<dl class="cz-bag__totals" data-totals></dl><p class="cz-msg" data-notice></p>'+
'<input class="cz-field" type="email" data-email placeholder="Your email" autocomplete="email" aria-label="Your email" />'+
'<input class="cz-field" type="text" data-name placeholder="Your name" autocomplete="name" aria-label="Your name" />'+
'<fieldset class="cz-bag__addr" data-addr hidden><legend class="cz-label">Shipping address</legend>'+
'<input class="cz-field" data-a="line1" placeholder="Address" autocomplete="address-line1" aria-label="Address" />'+
'<input class="cz-field" data-a="line2" placeholder="Apartment, suite (optional)" autocomplete="address-line2" aria-label="Apartment or suite" />'+
'<div class="cz-bag__row"><input class="cz-field" data-a="city" placeholder="City" autocomplete="address-level2" aria-label="City" />'+
'<input class="cz-field" data-a="state" placeholder="State / region" autocomplete="address-level1" aria-label="State or region" /></div>'+
'<input class="cz-field" data-a="postal_code" placeholder="Postal code" autocomplete="postal-code" aria-label="Postal code" /></fieldset>'+
'<button type="button" class="cz-btn cz-btn--solid cz-btn--block" data-go>Checkout</button>'+
'<p class="cz-msg" data-msg role="status"></p></div></aside>';
document.body.appendChild(root);
var linesEl=root.querySelector('[data-lines]'),totalsEl=root.querySelector('[data-totals]'),noticeEl=root.querySelector('[data-notice]'),
addrEl=root.querySelector('[data-addr]'),goEl=root.querySelector('[data-go]'),msgEl=root.querySelector('[data-msg]'),footEl=root.querySelector('[data-foot]'),
shipWrap=root.querySelector('[data-shipwrap]'),shipEl=root.querySelector('[data-ship]'),shipNote=root.querySelector('[data-shipnote]'),shipList='';
var promoWrap=root.querySelector('[data-promowrap]'),promoEl=root.querySelector('[data-promo]'),promoMsg=root.querySelector('[data-promo-msg]');
function applyPromo(){var c=promoEl.value.trim().toUpperCase();setPromo(c);quote=null;render();refreshQuote();}
root.querySelector('[data-promo-apply]').addEventListener('click',applyPromo);
promoEl.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();applyPromo();}});
promoMsg.addEventListener('click',function(e){if(e.target&&e.target.hasAttribute('data-promo-remove')){setPromo(null);promoEl.value='';quote=null;render();refreshQuote();}});
shipEl.addEventListener('change',function(){shipTo=shipEl.value;try{localStorage.setItem(CKEY,shipTo);}catch(e){}quote=null;render();refreshQuote();});
root.querySelectorAll('[data-close]').forEach(function(el){el.addEventListener('click',close);});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!root.hidden)close();});

function open(){root.hidden=false;document.body.style.overflow='hidden';render();refreshQuote();var x=root.querySelector('.cz-pd__x');if(x)x.focus();}
function close(){root.hidden=true;document.body.style.overflow='';btn.focus();}
function needsAddress(){return !!(quote&&quote.pays_by_card===false&&items.some(function(i){return i.fulfillment==='physical';}));}
function lineOf(i){return quote&&quote.lines&&quote.lines[i];}
// Where the bag ships: a picker when the store ships to more than one
// country, a note when it ships home only. The quote is what decides.
function paintShip(){var list=quote&&quote.ship_countries;
if(!list){shipWrap.hidden=true;shipNote.hidden=true;return;}
if(list.length<2){shipWrap.hidden=true;shipNote.hidden=false;shipNote.textContent='Ships within '+countryName(list[0])+' only.';return;}
shipNote.hidden=true;shipWrap.hidden=false;var key=list.join(',');
if(key!==shipList){shipList=key;shipEl.innerHTML=list.map(function(c,i){return '<option value="'+RT.esc(c)+'">'+RT.esc(countryName(c))+'</option>'+(i===0&&list.length>1?'<option disabled>──────────</option>':'');}).join('');}
shipEl.value=quote.ship_country;}

function render(){
paintButton();
if(!items.length){linesEl.innerHTML='<p class="cz-bag__empty">Your bag is empty.</p>';footEl.hidden=true;return;}
footEl.hidden=false;
linesEl.innerHTML=items.map(function(it,i){var q=lineOf(i),unit=q&&q.unit_price_cents!=null&&q.available!==false?q.unit_price_cents:it.est_unit_cents;
var gone=q&&q.available===false;
return '<div class="cz-bag__line'+(gone?' cz-bag__line--gone':'')+'"><div class="cz-bag__info"><div class="cz-bag__title">'+RT.esc(it.title)+'</div>'+
(it.options_label?'<div class="cz-bag__opts">'+RT.esc(it.options_label)+'</div>':'')+
(gone?'<div class="cz-msg err">'+RT.esc(q.reason||'Not available in that quantity')+'</div>':'')+
'<div class="cz-bag__qty"><button type="button" data-dec="'+i+'" aria-label="One fewer">−</button><span aria-live="polite">'+it.quantity+'</span>'+
'<button type="button" data-inc="'+i+'" aria-label="One more">+</button><button type="button" class="cz-bag__rm" data-rm="'+i+'">Remove</button></div></div>'+
'<div class="cz-bag__price">'+(unit!=null?RT.money(unit*it.quantity,it.currency):'')+'</div></div>';}).join('');
linesEl.querySelectorAll('[data-inc]').forEach(function(b){b.addEventListener('click',function(){var i=+b.getAttribute('data-inc');items[i].quantity=Math.min(MAX_QTY,items[i].quantity+1);changed();});});
linesEl.querySelectorAll('[data-dec]').forEach(function(b){b.addEventListener('click',function(){var i=+b.getAttribute('data-dec');if(items[i].quantity>1){items[i].quantity--;changed();}});});
linesEl.querySelectorAll('[data-rm]').forEach(function(b){b.addEventListener('click',function(){items.splice(+b.getAttribute('data-rm'),1);changed();});});
var cur=(quote&&quote.currency)||(items[0]&&items[0].currency)||'USD',rows=[];
// A code's discount is off the subtotal the server sends; show it on its own line.
var promo=quote&&quote.promo,disc=promo&&promo.valid?promo.discount_cents:0;
if(quote&&quote.total_cents!=null){rows.push(['Subtotal',quote.subtotal_cents+disc]);if(disc)rows.push(['Discount ('+promo.code+')',-disc]);if(quote.tax_cents)rows.push(['Tax',quote.tax_cents]);if(quote.shipping_cents)rows.push(['Shipping',quote.shipping_cents]);rows.push(['Total',quote.total_cents]);}
totalsEl.innerHTML=rows.map(function(r){return '<div'+(r[0]==='Total'?' class="cz-bag__total"':'')+'><dt>'+RT.esc(r[0])+'</dt><dd>'+(r[1]<0?'−':'')+RT.money(Math.abs(r[1]),cur)+'</dd></div>';}).join('')||'<div><dt>Total</dt><dd>…</dd></div>';
promoWrap.hidden=!(quote&&quote.promo_codes);
if(promoCode&&!promoEl.value)promoEl.value=promoCode;
if(promo&&promo.valid){promoMsg.className='cz-msg';promoMsg.innerHTML=RT.esc(promo.code)+' applied. <button type="button" class="cz-bag__rm" data-promo-remove>Remove</button>';}
else if(promo){promoMsg.className='cz-msg err';promoMsg.textContent=promo.message||'That code can’t be used.';}
else{promoMsg.textContent='';}
var approval=items.some(function(i){return i.requires_approval;});
var noShip=!!(quote&&quote.ships_to===false);
paintShip();
noticeEl.className='cz-msg'+(noShip?' err':'');
noticeEl.textContent=noShip?'This store doesn’t ship to '+countryName(quote.ship_country)+'. Choose another country.':
(approval?'Something in your bag needs the store’s approval first. You won’t be charged now — if they accept, you’ll get an email with a link to pay.':'');
addrEl.hidden=!needsAddress();
var blocked=!quote||noShip||(quote.lines||[]).some(function(l){return l.available===false;});
goEl.disabled=busy||blocked;goEl.textContent=busy?'Placing order…':(approval?'Send order request':(quote&&quote.pays_by_card?'Checkout':'Place order'));
}
function changed(){persist();quote=null;render();refreshQuote();}
// The server prices the bag: options, promotions, tax and shipping. A slow
// answer for an older bag can't overwrite a newer one.
function refreshQuote(){if(!items.length){quote=null;render();return;}var seq=++qseq;
var req={items:items.map(function(i){return {product_id:i.product_id,quantity:i.quantity,selected_option_ids:i.selected_option_ids||[]};})};
if(shipTo)req.ship_country=shipTo;
if(promoCode)req.promo_code=promoCode;
RT.post('/quote',req)
.then(function(q){if(seq!==qseq)return;quote=q;render();})
.catch(function(e){if(seq!==qseq)return;
if(shipTo){shipTo=null;try{localStorage.removeItem(CKEY);}catch(x){}refreshQuote();return;}
quote=null;render();msgEl.className='cz-msg err';msgEl.textContent=e.message||'Could not price your bag.';});}

goEl.addEventListener('click',function(){
var email=root.querySelector('[data-email]').value.trim(),name=root.querySelector('[data-name]').value.trim();
msgEl.className='cz-msg err';
if(!email){msgEl.textContent='Enter your email so the store can send your receipt.';return;}
var body={customer_email:email,customer_name:name||null,
items:items.map(function(i){return {product_id:i.product_id,quantity:i.quantity,selected_option_ids:i.selected_option_ids||[],intake_answers:i.intake_answers||{}};}),
success_url:location.href.split('#')[0],cancel_url:location.href.split('#')[0]};
// The country the bag was priced for; the payment page takes an address there only.
if(quote&&quote.ship_country)body.ship_country=quote.ship_country;
// Only a code the quote accepted: an invalid one would refuse the whole order.
if(quote&&quote.promo&&quote.promo.valid)body.promo_code=quote.promo.code;
if(needsAddress()){var a={};addrEl.querySelectorAll('[data-a]').forEach(function(el){a[el.getAttribute('data-a')]=el.value.trim();});
if(!a.line1||!a.city){msgEl.textContent='Add your shipping address (at least the address and city).';return;}
a.country=quote.ship_country;a.name=name||null;body.shipping_address=a;}
busy=true;render();msgEl.className='cz-msg';msgEl.textContent='';
RT.post('/orders',body).then(function(res){
// Remember which order this bag became: the order page empties the bag only
// for this one (an old order link must not empty a bag filled since).
try{localStorage.setItem(OKEY,res.order_token);}catch(e){}
if(res.checkout_url){msgEl.textContent='Redirecting to secure checkout…';window.location=res.checkout_url;return;}
window.location='/order/'+encodeURIComponent(res.order_token);
}).catch(function(e){busy=false;render();msgEl.className='cz-msg err';msgEl.textContent=e.message;refreshQuote();});});

window.__CAPPE_CART__={
add:function(line){line.quantity=Math.max(1,Math.min(MAX_QTY,parseInt(line.quantity,10)||1));var k=keyOf(line),hit=null;
items.forEach(function(i){if(keyOf(i)===k)hit=i;});if(hit){hit.quantity=Math.min(MAX_QTY,hit.quantity+line.quantity);}else{items.push(line);}
persist();quote=null;open();},
open:open};
// Another tab changed the bag.
window.addEventListener('storage',function(e){if(e.key===KEY){items=load();quote=null;render();if(!root.hidden)refreshQuote();}});
paintButton();
})();
