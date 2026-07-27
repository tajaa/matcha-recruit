(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
if(RT.preview){box.innerHTML='<p style="color:var(--muted)">Visitors pick from your open times here once your site is live.</p>';return;}
var selLoc='';
function locP(){return selLoc?('location_id='+encodeURIComponent(selLoc)):'';}
function qjoin(){var p=[];for(var i=0;i<arguments.length;i++){if(arguments[i])p.push(arguments[i]);}return p.length?('?'+p.join('&')):'';}
RT.get('/locations').catch(function(){return [];}).then(function(locs){locs=locs||[];
if(locs.length>1){box.innerHTML='<p class="cz-label">Choose a location</p><div class="cz-staffrow">'+
locs.map(function(l){return '<button type="button" class="cz-staff" data-loc-id="'+RT.esc(l.id)+'">'+RT.esc(l.name)+(l.address?'<span style="display:block;font-size:.75em;color:var(--muted)">'+RT.esc(l.address)+'</span>':'')+'</button>';}).join('')+'</div>';
box.querySelectorAll('[data-loc-id]').forEach(function(b){b.addEventListener('click',function(){selLoc=b.getAttribute('data-loc-id');start();});});}
else{selLoc=locs.length===1?locs[0].id:'';start();}});
function start(){
Promise.all([RT.get('/booking-types'+qjoin(locP())),RT.get('/rider').catch(function(){return {items:[]};}),RT.get('/staff'+qjoin(locP())).catch(function(){return [];})]).then(function(r){
var types=r[0],rider=(r[1]&&r[1].items)||[],staffList=r[2]||[];
if(!types.length){box.innerHTML='<p style="color:var(--muted)">No appointments available.</p>';return;}
var byId={};types.forEach(function(t){byId[t.id]=t;});
var staffById={};staffList.forEach(function(s){staffById[s.id]=s;});
var selStaff=null;
function priceLabel(t){if(!t.price_cents)return 'Free';var m=RT.money(t.price_cents,'USD');return t.pricing_mode==='hourly'?m+'/hr':m;}
var reqRider=rider.filter(function(i){return i.is_required;});
var riderHtml='';
if(rider.length){riderHtml='<div class="cz-rider" style="border:1px solid var(--line);border-radius:var(--radius);padding:.85rem 1rem;margin:.5rem 0;font-size:.9rem">'+
'<div style="font-weight:600;margin-bottom:.4rem">Booking requirements</div><ul style="margin:0 0 .5rem;padding-left:1.1rem;color:var(--muted)">'+
rider.map(function(i){return '<li>'+RT.esc(i.label)+(i.detail?' — '+RT.esc(i.detail):'')+(i.is_required?'':' (optional)')+'</li>';}).join('')+'</ul>'+
(reqRider.length?'<label style="display:flex;gap:.5rem;align-items:flex-start"><input type="checkbox" data-ack /> <span>I have read and agree to these requirements.</span></label>':'')+'</div>';}
box.innerHTML='<select class="cz-field" data-bt>'+types.map(function(t){return '<option value="'+RT.esc(t.id)+'">'+RT.esc(t.name)+' ('+t.duration_minutes+' min) · '+priceLabel(t)+'</option>';}).join('')+'</select>'+
'<div data-staff style="margin:.45rem 0"></div>'+
'<div data-slots style="margin:.5rem 0"><p style="color:var(--muted)">Loading times…</p></div>'+
'<input class="cz-field" type="email" data-email placeholder="Your email" /><input class="cz-field" type="text" data-name placeholder="Your name" />'+
riderHtml+
'<button class="cz-btn cz-btn--solid cz-btn--block" data-go disabled>Select a time</button><p class="cz-msg"></p>';
var sb=box.querySelector('[data-go]'),msg=box.querySelector('.cz-msg'),btSel=box.querySelector('[data-bt]'),slotWrap=box.querySelector('[data-slots]'),staffWrap=box.querySelector('[data-staff]'),sel=null;
function cur(){return byId[btSel.value];}
function renderStaff(t){selStaff=null;var ids=(t&&t.staff_ids)||[];if(!ids.length){staffWrap.innerHTML='';return;}
staffWrap.innerHTML='<p class="cz-label">With</p><div class="cz-staffrow"><button type="button" class="cz-staff cz-staff--on" data-staff-id="">Any available</button>'+
ids.map(function(id){var s=staffById[id];if(!s)return '';var iu=RT.url(s.image_url);return '<button type="button" class="cz-staff" data-staff-id="'+RT.esc(id)+'">'+(iu?'<img src="'+RT.esc(iu)+'" alt="" />':'')+RT.esc(s.name)+'</button>';}).join('')+'</div>';
staffWrap.querySelectorAll('.cz-staff').forEach(function(b){b.addEventListener('click',function(){staffWrap.querySelectorAll('.cz-staff').forEach(function(x){x.classList.remove('cz-staff--on');});b.classList.add('cz-staff--on');selStaff=b.getAttribute('data-staff-id')||null;loadSlots();});});}
function loadSlots(){sel=null;sb.disabled=true;sb.textContent='Select a time';slotWrap.innerHTML='<p style="color:var(--muted)">Loading times…</p>';
var t=cur();if(!t)return;
RT.get('/booking-types/'+encodeURIComponent(t.id)+'/slots'+qjoin(locP(),selStaff?('staff_id='+encodeURIComponent(selStaff)):'')).then(function(d){var slots=(d&&d.slots)||[];
if(!slots.length){slotWrap.innerHTML='<p style="color:var(--muted)">No open times in the next few weeks. Please check back soon.</p>';return;}
var days=[],byDay={};slots.forEach(function(s){if(!byDay[s.date]){byDay[s.date]=[];days.push(s.date);}byDay[s.date].push(s);});
// One price line when every slot costs the same; otherwise show price per time.
var uniform=slots.every(function(s){return s.price_cents===slots[0].price_cents;});
var priceNote=(uniform&&slots[0].price_cents)?(' · '+RT.money(slots[0].price_cents,'USD')+(t.pricing_mode==='hourly'?'/hr':'')):'';
var tzNote=d.timezone?(' · times in '+RT.esc(d.timezone)):'';
var discNote=d.discount_percent?(' · <span style="color:var(--brand)">'+d.discount_percent+'% off</span>'):'';
slotWrap.innerHTML='<p class="cz-label">Pick a day'+tzNote+priceNote+discNote+'</p>'+
'<div class="cz-daystrip">'+days.map(function(dt,i){return '<button type="button" class="cz-day" data-day="'+i+'">'+RT.esc(byDay[dt][0].day_label)+'<span>'+byDay[dt].length+' open</span></button>';}).join('')+'</div>'+
'<div class="cz-times" data-times></div>';
var timesWrap=slotWrap.querySelector('[data-times]'),dayBtns=slotWrap.querySelectorAll('.cz-day');
function showDay(i){sel=null;sb.disabled=true;sb.textContent='Select a time';
dayBtns.forEach(function(b,j){b.classList.toggle('cz-day--on',j===i);});
timesWrap.innerHTML=byDay[days[i]].map(function(s){var pl=(!uniform&&s.price_cents)?(' · '+RT.money(s.price_cents,'USD')):'';
return '<button type="button" class="cz-slot" data-start="'+RT.esc(s.start)+'" data-end="'+RT.esc(s.end)+'">'+RT.esc(s.time_label)+pl+'</button>';}).join('');
timesWrap.querySelectorAll('.cz-slot').forEach(function(btn){btn.addEventListener('click',function(){
timesWrap.querySelectorAll('.cz-slot').forEach(function(b){b.classList.remove('cz-slot--on');});
btn.classList.add('cz-slot--on');
sel={start:btn.getAttribute('data-start'),end:btn.getAttribute('data-end')};sb.disabled=false;sb.textContent='Request booking';});});}
dayBtns.forEach(function(b,i){b.addEventListener('click',function(){showDay(i);});});showDay(0);
}).catch(function(){slotWrap.innerHTML='<p style="color:var(--muted)">Could not load times.</p>';});}
function onType(){renderStaff(cur());loadSlots();}
btSel.addEventListener('change',onType);onType();
sb.addEventListener('click',function(){var t=cur(),email=box.querySelector('[data-email]').value.trim();
if(!sel){msg.textContent='Pick a time';msg.className='cz-msg err';return;}
if(!email){msg.textContent='Email required';msg.className='cz-msg err';return;}
var ackEl=box.querySelector('[data-ack]');if(ackEl&&!ackEl.checked){msg.textContent='Please agree to the requirements';msg.className='cz-msg err';return;}
var body={booking_type_id:t.id,starts_at:sel.start,customer_email:email,customer_name:box.querySelector('[data-name]').value.trim(),rider_acknowledged:ackEl?ackEl.checked:false};
if(t.pricing_mode==='hourly'&&sel.end)body.ends_at=sel.end;
if(selStaff)body.staff_id=selStaff;
if(selLoc)body.location_id=selLoc;
sb.disabled=true;msg.textContent='Requesting…';msg.className='cz-msg';
RT.post('/bookings',body).then(function(res){var price=res.quoted_price_cents?(' — '+RT.money(res.quoted_price_cents,'USD')):'';
var note=res.requires_approval?'Request sent for '+RT.esc(new Date(res.starts_at).toLocaleString())+price+'. The host will review and confirm by email.':'Booked for '+RT.esc(new Date(res.starts_at).toLocaleString())+price+'. A confirmation is on its way.';
box.innerHTML='<p class="cz-msg ok">'+note+'</p>';
}).catch(function(e){sb.disabled=false;sb.textContent='Request booking';msg.textContent=e.message;msg.className='cz-msg err';});});
}).catch(function(){box.innerHTML='<p style="color:var(--muted)">Unable to load.</p>';});}})();