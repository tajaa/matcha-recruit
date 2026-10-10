(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var wantForm=box.getAttribute('data-form')==='1',who='anyone';
function stars(n){n=n||0;var s='';for(var i=1;i<=5;i++){s+=i<=n?'★':'☆';}return s;}
// The server decides who may post (anyone / buyers / off); the block only says
// whether to offer the form at all.
function formHtml(){if(!wantForm||who==='off')return '';
if(who==='buyers')return '<p class="cz-msg" style="text-align:center">Bought something here? You can review it from your order page.</p>';
return '<div class="cz-rv-form"><div class="cz-rv-form__t">Leave a review</div>'+
'<input class="cz-field" data-name placeholder="Your name" aria-label="Your name" />'+
'<select class="cz-field" data-rating aria-label="Rating"><option value="5">★★★★★</option><option value="4">★★★★</option><option value="3">★★★</option><option value="2">★★</option><option value="1">★</option></select>'+
'<textarea class="cz-field" data-body rows="3" placeholder="Share your experience" aria-label="Your review"></textarea>'+
'<input class="cz-hp" data-website tabindex="-1" autocomplete="off" aria-hidden="true" />'+
'<button class="cz-btn cz-btn--solid cz-btn--block" data-go>Submit review</button><p class="cz-msg"></p></div>';}
function reviewHtml(r){return '<figure class="cz-review"><div class="cz-review__stars">'+stars(r.rating)+(r.verified?' <span class="cz-review__verified">Verified purchase</span>':'')+'</div><blockquote>'+RT.esc(r.body)+'</blockquote><figcaption>'+RT.esc(r.author_name)+'</figcaption>'+
(r.owner_reply?'<div class="cz-review__reply"><b>Reply from the store</b> '+RT.esc(r.owner_reply)+'</div>':'')+'</figure>';}
function render(list){
var grid=list.length?('<div class="cz-reviews-grid">'+list.map(reviewHtml).join('')+'</div>'):(wantForm&&who!=='off'?'':'<p style="color:var(--muted)">No reviews yet.</p>');
box.innerHTML=grid+formHtml();
var go=box.querySelector('[data-go]');if(!go)return;var msg=box.querySelector('.cz-msg');
go.addEventListener('click',function(){var name=box.querySelector('[data-name]').value.trim(),body=box.querySelector('[data-body]').value.trim(),rating=parseInt(box.querySelector('[data-rating]').value,10);
if(!name||!body){msg.textContent='Name and review are required';msg.className='cz-msg err';return;}
go.disabled=true;msg.textContent='Submitting…';msg.className='cz-msg';
RT.post('/reviews',{author_name:name,rating:rating,body:body,website:box.querySelector('[data-website]').value}).then(function(){box.querySelector('.cz-rv-form').innerHTML='<p class="cz-msg ok" style="text-align:center">Thanks! Your review will appear once approved.</p>';
}).catch(function(e){go.disabled=false;msg.textContent=e.message;msg.className='cz-msg err';});});}
if(RT.preview){render([{author_name:'Sample Customer',rating:5,body:'Approved reviews from your customers show here.'}]);return;}
Promise.all([RT.get('/reviews'),wantForm?RT.get('/review-settings').catch(function(){return {submissions:'anyone'};}):Promise.resolve(null)])
.then(function(r){if(r[1]&&r[1].submissions)who=r[1].submissions;render(r[0]||[]);})
.catch(function(){box.innerHTML='<p style="color:var(--muted)">Unable to load reviews.</p>';});
})();