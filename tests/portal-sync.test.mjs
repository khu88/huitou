import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../portal.js',import.meta.url),'utf8');
const copy=value=>structuredClone(value);
const reminder=(id,conferenceId,patch={})=>({
  id,conferenceId,trackName:'Main',kind:'full',deadline:'2027-01-01T00:00:00Z',
  leadMinutes:1440,enabled:true,...patch,
});
const state=()=>({
  favorites:['acl'],reminders:[reminder('acl-main','acl')],
  settings:{theme:'light',fontSize:'standard',timezone:'UTC',sound:false,reducedMotion:false},
  relax:{woodfish:8,accepts:2,amen:3},
});
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}

// Run the actual module with a small in-memory HTTP contract. Tests can change
// server state independently, hold responses, or reject a write. This is not a
// substitute for the backend transaction tests or real browser verification.
async function harness({signedIn=true,legacy=null,extensions={}}={}){
  const users=new Map([['first',state()],['second',{...state(),favorites:['neurips'],reminders:[]}]]);
  const scripts=[],calls=[],plans=[],optionalPlans=[],events=[],domListeners=new Map(),windowListeners=new Map(),storage=new Map();
  if(legacy){storage.set('conf-atlas-guest',JSON.stringify(legacy));storage.set('conf-atlas-favorites',JSON.stringify(legacy.favorites));}
  const elements=new Map(),timers=new Map();let sessionUser=signedIn?'first':null,timerId=0,latest,relaxControls,relaxFailure=false;
  const element=selector=>{
    if(!elements.has(selector))elements.set(selector,{
      dataset:{},innerHTML:'',textContent:'',hidden:false,querySelector:()=>null,replaceChildren(){this.innerHTML='';},
      classList:{toggle(){}},focus(){},
    });
    return elements.get(selector);
  };
  const response=(payload,status=200)=>({ok:status>=200&&status<300,status,json:async()=>copy(payload)});
  async function fetch(path,options={}){
    const body=options.body?JSON.parse(options.body):undefined,account=sessionUser;
    calls.push({path,body,account,method:options.method||'GET'});
    if(path==='/api/session')return response(account?{user:{id:account,displayName:account,username:account,role:'user'},csrfToken:'test-csrf',state:users.get(account),accountExtension:extensions[account]}:{user:null,csrfToken:null,state:null});
    if(path==='/api/optional/read'){const plan=optionalPlans.shift();plan.started.resolve();await plan.gate.promise;return response({error:{code:'authentication_required',message:'expired'}},401);}
    if(path==='/api/state/sync'){
      const plan=plans.shift()||{},stored=users.get(account);plan.started?.resolve();
      if(plan.error){
        if(plan.gate)await plan.gate.promise;
        return response({error:{code:'temporary_failure',message:'模拟保存失败'}},503);
      }
      if(body.favorites){
        stored.favorites=[...new Set([...stored.favorites,...body.favorites.add])].filter(id=>!body.favorites.remove.includes(id));
        stored.reminders=stored.reminders.map(r=>body.favorites.remove.includes(r.conferenceId)?{...r,enabled:false}:r);
      }
      if(body.reminders){
        const upserts=new Map(body.reminders.upsert.map(r=>[r.id,r]));
        stored.reminders=stored.reminders.filter(r=>!body.reminders.remove.includes(r.id)).map(r=>upserts.get(r.id)||r);
        for(const item of body.reminders.upsert)if(!stored.reminders.some(r=>r.id===item.id))stored.reminders.push(item);
      }
      const result={state:copy(stored)};
      if(plan.gate)await plan.gate.promise;
      return response(result);
    }
    if(path==='/api/relax/increment'){
      if(relaxFailure){relaxFailure=false;return response({error:{code:'count_failure',message:'模拟计数保存失败'}},503);}
      const stored=users.get(account);for(const [key,value] of Object.entries(body))stored.relax[key]+=value;
      return response({relax:stored.relax});
    }
    if(path==='/api/state'){
      const stored=users.get(account);if(body.settings)Object.assign(stored.settings,body.settings);
      return response({state:stored});
    }
    throw new Error('Unexpected test request: '+path);
  }
  const context=vm.createContext({
    structuredClone,console,fetch,CustomEvent:class{constructor(type){this.type=type;}},
    setTimeout:callback=>{timers.set(++timerId,callback);return timerId;},clearTimeout:id=>timers.delete(id),
    matchMedia:()=>({matches:false,addEventListener(){}}),
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},
    document:{documentElement:{dataset:{}},head:{append:node=>scripts.push(node)},createElement:tag=>({tag,remove(){this.removed=true;}}),querySelector:element,addEventListener:(name,fn)=>domListeners.set(name,fn),dispatchEvent:event=>{events.push(event.type);return true;}},
    window:{addEventListener:(name,fn)=>windowListeners.set(name,fn),ConfRelax:{
      html:()=>'',leave(){},mount:controls=>{relaxControls=controls;},
    }},
  });
  vm.runInContext(source,context,{filename:'portal.js'});
  const portal=context.window.ConfPortal;
  await portal.init(value=>{latest=value;});
  return {
    portal,calls,users,storage,events,scripts,element,get latest(){return latest;},
    server:()=>users.get(sessionUser),
    nextWrite({hold=false,error=false}={}){
      const plan={error,started:deferred(),gate:hold?deferred():null};plans.push(plan);
      return {started:plan.started.promise,release:()=>plan.gate?.resolve()};
    },
    async switchAccount(id){sessionUser=id;await portal.init();},
    tap(){portal.render('relax');relaxControls.increment('woodfish');},
    pagehide(){windowListeners.get('pagehide')();},
    async setting(key,value){await domListeners.get('click')({target:{closest:selector=>selector==='[data-portal]'?{dataset:{portal:'setting',key,value}}:null}});},
    async importFavorites(){await domListeners.get('click')({target:{closest:selector=>selector==='[data-portal]'?{dataset:{portal:'import-favorites'},isConnected:false}:null}});},
    failNextRelax(){relaxFailure=true;},
    holdOptionalFailure(){const plan={started:deferred(),gate:deferred()};optionalPlans.push(plan);return {started:plan.started.promise,release:()=>plan.gate.resolve()};},
  };
}
const favorites=h=>Array.from(h.portal.getFavorites());
const syncCalls=h=>h.calls.filter(call=>call.path==='/api/state/sync');

test('a browser favorite edit preserves a conference and reminder added concurrently from WeChat',async()=>{
  const h=await harness();
  h.server().favorites.push('iclr');h.server().reminders.push(reminder('iclr-main','iclr'));
  await h.portal.setFavorites(['acl','aaai']);
  assert.deepEqual(syncCalls(h).at(-1).body,{favorites:{add:['aaai'],remove:[]}});
  assert.deepEqual(favorites(h),['acl','iclr','aaai']);
  assert.deepEqual(h.portal.getReminders().map(r=>r.id),['acl-main','iclr-main']);
  assert.equal(h.calls.filter(call=>call.path==='/api/state').length,0,'lists must not use replacement writes');
});

test('reminder edits only upsert the target and preserve unseen server reminders',async()=>{
  const h=await harness();h.server().reminders.push(reminder('iclr-main','iclr'));
  await h.portal.setReminders(h.portal.getReminders().map(r=>({...r,enabled:false})));
  const delta=syncCalls(h).at(-1).body;
  assert.equal(delta.reminders.upsert.length,1);assert.equal(delta.reminders.upsert[0].id,'acl-main');
  assert.deepEqual(delta.reminders.remove,[]);
  assert.deepEqual(h.portal.getReminders().map(r=>[r.id,r.enabled]),[['acl-main',false],['iclr-main',true]]);
  await h.portal.setReminders(h.portal.getReminders().filter(r=>r.id!=='acl-main'));
  assert.deepEqual(syncCalls(h).at(-1).body,{reminders:{upsert:[],remove:['acl-main']}});
});

test('removing a favorite leaves unrelated WeChat additions intact and pauses all its latest reminders',async()=>{
  const h=await harness();h.server().favorites.push('iclr');
  h.server().reminders.push(reminder('acl-extra','acl'),reminder('iclr-main','iclr'));
  await h.portal.setFavorites([]);
  assert.deepEqual(syncCalls(h).at(-1).body,{favorites:{add:[],remove:['acl']}});
  assert.deepEqual(favorites(h),['iclr']);
  assert.deepEqual(h.portal.getReminders().map(r=>[r.id,r.enabled]),[['acl-main',false],['acl-extra',false],['iclr-main',true]]);
});

test('saving a reminder explicitly re-favorites its conference after an unseen remote unfavorite',async()=>{
  const h=await harness();h.server().favorites=[];
  await h.portal.setReminders([reminder('acl-main','acl',{leadMinutes:4320})],'acl');
  assert.deepEqual(syncCalls(h).at(-1).body.favorites,{add:['acl'],remove:[]});
  assert.deepEqual(favorites(h),['acl']);
});

test('two fast queued edits keep the latest local intent while earlier replies are delayed',async()=>{
  const h=await harness();const held=h.nextWrite({hold:true});
  const first=h.portal.setFavorites(['acl','aaai']);await held.started;
  const second=h.portal.setFavorites(['aaai','cvpr']);
  assert.deepEqual(favorites(h),['aaai','cvpr']);
  held.release();await Promise.all([first,second]);
  assert.deepEqual(syncCalls(h).map(call=>call.body),[
    {favorites:{add:['aaai'],remove:[]}},
    {favorites:{add:['cvpr'],remove:['acl']}},
  ]);
  assert.deepEqual(favorites(h),['aaai','cvpr']);assert.deepEqual(h.server().favorites,['aaai','cvpr']);
});

test('a rejected final edit rolls back to the latest confirmed server lists',async()=>{
  const h=await harness();h.server().favorites.push('iclr');
  await h.portal.setFavorites(['acl','aaai']);
  h.nextWrite({error:true});
  await assert.rejects(h.portal.setFavorites(['aaai']),/模拟保存失败/);
  assert.deepEqual(favorites(h),['acl','iclr','aaai']);
  assert.deepEqual(h.portal.getReminders(),h.server().reminders);
});

test('an earlier rejected write does not prevent a later queued edit from reaching the server',async()=>{
  const h=await harness();const held=h.nextWrite({hold:true,error:true});
  const failed=assert.rejects(h.portal.setFavorites(['acl','aaai']),/模拟保存失败/);
  await held.started;const later=h.portal.setFavorites(['acl','aaai','cvpr']);
  held.release();await Promise.all([failed,later]);
  assert.deepEqual(favorites(h),['acl','cvpr'],'the failed AAAI change must not be reported as saved');
  assert.deepEqual(syncCalls(h).at(-1).body,{favorites:{add:['cvpr'],remove:[]}});
});

test('an old account reply cannot replace the current account lists',async()=>{
  const h=await harness();const held=h.nextWrite({hold:true});
  const pending=h.portal.setFavorites(['acl','aaai']);await held.started;
  await h.switchAccount('second');assert.deepEqual(favorites(h),['neurips']);
  held.release();await pending;
  assert.equal(h.portal.getScope(),'second');assert.deepEqual(favorites(h),['neurips']);
  assert.deepEqual(Array.from(h.portal.getReminders()),[]);
  assert.deepEqual(h.users.get('first').favorites,['acl','aaai'],'the requested old-account write may finish without leaking its result');
});

test('list responses preserve local settings and unsaved relax taps',async()=>{
  const h=await harness();h.tap();h.server().settings.theme='dark';h.server().relax.woodfish=50;
  await h.portal.setFavorites(['acl','aaai']);
  assert.equal(h.portal.getSettings().theme,'light');assert.equal(h.latest.relax.woodfish,9);
  assert.equal(h.calls.some(call=>call.path==='/api/relax/increment'),false,'list saving must not flush or replace pending taps');
});

test('refreshing from a stale query response does not overwrite a list write still pending',async()=>{
  const h=await harness();const stale=copy(h.server()),held=h.nextWrite({hold:true});
  const pending=h.portal.setFavorites(['acl','aaai']);await held.started;
  await h.portal.refreshState(stale,'first');assert.deepEqual(favorites(h),['acl','aaai']);
  held.release();await pending;assert.deepEqual(favorites(h),['acl','aaai']);
});

test('the next synchronization can recover after a previously reported save failure',async()=>{
  const h=await harness();h.nextWrite({error:true});
  await assert.rejects(h.portal.setFavorites(['acl','aaai']),/模拟保存失败/);
  await h.portal.prepareSync();
  await h.portal.refreshState();
  assert.deepEqual(favorites(h),['acl']);
});


test('synchronization does not hide a failure in a list write that was still pending',async()=>{
  const h=await harness(),held=h.nextWrite({hold:true,error:true});
  const failedWrite=assert.rejects(h.portal.setFavorites(['acl','aaai']),/模拟保存失败/);
  await held.started;
  const failedSync=assert.rejects(h.portal.prepareSync(),/模拟保存失败/);
  held.release();await Promise.all([failedWrite,failedSync]);
});

test('synchronization propagates a new queued failure after the initially awaited write',async()=>{
  const h=await harness(),held=h.nextWrite({hold:true});
  const first=h.portal.setFavorites(['acl','aaai']);await held.started;
  const failedSync=assert.rejects(h.portal.prepareSync(),/模拟保存失败/);
  h.nextWrite({error:true});
  const failedWrite=assert.rejects(h.portal.setFavorites(['acl','aaai','cvpr']),/模拟保存失败/);
  held.release();await Promise.all([first,failedWrite,failedSync]);
});

test('recovering an old failure does not swallow a new relax flush failure',async()=>{
  const h=await harness();h.nextWrite({error:true});
  await assert.rejects(h.portal.setFavorites(['acl','aaai']),/模拟保存失败/);
  h.tap();h.failNextRelax();
  await assert.rejects(h.portal.prepareSync(),/模拟计数保存失败/);
});

test('signed-out visitors cannot expose or mutate legacy favorites and reminders',async()=>{
  const legacy=state(),h=await harness({signedIn:false,legacy});
  assert.deepEqual(favorites(h),[]);assert.deepEqual(Array.from(h.portal.getReminders()),[]);
  assert.deepEqual(Array.from(h.latest.favorites),[]);assert.deepEqual(Array.from(h.latest.reminders),[]);
  await assert.rejects(h.portal.setFavorites(['cvpr']),/请先登录/);
  await assert.rejects(h.portal.setReminders([reminder('cvpr-main','cvpr')],'cvpr'),/请先登录/);
  assert.equal(syncCalls(h).length,0);
  assert.deepEqual(h.events,['conf-login-required','conf-login-required']);
  assert.deepEqual(JSON.parse(h.storage.get('conf-atlas-guest')),legacy);
  assert.deepEqual(favorites(h),[]);
});

test('guest settings and relax saving preserve hidden legacy personal lists',async()=>{
  const legacy=state(),h=await harness({signedIn:false,legacy});
  await h.setting('theme','dark');h.tap();h.pagehide();
  const stored=JSON.parse(h.storage.get('conf-atlas-guest'));
  assert.equal(stored.settings.theme,'dark');assert.equal(stored.relax.woodfish,9);
  assert.deepEqual(stored.favorites,legacy.favorites);assert.deepEqual(stored.reminders,legacy.reminders);
  assert.deepEqual(JSON.parse(h.storage.get('conf-atlas-favorites')),legacy.favorites);
  assert.deepEqual(Array.from(h.latest.favorites),[]);assert.deepEqual(Array.from(h.latest.reminders),[]);
  assert.equal(h.calls.filter(call=>call.method!=='GET').length,0);
});

test('legacy favorites import requires authentication and remains explicit',async()=>{
  const legacy={...state(),favorites:['cvpr']},h=await harness({signedIn:false,legacy});
  await h.switchAccount('first');assert.deepEqual(favorites(h),['acl']);
  assert.equal(h.portal.requireLogin(),true);
  await h.importFavorites();assert.deepEqual(favorites(h),['acl','cvpr']);
  await h.switchAccount(null);
  assert.deepEqual(favorites(h),[]);assert.deepEqual(Array.from(h.portal.getReminders()),[]);
  assert.deepEqual(Array.from(h.latest.favorites),[]);assert.deepEqual(Array.from(h.latest.reminders),[]);
  assert.deepEqual(JSON.parse(h.storage.get('conf-atlas-guest')).favorites,['cvpr']);
});


test('optional account UI is loaded only from a valid same-origin session manifest',async()=>{
  for(const path of [undefined,'https://elsewhere.test/code.js','//elsewhere.test/code.js','/api/extension?token=secret','/api/extension#code','javascript:alert(1)']){
    const h=await harness({extensions:{first:path}});assert.equal(h.scripts.length,0);
  }
  const h=await harness({extensions:{first:'/api/account-extension'}});
  assert.equal(h.scripts.length,1);assert.equal(h.scripts[0].src,'/api/account-extension');
  const guest=await harness({signedIn:false,extensions:{first:'/api/account-extension'}});
  assert.equal(guest.scripts.length,0);
});

test('only the exact script node for the current session can install optional UI',async()=>{
  const h=await harness({extensions:{first:'/api/account-extension',second:'/api/account-extension'}});
  let mounted=0,disposed=0,lastContext;
  const extension={html:()=>'<p>Optional local tool</p>',mount:ctx=>{mounted++;lastContext=ctx;},dispose:()=>{disposed++;}};
  h.portal.render('account');
  assert.equal(h.portal.installAccountExtension(extension,{}),false);
  const first=h.scripts[0];assert.equal(h.portal.installAccountExtension(extension,first),true);
  assert.equal(mounted,1);assert.equal(lastContext.isCurrent(),true);
  await h.switchAccount('second');
  assert.equal(first.removed,true);assert.equal(disposed,1);assert.equal(lastContext.isCurrent(),false);
  assert.equal(h.portal.installAccountExtension(extension,first),false);
  assert.equal(h.portal.installAccountExtension(extension,h.scripts[1]),true);
  assert.equal(mounted,2);
});

test('logout removes optional UI and rejects a script that finishes after logout',async()=>{
  const h=await harness({extensions:{first:'/api/account-extension'}});let context;
  h.portal.render('account');
  const extension={html:()=>'<p>Optional private view</p>',mount:value=>{context=value;}};
  assert.equal(h.portal.installAccountExtension(extension,h.scripts[0]),true);
  await h.switchAccount(null);
  assert.equal(context.isCurrent(),false);assert.equal(h.element('#account-extension').innerHTML,'');
  assert.equal(h.portal.installAccountExtension(extension,h.scripts[0]),false);
});

test('leaving the account page invalidates a pending optional UI context',async()=>{
  const h=await harness({extensions:{first:'/api/account-extension'}});let context;
  h.portal.render('account');
  h.portal.installAccountExtension({html:()=>'',mount:value=>{context=value;}},h.scripts[0]);
  assert.equal(context.isCurrent(),true);h.portal.render('settings');assert.equal(context.isCurrent(),false);
});

test('an expired response from an earlier account cannot log out the replacement account',async()=>{
  const h=await harness();const held=h.holdOptionalFailure();
  const pending=assert.rejects(h.portal.api('/api/optional/read'),/expired/);
  await held.started;await h.switchAccount('second');held.release();await pending;
  assert.equal(h.portal.getScope(),'second');
});
