import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../community.js',import.meta.url),'utf8');
const epoch=Date.parse('2026-10-29T00:00:00Z');
let ids=0;
const newId=()=>`10000000-0000-4000-8000-${String(++ids).padStart(12,'0')}`;
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
function server(){
  const streams=new Map(),calls=[];
  let total=0,instanceId=newId(),available=true,drop=false,gate=null,getGate=null,rateLimit=false;
  const snapshot=()=>({woodfishTotal:total,instanceId,startedAt:new Date(epoch).toISOString(),scope:'instance'});
  async function fetch(path,options={}){
    const body=options.body?JSON.parse(options.body):null;
    calls.push({path,body,keepalive:options.keepalive||false});
    assert.equal(options.credentials,'omit');
    if(!available)return {ok:false,status:404,headers:{get:()=>null}};
    if(path==='/api/community/stats'){
      const result=snapshot();if(getGate){const wait=getGate;getGate=null;await wait.promise;}
      return {ok:true,json:async()=>result};
    }
    if(rateLimit)return {ok:false,status:429,headers:{get:()=> '300'}};
    assert.equal(path,'/api/community/woodfish');
    if(body.instanceId!==instanceId)return {ok:false,status:409,headers:{get:()=>null}};
    assert.ok(body.total<=1000);
    const previous=streams.get(body.streamId)||0;
    streams.set(body.streamId,Math.max(previous,body.total));total+=Math.max(0,body.total-previous);
    const result={...snapshot(),acceptedTotal:streams.get(body.streamId)};
    if(drop){drop=false;throw new Error('Response lost after commit');}
    if(gate){const wait=gate;gate=null;await wait.promise;}
    return {ok:true,json:async()=>result};
  }
  return {fetch,calls,streams,get total(){return total;},set available(v){available=v;},set drop(v){drop=v;},set gate(v){gate=v;},set getGate(v){getGate=v;},set rateLimit(v){rateLimit=v;},replace(){instanceId=newId();streams.clear();total=0;}};
}
async function harness({backend=server(),storage=new Map(),brokenStorage=false}={}){
  let now=epoch,timerId=0;
  const timers=new Map(),listeners=new Map(),documentListeners=new Map(),elements=new Map();
  for(const key of ['total','status','started'])elements.set(`[data-community-${key}]`,[{textContent:''}]);
  const storageAPI={
    get length(){if(brokenStorage)throw new Error('blocked');return storage.size;},
    key:i=>[...storage.keys()][i]??null,
    getItem:key=>{if(brokenStorage)throw new Error('blocked');return storage.get(key)??null;},
    setItem:(key,value)=>{if(brokenStorage)throw new Error('blocked');storage.set(key,value);},
    removeItem:key=>{if(brokenStorage)throw new Error('blocked');storage.delete(key);},
  };
  class Clock extends Date{static now(){return now;}}
  const context=vm.createContext({
    console,Date:Clock,AbortController,crypto:{randomUUID:newId},localStorage:storageAPI,fetch:backend.fetch,
    setTimeout:(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;},clearTimeout:id=>timers.delete(id),setInterval:()=>1,
    window:{addEventListener:(name,fn)=>listeners.set(name,fn)},
    document:{hidden:false,querySelectorAll:selector=>elements.get(selector)||[],addEventListener:(name,fn)=>documentListeners.set(name,fn)},
  });
  vm.runInContext(source,context,{filename:'community.js'});
  const ui=context.window.ConfCommunity;
  await ui.refresh();
  return {ui,backend,storage,timers,advance:ms=>{now+=ms;},pagehide:()=>listeners.get('pagehide')(),
    get total(){return elements.get('[data-community-total]')[0].textContent;},
    get status(){return elements.get('[data-community-status]')[0].textContent;},
  };
}

test('new explicit taps count independently from any old account or guest data',async()=>{
  const storage=new Map([['conf-atlas-guest',JSON.stringify({relax:{woodfish:999}})]]);
  const h=await harness({storage});
  assert.equal(h.total,'0');h.ui.tap();h.ui.tap();
  assert.equal(h.total,'0');assert.match(h.status,/2 次待同步/);
  await h.ui.flush();assert.equal(h.total,'2');assert.equal(h.backend.total,2);
  assert.equal(h.backend.calls.filter(c=>c.body).length,1);
});

test('two tabs use independent streams and shared retries never duplicate totals',async()=>{
  const backend=server(),storage=new Map(),a=await harness({backend,storage}),b=await harness({backend,storage});
  a.ui.tap();a.ui.tap();b.ui.tap();
  await Promise.all([a.ui.flush(),b.ui.flush()]);
  assert.equal(backend.total,3);assert.equal(backend.streams.size,2);
  await Promise.all([a.ui.refresh(),b.ui.refresh()]);assert.equal(a.total,'3');assert.equal(b.total,'3');
});

test('a response lost after server commit retries same stream without counting twice',async()=>{
  const h=await harness();h.ui.tap();h.backend.drop=true;await h.ui.flush();
  assert.equal(h.backend.total,1);assert.match(h.status,/1 次待同步/);
  h.advance(10000);await h.ui.flush();
  assert.equal(h.total,'1');assert.doesNotMatch(h.status,/待同步/);
  const writes=h.backend.calls.filter(c=>c.body);assert.equal(writes[0].body.streamId,writes[1].body.streamId);
});

test('new taps during an in-flight acknowledgement survive and are later sent',async()=>{
  const h=await harness(),gate=deferred();h.ui.tap();h.ui.tap();h.backend.gate=gate;
  const first=h.ui.flush();await Promise.resolve();h.ui.tap();gate.resolve();await first;
  assert.equal(h.backend.total,2);assert.match(h.status,/1 次待同步/);
  await h.ui.flush();assert.equal(h.backend.total,3);assert.equal(h.total,'3');
});

test('reload retries durable pending stream and pagehide keepalive is idempotent',async()=>{
  const backend=server(),storage=new Map(),a=await harness({backend,storage});a.ui.tap();a.ui.tap();
  a.pagehide();await Promise.resolve();assert.equal(backend.total,2);
  const b=await harness({backend,storage});await b.ui.flush();
  assert.equal(backend.total,2);assert.equal(b.total,'2');
  assert.equal([...storage.keys()].filter(k=>k.includes('stream:')).length,0);
});

test('pure static fallback shows unknown and an offline backlog over 1000 remains bounded',async()=>{
  const backend=server();backend.available=false;const h=await harness({backend});
  assert.equal(h.total,'—');assert.match(h.status,/未连接统计服务/);
  for(let i=0;i<2101;i++)h.ui.tap();
  assert.equal(h.total,'—');assert.match(h.status,/2,101 次待同步/);
  backend.available=true;h.advance(10000);await h.ui.flush();
  assert.equal(backend.total,2101);assert.equal(h.total,'2,101');
  assert.deepEqual(backend.calls.filter(c=>c.body).map(c=>c.body.total),[1000,1000,101]);
});

test('rate limit honors Retry-After and keeps durable taps',async()=>{
  const h=await harness();h.ui.tap();h.backend.rateLimit=true;await h.ui.flush();
  const before=h.backend.calls.length;h.advance(299000);await h.ui.flush();assert.equal(h.backend.calls.length,before);
  h.backend.rateLimit=false;h.advance(1000);await h.ui.flush();assert.equal(h.backend.total,1);
});

test('database replacement does not replay a bound old pending stream into new totals',async()=>{
  const h=await harness();h.ui.tap();h.backend.drop=true;await h.ui.flush();assert.equal(h.backend.total,1);
  h.backend.replace();h.advance(10000);await h.ui.refresh();await h.ui.flush();
  assert.equal(h.backend.total,0);assert.equal(h.total,'0');assert.match(h.status,/其他服务，暂不合并/);
  h.ui.tap();await h.ui.flush();assert.equal(h.backend.total,1);
});

test('blocked browser storage keeps current-page pending taps and explains the limitation',async()=>{
  const h=await harness({brokenStorage:true});h.ui.tap();h.ui.tap();await h.ui.flush();
  assert.equal(h.backend.total,2);assert.match(h.status,/存储不可用/);assert.match(h.status,/仅保留当前页面/);
});

test('late GET response cannot regress a more recent confirmed total',async()=>{
  const h=await harness(),gate=deferred();h.backend.getGate=gate;const reading=h.ui.refresh();
  h.ui.tap();await h.ui.flush();assert.equal(h.total,'1');gate.resolve();await reading;assert.equal(h.total,'1');
});

test('backend replaced between GET and POST rejects old-instance write before any new count',async()=>{
  const h=await harness();h.ui.tap();h.backend.replace();await h.ui.flush();
  assert.equal(h.backend.total,0);assert.equal(h.total,'—');
  h.advance(10000);await h.ui.flush();assert.equal(h.total,'0');assert.match(h.status,/其他服务，暂不合并/);
  h.ui.tap();await h.ui.flush();assert.equal(h.backend.total,1);
});

test('another tab acknowledging an old snapshot cannot overwrite owner newer taps',async()=>{
  const backend=server(),storage=new Map(),a=await harness({backend,storage}),b=await harness({backend,storage}),gate=deferred();
  a.ui.tap();backend.gate=gate;const saving=b.ui.flush();await Promise.resolve();
  a.ui.tap();a.ui.tap();gate.resolve();await saving;
  assert.equal(backend.total,1);await a.ui.flush();assert.equal(backend.total,3);
  const c=await harness({backend,storage});await c.ui.flush();assert.equal(backend.total,3);
});

test('retired offline stream acknowledged by another tab is not replayed after a database switch',async()=>{
  const backend=server(),storage=new Map();backend.available=false;const a=await harness({backend,storage});
  a.ui.tap();a.pagehide();backend.available=true;const b=await harness({backend,storage});await b.ui.flush();
  assert.equal(backend.total,1);backend.replace();a.advance(10000);await a.ui.refresh();await a.ui.flush();assert.equal(backend.total,0);
});

test('blocked storage still binds initially offline taps before a lost response and database change',async()=>{
  const backend=server();backend.available=false;const h=await harness({backend,brokenStorage:true});h.ui.tap();
  backend.available=true;h.advance(10000);backend.drop=true;await h.ui.flush();assert.equal(backend.total,1);
  backend.replace();h.advance(10000);await h.ui.refresh();await h.ui.flush();
  assert.equal(backend.total,0);assert.match(h.status,/其他服务，暂不合并/);
  h.pagehide();await Promise.resolve();assert.equal(backend.total,0);
});

test('a refresh changing instances during a batch stops remaining old-bound writes',async()=>{
  const backend=server();backend.available=false;const h=await harness({backend}),gate=deferred();
  for(let i=0;i<1001;i++)h.ui.tap();
  backend.available=true;h.advance(10000);await h.ui.refresh();
  // A prior attempted delivery already bound both offline-created streams to A.
  const records=[...h.storage.entries()].filter(([key])=>key.includes('stream:')).map(([,value])=>JSON.parse(value));
  const {instanceId}=await (await backend.fetch('/api/community/stats',{credentials:'omit'})).json();
  for(const item of records)h.storage.set('conf-atlas-community-v1:instance:'+item.id,instanceId);
  backend.gate=gate;const running=h.ui.flush();await Promise.resolve();assert.equal(backend.total,1000);
  backend.replace();await h.ui.refresh();gate.resolve();await running;
  assert.equal(backend.total,0);h.advance(10000);await h.ui.flush();assert.equal(backend.total,0);
  assert.equal(backend.calls.filter(call=>call.body).length,1);
});

test('a stream bound elsewhere after batch snapshot is not rebound by the next iteration',async()=>{
  const backend=server();backend.available=false;const h=await harness({backend}),gate=deferred();
  for(let i=0;i<1001;i++)h.ui.tap();
  backend.available=true;h.advance(10000);await h.ui.refresh();
  const records=[...h.storage.entries()].filter(([key])=>key.includes('stream:')).map(([,value])=>JSON.parse(value));
  const second=records.find(item=>item.total===1),otherInstance=newId();
  backend.gate=gate;const running=h.ui.flush();await Promise.resolve();
  h.storage.set('conf-atlas-community-v1:instance:'+second.id,otherInstance);
  gate.resolve();await running;
  assert.equal(backend.total,1000);assert.equal(h.storage.get('conf-atlas-community-v1:instance:'+second.id),otherInstance);
  assert.equal(backend.calls.filter(call=>call.body).length,1);
});
