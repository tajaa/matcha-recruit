(function(){
var RT=window.__CAPPE_RT__,pv=RT&&RT.preview,edit=document.body.classList.contains('cz-editable');
var slug=((window.__CAPPE__||{}).slug)||'';
function k(s){return 'czp:'+slug+':'+s;}
var bar=document.getElementById('czbar');
if(bar){var bx=bar.querySelector('[data-czclose]');
  if(bx){if(!pv){try{if(localStorage.getItem(k('bar'))==='1')bar.setAttribute('hidden','');}catch(e){}}
    bx.addEventListener('click',function(){bar.setAttribute('hidden','');try{localStorage.setItem(k('bar'),'1');}catch(e){}});}}
var pop=document.getElementById('czpop');
if(pop){
  var trig=pop.getAttribute('data-trigger')||'load',
      delay=parseInt(pop.getAttribute('data-delay'),10)||0,
      freq=pop.getAttribute('data-freq')||'session',shown=false;
  function seen(){try{return (freq==='once'?localStorage:sessionStorage).getItem(k('pop'))==='1';}catch(e){return false;}}
  function mark(){try{(freq==='once'?localStorage:sessionStorage).setItem(k('pop'),'1');}catch(e){}}
  function open(){if(shown)return;if(!pv&&freq!=='always'&&seen())return;shown=true;
    pop.removeAttribute('hidden');requestAnimationFrame(function(){pop.classList.add('cz-in');});if(!pv)mark();}
  function close(){pop.classList.remove('cz-in');setTimeout(function(){pop.setAttribute('hidden','');},300);}
  [].slice.call(pop.querySelectorAll('[data-czclose]')).forEach(function(el){el.addEventListener('click',close);});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!pop.hasAttribute('hidden'))close();});
  if(pv){if(!edit)open();}
  else if(trig==='delay'){setTimeout(open,Math.max(0,delay)*1000);}
  else if(trig==='exit'){var armed=false;setTimeout(function(){armed=true;},2000);
    document.addEventListener('mouseout',function(e){if(armed&&!e.relatedTarget&&e.clientY<=0)open();});
    setTimeout(open,25000);}
  else{setTimeout(open,500);}
  var nf=pop.querySelector('[data-cznews]');
  if(nf&&RT){var inp=nf.querySelector('input'),btn=nf.querySelector('button'),msg=pop.querySelector('[data-czmsg]');
    btn.addEventListener('click',function(){var email=(inp.value||'').trim();
      if(!email){if(msg){msg.textContent='Email required';msg.className='cz-msg err';}return;}
      btn.disabled=true;RT.post('/subscribe',{email:email}).then(function(){
        nf.innerHTML='<p class="cz-msg ok">You are subscribed!</p>';
      }).catch(function(e){btn.disabled=false;if(msg){msg.textContent=e.message;msg.className='cz-msg err';}});});}
  var cp=pop.querySelector('[data-czcopy]');
  if(cp){cp.addEventListener('click',function(){var code=cp.getAttribute('data-code')||'';
    try{navigator.clipboard.writeText(code);cp.textContent='Copied!';setTimeout(function(){cp.textContent='Copy';},1500);}catch(e){}});}
}})();