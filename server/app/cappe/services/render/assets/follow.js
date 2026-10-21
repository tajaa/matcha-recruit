(function(){
var box=document.getElementById('mz-follow'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var f=box.querySelector('form'),msg=box.querySelector('[data-mz-msg]'),btn=f.querySelector('button'),input=f.querySelector('input');
if(RT.preview){btn.disabled=true;msg.textContent='Readers follow your magazine here.';return;}
f.addEventListener('submit',function(e){e.preventDefault();var email=input.value.trim();
if(!email){msg.textContent='Your email, please.';msg.className='mz-follow__msg err';return;}
btn.disabled=true;RT.post('/follow',{email:email}).then(function(d){f.style.display='none';
msg.textContent=(d&&d.message)||'Check your inbox to confirm.';msg.className='mz-follow__msg ok';
}).catch(function(err){btn.disabled=false;msg.textContent=err.message||'That didn’t work. Try again.';msg.className='mz-follow__msg err';});});})();
