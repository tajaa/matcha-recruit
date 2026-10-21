(function(){
// A paid story's paywall (services/magazine/pages.py paywall_section): a
// story's page has one; an issue (issue_pages.py) has one per paid story in
// it, all served by this one script with one sign-in. Signs a reader in with
// an emailed code — the session's refresh token is an HttpOnly cookie and
// only the short-lived access token is kept here, in memory, as on /account
// (account.js) — then fills each wall's empty .mz-paid box with that story's
// paid part for a subscriber (GET .../stories/<slug>/paid, never cached), or
// starts their subscription (POST .../magazine/checkout → Stripe).
var RT=window.__CAPPE_RT__,els=document.querySelectorAll('[data-mz-paywall]');
if(!RT||!els.length||!RT.slug||RT.preview)return;
var walls=[];
for(var i=0;i<els.length;i++){var el=els[i],paid=el.nextElementSibling;
walls.push({n:i,el:el,slug:el.getAttribute('data-mz-story'),acts:el.querySelector('[data-mz-actions]'),msg:el.querySelector('[data-mz-msg]'),
paid:paid&&paid.hasAttribute('data-mz-paid')?paid:null});}
var api=RT.api,open=els[0].getAttribute('data-mz-open')==='1',price=els[0].getAttribute('data-mz-price')||'';
var token=null,back=new URLSearchParams(location.search).get('subscribed')==='1';
function esc(s){return RT.esc(s);}
function say(w,t,err){w.msg.className='mz-paywall__msg'+(err?' err':'');w.msg.textContent=t||'';}
function sayAll(t,err){walls.forEach(function(w){if(!w.el.hidden)say(w,t,err);});}
function detail(d){var x=d&&d.detail;if(typeof x==='string')return x;if(x&&x.message)return x.message;return 'Something went wrong. Please try again.';}
function wait(ms){return new Promise(function(done){setTimeout(done,ms);});}
// One refresh at a time, queued with the account page's across tabs: each
// rotates the cookie, and a request carrying the one just replaced is refused.
function refreshOnce(){return fetch(api+'/shopper/web/refresh',{method:'POST',headers:{'X-Cappe-Web':'1'},credentials:'same-origin'})
.then(function(r){if(r.ok)return r.json().then(function(d){token=d.access_token;return true;});
return r.json().catch(function(){return null;}).then(function(d){return !!(d&&d.stale)&&'stale';});}).catch(function(){return false;});}
var refreshing=null;
function refresh(){if(refreshing)return refreshing;
var run=function(){return refreshOnce().then(function(ok){return ok!=='stale'?ok:wait(300).then(refreshOnce).then(function(again){return again===true;});});};
var locks=navigator.locks&&navigator.locks.request?navigator.locks:null;
refreshing=(locks?locks.request('cz-shopper-refresh:'+RT.slug,run):run()).catch(function(){return false;})
.then(function(ok){refreshing=null;return ok;});
return refreshing;}
function call(method,path,data,retried){
var h={'X-Cappe-Web':'1'},sent=token;if(data!==undefined)h['Content-Type']='application/json';if(token)h.Authorization='Bearer '+token;
return fetch(api+path,{method:method,headers:h,credentials:'same-origin',body:data===undefined?undefined:JSON.stringify(data)}).then(function(r){
return r.json().catch(function(){return null;}).then(function(d){
if(r.status===401&&!retried&&sent){return (token&&token!==sent?Promise.resolve(true):refresh()).then(function(ok){
if(!ok){token=null;var gone=new Error('Please sign in again.');gone.status=401;throw gone;}return call(method,path,data,true);});}
if(!r.ok){var e=new Error(detail(d));e.status=r.status;throw e;}return d;});});}

function button(label,solid){return '<button type="button" class="mz-paywall__btn'+(solid?' mz-paywall__btn--solid':'')+'">'+esc(label)+'</button>';}
var offerLabel='Subscribe'+(price?' for '+price+' a month':'');
// Signed out: subscribe (which signs in first) or sign in.
function offer(){walls.forEach(function(w){if(w.el.hidden)return;
w.acts.innerHTML=(open?button(offerLabel,true):'')+
'<p class="mz-paywall__note">'+(open?'Already a subscriber? ':'')+'<a href="#" data-signin>Sign in</a></p>';
if(open)w.acts.querySelector('button').addEventListener('click',function(){signIn(w,true);});
w.acts.querySelector('[data-signin]').addEventListener('click',function(e){e.preventDefault();signIn(w,false);});});}
function form(w,id,input,label,note){
w.acts.innerHTML='<form class="mz-paywall__form"><label class="mz-sr" for="'+id+'">'+esc(label)+'</label>'+input+
'<button type="submit" class="mz-paywall__btn mz-paywall__btn--solid">Continue</button></form><p class="mz-paywall__note">'+note+'</p>';
return w.acts.querySelector('form');}
function signIn(w,thenSubscribe){say(w,'');
var f=form(w,'mz-pw-email-'+w.n,'<input id="mz-pw-email-'+w.n+'" type="email" required autocomplete="email" placeholder="you@example.com">','Your email',
'We’ll email you a 6-digit code. No password.');
f.addEventListener('submit',function(e){e.preventDefault();var email=f.querySelector('input').value.trim();if(!email)return;say(w,'Sending…');
fetch(api+'/shopper/auth/start',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({email:email})})
.then(function(r){if(!r.ok)return r.json().catch(function(){return null;}).then(function(d){throw new Error(detail(d));});say(w,'');code(w,email,thenSubscribe);})
.catch(function(err){say(w,err.message,true);});});}
function code(w,email,thenSubscribe){
var f=form(w,'mz-pw-code-'+w.n,'<input id="mz-pw-code-'+w.n+'" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required placeholder="6-digit code">','Code',
'We sent it to '+esc(email)+'. It works for 10 minutes.');
f.addEventListener('submit',function(e){e.preventDefault();say(w,'Signing in…');
fetch(api+'/shopper/web/verify',{method:'POST',headers:{'Content-Type':'application/json','X-Cappe-Web':'1'},credentials:'same-origin',
body:JSON.stringify({email:email,code:f.querySelector('input').value.trim()})})
.then(function(r){return r.json().catch(function(){return null;}).then(function(d){if(!r.ok)throw new Error(detail(d));token=d.access_token;say(w,'');unlock(thenSubscribe?w:null,0);});})
.catch(function(err){say(w,err.message,true);});});}
// Signed in without access.
function member(){walls.forEach(function(w){if(w.el.hidden)return;
w.acts.innerHTML=open?button(offerLabel,true):'<p class="mz-paywall__note">This magazine isn’t taking new subscribers right now.</p>';
if(open)w.acts.querySelector('button').addEventListener('click',function(){subscribe(w);});});}
// Back from checkout to the story the reader subscribed from.
function subscribe(w){say(w,'Taking you to secure checkout…');
var here=location.origin+location.pathname,at=document.getElementById('mz-s-'+w.slug)?'#mz-s-'+w.slug:'';
call('POST','/magazine/checkout',{success_url:here+'?subscribed=1'+at,cancel_url:here+at})
.then(function(r){location.assign(r.checkout_url);})
.catch(function(err){say(w,err.message,true);member();});}
function fill(w){return call('GET','/stories/'+encodeURIComponent(w.slug)+'/paid').then(function(d){
if(w.paid){w.paid.innerHTML=d.html;w.paid.hidden=false;}w.el.hidden=true;return null;},function(err){return err;});}
// Each paid part for a subscriber; otherwise what the reader can do. Back
// from checkout, the subscription arrives by webhook a few seconds later.
// `from`: the wall whose "Subscribe" signed the reader in.
function unlock(from,tries){
var left=walls.filter(function(w){return !w.el.hidden;});
return Promise.all(left.map(fill)).then(function(errs){errs=errs.filter(Boolean);if(!errs.length)return;
if(errs.some(function(e){return e.status===401;})){token=null;offer();return;}
var other=errs.filter(function(e){return e.status!==403;});
if(other.length){sayAll(other[0].message,true);return;}
if(back&&tries<6){sayAll('Confirming your subscription…');return wait(2000).then(function(){return unlock(null,tries+1);});}
if(back){sayAll('Your payment went through. It can take a minute to show here: refresh the page shortly.');}
if(from&&open)subscribe(from);else member();});}
refresh().then(function(ok){if(ok)unlock(null,0);else offer();});
})();
