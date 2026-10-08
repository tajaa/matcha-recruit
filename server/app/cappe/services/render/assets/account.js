(function(){
// The shopper's account page (/account). Sign in with an emailed code; the
// session's refresh token lives in an HttpOnly cookie the server sets, and
// only the short-lived access token is kept here, in memory. See
// routes/public/shopper_web.py.
var RT=window.__CAPPE_RT__,box=document.querySelector('[data-czaccount]');if(!RT||!box||!RT.slug)return;
var base=RT.api+'/shopper',titleEl=box.querySelector('[data-title]'),bodyEl=box.querySelector('[data-body]');
var token=null,me=null,storeOpen=true,params=new URLSearchParams(location.search);
var wantSub=params.get('subscribe');
function esc(s){return RT.esc(s);}
function day(iso){try{return new Date(iso).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});}catch(e){return '';}}
function msgOf(d){var x=d&&d.detail;if(typeof x==='string')return x;if(x&&x.message)return x.message;if(Array.isArray(x))return x.map(function(e){return e&&e.msg?String(e.msg).replace(/^Value error, /,''):'';}).filter(Boolean).join('. ')||'Please check and try again.';return 'Something went wrong. Please try again.';}
function signedInAs(d){token=d.access_token;me=d.shopper;storeOpen=d.store_open!==false;}
function wait(ms){return new Promise(function(done){setTimeout(done,ms);});}
// true, false (no live session), or 'stale' (another request just rotated
// the cookie; the browser now holds the newer one).
function refreshOnce(){return fetch(base+'/web/refresh',{method:'POST',headers:{'X-Cappe-Web':'1'},credentials:'same-origin'})
.then(function(r){if(r.ok)return r.json().then(function(d){signedInAs(d);return true;});
return r.json().catch(function(){return null;}).then(function(d){return !!(d&&d.stale)&&'stale';});}).catch(function(){return false;});}
// Each refresh rotates the cookie, and a request carrying the cookie another
// one just replaced is refused — so one refresh at a time: shared by this
// page's calls, and queued across tabs where the browser has Web Locks. One
// refused as stale anyway is retried once with the cookie the browser holds.
var refreshing=null;
function refresh(){if(refreshing)return refreshing;
var run=function(){return refreshOnce().then(function(ok){return ok!=='stale'?ok:wait(300).then(refreshOnce).then(function(again){return again===true;});});};
var locks=navigator.locks&&navigator.locks.request?navigator.locks:null;
refreshing=(locks?locks.request('cz-shopper-refresh:'+RT.slug,run):run()).catch(function(){return false;})
.then(function(ok){refreshing=null;return ok;});
return refreshing;}
// Every call carries the access token; one that has expired is renewed from
// the cookie once and retried. A call that set out with a token another call
// has since renewed just retries with the new one.
function call(method,path,data,retried){
var h={'X-Cappe-Web':'1'},sent=token;if(data!==undefined)h['Content-Type']='application/json';if(token)h.Authorization='Bearer '+token;
return fetch(base+path,{method:method,headers:h,credentials:'same-origin',body:data===undefined?undefined:JSON.stringify(data)}).then(function(r){
if(r.status===204)return null;
return r.json().catch(function(){return null;}).then(function(d){
if(r.status===401&&!retried&&sent){return (token&&token!==sent?Promise.resolve(true):refresh()).then(function(ok){if(!ok){signInView();throw new Error('Please sign in again.');}return call(method,path,data,true);});}
if(!r.ok)throw new Error(msgOf(d));return d;});});}

// ── signing in ──
function signInView(note){
token=null;me=null;titleEl.textContent='Sign in';
bodyEl.innerHTML='<p class="cz-order__lead">'+esc(note||(wantSub?'Sign in to start your subscription. We’ll email you a 6-digit code — no password needed.':'We’ll email you a 6-digit code — no password needed.'))+'</p>'+
'<form class="cz-account__form" data-start><input class="cz-field" type="email" required autocomplete="email" placeholder="Your email" aria-label="Your email" data-email />'+
'<button class="cz-btn cz-btn--solid" type="submit">Email me a code</button></form><p class="cz-msg" data-msg role="status"></p>';
var form=bodyEl.querySelector('[data-start]'),msg=bodyEl.querySelector('[data-msg]');
form.addEventListener('submit',function(e){e.preventDefault();var email=bodyEl.querySelector('[data-email]').value.trim();if(!email)return;
msg.className='cz-msg';msg.textContent='Sending…';
fetch(base+'/auth/start',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({email:email})})
.then(function(r){if(!r.ok)return r.json().catch(function(){return null;}).then(function(d){throw new Error(msgOf(d));});codeView(email);})
.catch(function(err){msg.className='cz-msg err';msg.textContent=err.message;});});}
function codeView(email){
titleEl.textContent='Check your email';
bodyEl.innerHTML='<p class="cz-order__lead">We sent a code to '+esc(email)+'. It works for 10 minutes.</p>'+
'<form class="cz-account__form" data-verify><input class="cz-field" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required placeholder="6-digit code" aria-label="Code" data-code />'+
'<button class="cz-btn cz-btn--solid" type="submit">Sign in</button></form><p class="cz-msg" data-msg role="status"></p>'+
'<p><button type="button" class="cz-bag__rm" data-back>Use a different email</button></p>';
var msg=bodyEl.querySelector('[data-msg]');
bodyEl.querySelector('[data-back]').addEventListener('click',function(){signInView();});
bodyEl.querySelector('[data-verify]').addEventListener('submit',function(e){e.preventDefault();var code=bodyEl.querySelector('[data-code]').value.trim();
msg.className='cz-msg';msg.textContent='Signing in…';
fetch(base+'/web/verify',{method:'POST',headers:{'Content-Type':'application/json','X-Cappe-Web':'1'},credentials:'same-origin',body:JSON.stringify({email:email,code:code})})
.then(function(r){return r.json().catch(function(){return null;}).then(function(d){if(!r.ok)throw new Error(msgOf(d));signedInAs(d);signedIn();});})
.catch(function(err){msg.className='cz-msg err';msg.textContent=err.message;});});}

function signedIn(){if(wantSub&&storeOpen)startSubscription();else accountView();}

// ── "Subscribe" from the product panel ──
function startSubscription(){
titleEl.textContent='Starting your subscription…';bodyEl.innerHTML='<p class="cz-order__lead">Taking you to secure checkout.</p>';
var item={product_id:wantSub,quantity:Math.max(1,parseInt(params.get('qty'),10)||1),selected_option_ids:(params.get('opts')||'').split(',').filter(Boolean)};
var here=location.origin+'/account';
call('POST','/me/subscriptions/checkout',{items:[item],interval:params.get('every')==='week'?'week':'month',success_url:here+'?subscribed=1',cancel_url:here})
.then(function(r){window.location=r.checkout_url;})
.catch(function(err){wantSub=null;history.replaceState(null,'','/account');accountView('Your subscription couldn’t be started: '+err.message,true);});}

// ── the account ──
var SUB_LABEL={active:'Active',trialing:'Active',past_due:'Payment failing',unpaid:'Unpaid',paused:'Paused',canceled:'Ended'};
function accountView(note,isError){
if(params.get('subscribed')==='1'&&!note){note='Your subscription is set up. A confirmation is on its way to your email.';}
if(!storeOpen&&!note){note='This store isn’t open right now. You can still see and cancel your subscriptions here.';}
titleEl.textContent=me&&me.name?'Hi, '+me.name:'Your account';
bodyEl.innerHTML=(note?'<p class="cz-msg'+(isError?' err':'')+'">'+esc(note)+'</p>':'')+
'<p class="cz-order__lead">Signed in as '+esc(me?me.email:'')+'. <button type="button" class="cz-bag__rm" data-signout>Sign out</button></p><p class="cz-msg" data-outmsg role="status"></p>'+
'<section class="cz-account__section"><h2 class="cz-order__h">Subscriptions</h2><div data-subs><p class="cz-msg">Loading…</p></div></section>'+
(storeOpen?'<section class="cz-account__section"><h2 class="cz-order__h">Orders</h2><div data-orders><p class="cz-msg">Loading…</p></div></section>'+
'<section class="cz-account__section"><h2 class="cz-order__h">Addresses</h2><div data-addrs><p class="cz-msg">Loading…</p></div></section>':'');
var out=bodyEl.querySelector('[data-signout]'),outMsg=bodyEl.querySelector('[data-outmsg]');
out.addEventListener('click',function(){out.disabled=true;outMsg.className='cz-msg';outMsg.textContent='Signing out…';
// Only a confirmed sign-out says so: a failed one leaves the session (and
// its cookie) alive, and a reload would show the account again.
fetch(base+'/web/logout',{method:'POST',headers:{'X-Cappe-Web':'1'},credentials:'same-origin'})
.then(function(r){if(!r.ok)throw new Error();signInView('You’re signed out.');})
.catch(function(){out.disabled=false;outMsg.className='cz-msg err';outMsg.textContent='Couldn’t sign you out. Check your connection and try again.';});});
loadSubs();if(storeOpen){loadOrders(null);loadAddrs();}}

// Every subscription that isn't an abandoned checkout, page by page: the
// server drops those before its limit, so an older one that still bills is
// never pushed off the list by newer abandoned ones.
var SUB_PAGE=100,SUB_PAGES=20;
function allSubs(offset,acc){return call('GET','/me/subscriptions?include_abandoned=false&limit='+SUB_PAGE+'&offset='+offset).then(function(rows){
acc=acc.concat(rows||[]);return (rows||[]).length<SUB_PAGE||offset/SUB_PAGE+1>=SUB_PAGES?acc:allSubs(offset+SUB_PAGE,acc);});}
function loadSubs(){var el=bodyEl.querySelector('[data-subs]');
allSubs(0,[]).then(function(rows){
rows=rows.filter(function(s){return SUB_LABEL[s.status];});
if(!rows.length){el.innerHTML='<p class="cz-msg">No subscriptions.</p>';return;}
var live=rows.some(function(s){return s.status!=='canceled';});
el.innerHTML='<ul class="cz-order__items">'+rows.map(function(s){
var what=(s.items||[]).map(function(i){return (i.quantity>1?i.quantity+' × ':'')+(i.title||'Item');}).join(', ');
var ends=s.cancel_at_period_end&&s.current_period_end,when=s.current_period_end?day(s.current_period_end):'';
var state=s.status==='canceled'?'Ended':(ends?'Ends '+when:(SUB_LABEL[s.status]+(when?' · renews '+when:'')));
var btn=s.status==='canceled'?'':(ends?(storeOpen?'<button type="button" class="cz-btn cz-btn--ghost" data-resume="'+esc(s.id)+'">Keep it</button>':''):'<button type="button" class="cz-btn cz-btn--ghost" data-cancel="'+esc(s.id)+'">Cancel</button>');
return '<li class="cz-order__item"><div class="cz-order__line"><span>'+esc(what)+'<span class="cz-order__opts">'+esc(RT.money(s.total_cents,s.currency))+' every '+esc(s.interval)+' · '+esc(state)+'</span></span>'+btn+'</div></li>';}).join('')+'</ul>'+
(live&&storeOpen?'<p><button type="button" class="cz-btn cz-btn--ghost" data-card>Update the card it charges</button></p>':'')+'<p class="cz-msg" data-submsg role="status"></p>';
var m=el.querySelector('[data-submsg]');
el.querySelectorAll('[data-cancel]').forEach(function(b){b.addEventListener('click',function(){if(!confirm('Cancel this subscription? It stops before the next charge.'))return;
b.disabled=true;call('POST','/me/subscriptions/'+encodeURIComponent(b.getAttribute('data-cancel'))+'/cancel').then(loadSubs).catch(function(err){b.disabled=false;m.className='cz-msg err';m.textContent=err.message;});});});
el.querySelectorAll('[data-resume]').forEach(function(b){b.addEventListener('click',function(){b.disabled=true;
call('POST','/me/subscriptions/'+encodeURIComponent(b.getAttribute('data-resume'))+'/resume').then(loadSubs).catch(function(err){b.disabled=false;m.className='cz-msg err';m.textContent=err.message;});});});
var card=el.querySelector('[data-card]');if(card)card.addEventListener('click',function(){card.disabled=true;
call('POST','/me/billing-portal',{return_url:location.origin+'/account'}).then(function(r){window.location=r.url;}).catch(function(err){card.disabled=false;m.className='cz-msg err';m.textContent=err.message;});});
}).catch(function(err){el.innerHTML='<p class="cz-msg err">'+esc(err.message)+'</p>';});}

function loadOrders(cursor){var el=bodyEl.querySelector('[data-orders]');
call('GET','/me/orders?limit=10'+(cursor?'&cursor='+encodeURIComponent(cursor):'')).then(function(page){
var rows=(page&&page.orders)||[];
if(!rows.length&&!cursor){el.innerHTML='<p class="cz-msg">No orders yet.</p>';return;}
var html=rows.map(function(o){var what=(o.items||[]).map(function(i){return (i.quantity>1?i.quantity+' × ':'')+(i.title||'Item');}).join(', ');
return '<li class="cz-order__item"><div class="cz-order__line"><span>'+esc(day(o.created_at))+' · '+esc(o.status)+'<span class="cz-order__opts">'+esc(what)+'</span></span>'+
'<span>'+esc(RT.money(o.total_cents!=null?o.total_cents:o.subtotal_cents,o.currency))+' <a href="/order/'+encodeURIComponent(o.order_token)+'">View</a></span></div></li>';}).join('');
var list=el.querySelector('ul');if(!cursor||!list){el.innerHTML='<ul class="cz-order__items">'+html+'</ul>';list=el.querySelector('ul');}else{list.insertAdjacentHTML('beforeend',html);}
var more=el.querySelector('[data-more]');if(more)more.remove();
if(page&&page.next_cursor){el.insertAdjacentHTML('beforeend','<p><button type="button" class="cz-btn cz-btn--ghost" data-more>Show more</button></p>');
el.querySelector('[data-more]').addEventListener('click',function(){loadOrders(page.next_cursor);});}
}).catch(function(err){el.innerHTML='<p class="cz-msg err">'+esc(err.message)+'</p>';});}

var ADDR_FIELDS=[['name','Full name',1],['line1','Address',1],['line2','Apartment, suite (optional)',0],['city','City',1],['region','State / region',0],['postal_code','Postal code',1],['country','Country code (e.g. US)',1],['phone','Phone (optional)',0]];
function loadAddrs(){var el=bodyEl.querySelector('[data-addrs]');
call('GET','/me/addresses').then(function(rows){rows=rows||[];
el.innerHTML=(rows.length?'<ul class="cz-order__items">'+rows.map(function(a){
var text=[a.name,a.line1,a.line2,[a.city,a.region,a.postal_code].filter(Boolean).join(' '),a.country].filter(Boolean).join(', ');
return '<li class="cz-order__item"><div class="cz-order__line"><span>'+esc(text)+(a.is_default?'<span class="cz-order__opts">Default — subscriptions ship here</span>':'')+'</span><span>'+
(a.is_default?'':'<button type="button" class="cz-bag__rm" data-default="'+esc(a.id)+'">Make default</button> ')+'<button type="button" class="cz-bag__rm" data-del="'+esc(a.id)+'">Delete</button></span></div></li>';}).join('')+'</ul>':'<p class="cz-msg">No saved addresses.</p>')+
'<form class="cz-account__addr" data-addform hidden>'+ADDR_FIELDS.map(function(f){return '<input class="cz-field" data-f="'+f[0]+'" placeholder="'+esc(f[1])+'" aria-label="'+esc(f[1])+'"'+(f[2]?' required':'')+(f[0]==='country'?' maxlength="2" value="US"':'')+' />';}).join('')+
'<label class="cz-label"><input type="checkbox" data-isdefault'+(rows.length?'':' checked')+' /> Make this my default address</label>'+
'<button class="cz-btn cz-btn--solid" type="submit">Save address</button></form>'+
'<p><button type="button" class="cz-btn cz-btn--ghost" data-addopen>Add an address</button></p><p class="cz-msg" data-addrmsg role="status"></p>';
var m=el.querySelector('[data-addrmsg]'),form=el.querySelector('[data-addform]');
function fail(err){m.className='cz-msg err';m.textContent=err.message;}
el.querySelector('[data-addopen]').addEventListener('click',function(){form.hidden=false;this.hidden=true;});
form.addEventListener('submit',function(e){e.preventDefault();var b={};form.querySelectorAll('[data-f]').forEach(function(i){var v=i.value.trim();b[i.getAttribute('data-f')]=v||null;});
b.country=(b.country||'').toUpperCase();b.is_default=form.querySelector('[data-isdefault]').checked;
call('POST','/me/addresses',b).then(loadAddrs).catch(fail);});
el.querySelectorAll('[data-del]').forEach(function(btn){btn.addEventListener('click',function(){if(!confirm('Delete this address?'))return;
call('DELETE','/me/addresses/'+encodeURIComponent(btn.getAttribute('data-del'))).then(loadAddrs).catch(fail);});});
el.querySelectorAll('[data-default]').forEach(function(btn){btn.addEventListener('click',function(){var a=rows.filter(function(r){return r.id===btn.getAttribute('data-default');})[0];if(!a)return;
var b={};ADDR_FIELDS.forEach(function(f){b[f[0]]=a[f[0]];});b.label=a.label;b.is_default=true;
call('PATCH','/me/addresses/'+encodeURIComponent(a.id),b).then(loadAddrs).catch(fail);});});
}).catch(function(err){el.innerHTML='<p class="cz-msg err">'+esc(err.message)+'</p>';});}

refresh().then(function(ok){if(ok)signedIn();else signInView();});
})();
