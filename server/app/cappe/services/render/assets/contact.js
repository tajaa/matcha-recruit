(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var slug=box.getAttribute('data-form')||'';var sb=box.querySelector('button'),msg=box.querySelector('.cz-msg');
sb.addEventListener('click',function(){if(!slug){msg.textContent='Form not configured yet';msg.className='cz-msg err';return;}
var data={};box.querySelectorAll('[data-k]').forEach(function(el){data[el.getAttribute('data-k')]=el.value;});
sb.disabled=true;msg.textContent='Sending...';msg.className='cz-msg';
RT.post('/forms/'+encodeURIComponent(slug),{data:data,submitter_email:data.email||null}).then(function(){
box.innerHTML='<p class="cz-msg ok" style="text-align:center">Thanks - your message was sent.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='cz-msg err';});});})();