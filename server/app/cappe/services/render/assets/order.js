(function(){
var box=document.querySelector('[data-czorder]'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var token=box.getAttribute('data-token'),base='/api/cappe/public/orders/'+encodeURIComponent(token);
// Empty the bag only for the order it was checked out as — an old order link
// opened later must not wipe a bag the buyer has filled since.
try{var k='cz-cart-order:'+RT.slug;if(box.getAttribute('data-clear-cart')==='1'&&localStorage.getItem(k)===token){localStorage.removeItem('cz-cart:'+RT.slug);localStorage.removeItem('cz-cart-promo:'+RT.slug);localStorage.removeItem(k);}}catch(e){}
var pay=box.querySelector('[data-czpay]'),msg=box.querySelector('[data-czpay-msg]');
if(pay){pay.addEventListener('click',function(){pay.disabled=true;if(msg){msg.className='cz-msg';msg.textContent='Opening secure checkout…';}
fetch(base+'/pay',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(function(r){return r.json().catch(function(){return null;}).then(function(d){if(!r.ok)throw new Error((d&&typeof d.detail==='string'&&d.detail)||'Could not open checkout. Try again in a moment.');return d;});})
.then(function(d){if(d&&d.checkout_url){window.location=d.checkout_url;}else{throw new Error('Could not open checkout.');}})
.catch(function(e){pay.disabled=false;if(msg){msg.className='cz-msg err';msg.textContent=e.message;}});});}
// Back from Stripe a moment before the payment is confirmed: look again for a
// short while, then leave the page as it is.
if(box.getAttribute('data-poll')==='1'){var n=0;var tick=function(){n++;fetch(base).then(function(r){return r.ok?r.json():null;}).then(function(d){if(d&&(d.status==='paid'||d.status==='fulfilled')){window.location.reload();return;}if(n<15)setTimeout(tick,2000);}).catch(function(){if(n<15)setTimeout(tick,3000);});};setTimeout(tick,1500);}
// Reviews of what was bought: sent with this order's token, so they're marked
// as a verified purchase.
box.querySelectorAll('[data-czreview]').forEach(function(f){f.addEventListener('submit',function(e){e.preventDefault();
var m=f.querySelector('.cz-msg'),b=f.querySelector('button');b.disabled=true;m.className='cz-msg';m.textContent='Posting…';
RT.post('/reviews',{author_name:f.querySelector('[data-name]').value.trim(),rating:parseInt(f.querySelector('[data-rating]').value,10),
body:f.querySelector('[data-body]').value.trim(),product_id:f.getAttribute('data-product'),order_token:token})
.then(function(){f.innerHTML='<p class="cz-msg ok">Thanks! Your review will appear once the store approves it.</p>';})
.catch(function(err){b.disabled=false;m.className='cz-msg err';m.textContent=err.message;});});});
})();
