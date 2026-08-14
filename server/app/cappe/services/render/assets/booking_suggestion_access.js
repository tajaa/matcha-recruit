(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;
if(!box||!RT||RT.preview)return;
function accessForm(ai){
 ai.innerHTML='<summary style="cursor:pointer;font-weight:600">Describe what works</summary>'+
  '<p style="color:var(--muted);font-size:.88rem;margin:.55rem 0">AI matching is available to returning clients. Enter your email and we’ll send a secure link if we find your client record.</p>'+
  '<input class="cz-field" type="email" data-ai-email placeholder="Your client email" />'+
  '<input type="text" data-ai-website tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0" />'+
  '<button type="button" class="cz-btn cz-btn--block" data-ai-access>Send secure link</button><p class="cz-msg" data-ai-access-msg></p>';
 var button=ai.querySelector('[data-ai-access]'),message=ai.querySelector('[data-ai-access-msg]');
 button.addEventListener('click',function(){
  var email=ai.querySelector('[data-ai-email]').value.trim(),honeypot=ai.querySelector('[data-ai-website]').value;
  if(!email){message.textContent='Email required';message.className='cz-msg err';return;}
  if(honeypot){message.textContent='Could not send link';message.className='cz-msg err';return;}
  button.disabled=true;message.textContent='Sending…';message.className='cz-msg';
  RT.post('/booking-suggestions/access',{email:email,website:honeypot}).then(function(){
   message.textContent='If you’re an existing client, a secure link is on its way.';message.className='cz-msg ok';
  }).catch(function(error){
   message.textContent=error.message||'Could not send link';message.className='cz-msg err';button.disabled=false;
  });
 });
}
 function initializeAccessGate(){
  var ai=box.querySelector('[data-ai]');
  if(!ai)return false;
  if(ai.dataset.accessGateInitialized==='1')return true;
  ai.dataset.accessGateInitialized='1';
  ai.hidden=true;
  RT.get('/booking-suggestions/access/status').then(function(result){
   if(!result||result.status!=='eligible')accessForm(ai);
   ai.hidden=false;
  }).catch(function(){accessForm(ai);ai.hidden=false;});
  return true;
 }
 if(!initializeAccessGate())box.addEventListener('cappe:booking-ready',initializeAccessGate,{once:true});
})();
