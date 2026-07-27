(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
box.innerHTML='<div class="cz-inline"><input class="cz-field" type="email" data-email placeholder="you@example.com" /><button class="cz-btn cz-btn--solid">Subscribe</button></div><p class="cz-msg"></p>';
var sb=box.querySelector('button'),msg=box.querySelector('.cz-msg');
sb.addEventListener('click',function(){var email=box.querySelector('[data-email]').value.trim();
if(!email){msg.textContent='Email required';msg.className='cz-msg err';return;}
sb.disabled=true;RT.post('/subscribe',{email:email}).then(function(){box.innerHTML='<p class="cz-msg ok">You are subscribed.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='cz-msg err';});});})();