(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var wantForm=box.getAttribute('data-form')==='1';
function stars(n){n=n||0;var s='';for(var i=1;i<=5;i++){s+=i<=n?'★':'☆';}return s;}
function formHtml(){return wantForm?'<div class="cz-rv-form"><div class="cz-rv-form__t">Leave a review</div>'+
'<input class="cz-field" data-name placeholder="Your name" />'+
'<select class="cz-field" data-rating><option value="5">★★★★★</option><option value="4">★★★★</option><option value="3">★★★</option><option value="2">★★</option><option value="1">★</option></select>'+
'<textarea class="cz-field" data-body rows="3" placeholder="Share your experience"></textarea>'+
'<button class="cz-btn cz-btn--solid cz-btn--block" data-go>Submit review</button><p class="cz-msg"></p></div>':'';}
function render(list){
var grid=list.length?('<div class="cz-reviews-grid">'+list.map(function(r){return '<figure class="cz-review"><div class="cz-review__stars">'+stars(r.rating)+'</div><blockquote>'+RT.esc(r.body)+'</blockquote><figcaption>'+RT.esc(r.author_name)+'</figcaption></figure>';}).join('')+'</div>'):(wantForm?'':'<p style="color:var(--muted)">No reviews yet.</p>');
box.innerHTML=grid+formHtml();
if(!wantForm)return;
var go=box.querySelector('[data-go]'),msg=box.querySelector('.cz-msg');
go.addEventListener('click',function(){var name=box.querySelector('[data-name]').value.trim(),body=box.querySelector('[data-body]').value.trim(),rating=parseInt(box.querySelector('[data-rating]').value,10);
if(!name||!body){msg.textContent='Name and review are required';msg.className='cz-msg err';return;}
go.disabled=true;msg.textContent='Submitting…';msg.className='cz-msg';
RT.post('/reviews',{author_name:name,rating:rating,body:body}).then(function(){box.querySelector('.cz-rv-form').innerHTML='<p class="cz-msg ok" style="text-align:center">Thanks! Your review will appear once approved.</p>';
}).catch(function(e){go.disabled=false;msg.textContent=e.message;msg.className='cz-msg err';});});}
if(RT.preview){render([{author_name:'Sample Customer',rating:5,body:'Approved reviews from your customers show here.'}]);return;}
RT.get('/reviews').then(function(list){render(list||[]);}).catch(function(){box.innerHTML='<p style="color:var(--muted)">Unable to load reviews.</p>';});
})();