'use strict';
(() => {
  // Per-page streams separate concurrent tabs. Only their owner writes totals;
  // acknowledgements have separate keys, so a retry cannot erase newer taps.
  const prefix='conf-atlas-community-v1:', ackPrefix=prefix+'ack:', bindingPrefix=prefix+'instance:';
  const memory=new Map(),bindings=new Map();
  let currentId=null,stats=null,connected=null,storageOK=true,flushing=null,reading=null;
  let flushTimer=null,retryAt=0,failures=0;
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const validTotal=value=>Number.isSafeInteger(value)&&value>=0&&value<=1000;
  function read(key){try{return localStorage.getItem(key);}catch{storageOK=false;return null;}}
  function write(key,value){try{localStorage.setItem(key,value);}catch{storageOK=false;}}
  function remove(key){try{localStorage.removeItem(key);}catch{storageOK=false;}}
  function parse(raw){try{const item=JSON.parse(raw);return item&&uuid.test(item.id)&&validTotal(item.total)&&typeof item.closed==='boolean'&&(item.instanceId===null||uuid.test(item.instanceId))?item:null;}catch{return null;}}
  function records(){
    const result=new Map(memory);
    try{
      for(let i=0;i<localStorage.length;i++){
        const key=localStorage.key(i);
        if(!key?.startsWith(prefix+'stream:'))continue;
        const item=parse(localStorage.getItem(key));
        if(item)result.set(item.id,item);
      }
    }catch{storageOK=false;}
    return [...result.values()];
  }
  const keyOf=id=>prefix+'stream:'+id;
  const instanceOf=item=>item.instanceId||bindings.get(item.id)||read(bindingPrefix+item.id);
  function bind(item,destination){
    const existing=instanceOf(item);
    if(existing)return existing;
    // Bind before dispatch, including when storage is blocked. A lost response
    // must never make this stream eligible for a different backend instance.
    bindings.set(item.id,destination);write(bindingPrefix+item.id,destination);
    return destination;
  }
  const belongsHere=item=>!instanceOf(item)||instanceOf(item)===stats?.instanceId;
  function save(item){memory.set(item.id,{...item});write(keyOf(item.id),JSON.stringify(item));}
  function ackOf(item){const stored=Number(read(ackPrefix+item.id)||0);return Math.max(item.ack||0,validTotal(stored)?stored:0);}
  function pending(){return records().reduce((sum,item)=>sum+Math.max(0,item.total-ackOf(item)),0);}
  function applyStats(value){
    if(!value||!Number.isSafeInteger(value.woodfishTotal)||value.woodfishTotal<0||!uuid.test(value.instanceId)||!Number.isFinite(Date.parse(value.startedAt)))throw new Error('统计响应格式无效');
    if(stats?.instanceId===value.instanceId)value={...value,woodfishTotal:Math.max(stats.woodfishTotal,value.woodfishTotal)};
    stats=value;connected=true;failures=0;retryAt=0;
  }
  function render(){
    const count=pending(),other=stats?records().filter(item=>instanceOf(item)&&instanceOf(item)!==stats.instanceId).reduce((sum,item)=>sum+Math.max(0,item.total-ackOf(item)),0):0;
    let status=connected===null?'正在连接统计服务…':connected?'访客与登录用户共同累计 · 当前服务':'未连接统计服务';
    if(stats&&!connected)status+=' · 显示上次确认值';
    if(count)status+=` · ${count.toLocaleString('zh-CN')} 次待同步`;
    if(other)status+=`（其中 ${other.toLocaleString('zh-CN')} 次来自其他服务，暂不合并）`;
    if(!storageOK)status+=' · 浏览器存储不可用，未同步记录仅保留当前页面';
    document.querySelectorAll('[data-community-total]').forEach(el=>{el.textContent=stats?stats.woodfishTotal.toLocaleString('zh-CN'):'—';});
    document.querySelectorAll('[data-community-status]').forEach(el=>{el.textContent=status;});
    document.querySelectorAll('[data-community-started]').forEach(el=>{el.textContent=stats?`自 ${stats.startedAt.slice(0,10)} 起累计（UTC），不回填此前的个人记录。`:'连接统计服务后开始汇总；此前的个人记录不回填。';});
  }
  async function request(path,options={}){
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch(path,{credentials:'omit',...options,signal:controller.signal});
      if(!response.ok){const error=new Error('统计服务未连接');error.status=response.status;error.retryAfter=Number(response.headers?.get('Retry-After')||0);throw error;}
      return await response.json();
    }finally{clearTimeout(timeout);}
  }
  function failed(error){
    connected=false;failures++;retryAt=Date.now()+(error.status===429?Math.max(60000,(error.retryAfter||300)*1000):Math.min(60000,2000*2**Math.min(failures,5)));
    render();schedule(retryAt-Date.now());
  }
  function schedule(delay=500){
    if(flushTimer!==null)return;
    flushTimer=setTimeout(()=>{flushTimer=null;void flush();},Math.max(delay,retryAt-Date.now(),0));
  }
  async function refresh(){
    if(reading)return reading;
    if(Date.now()<retryAt){render();return;}
    reading=(async()=>{
      try{applyStats(await request('/api/community/stats'));render();if(pending())schedule(0);}
      catch(error){failed(error);}
      finally{reading=null;}
    })();
    return reading;
  }
  function acknowledge(item,value){
    if(!validTotal(value)||value<item.total)throw new Error('统计确认值无效');
    const live=memory.get(item.id)||parse(read(keyOf(item.id)))||item;
    const acknowledged=Math.max(ackOf(live),value);
    // Persist the ACK separately; an in-flight response never writes old totals.
    // Keep the tiny ACK/binding tombstones after retiring a stream: another
    // tab may still hold its snapshot, even after the database is replaced.
    write(ackPrefix+item.id,String(acknowledged));
    if(memory.has(item.id))memory.set(item.id,{...live,ack:acknowledged});
    if(live.closed&&acknowledged>=live.total){
      remove(keyOf(item.id));memory.delete(item.id);
    }
  }
  async function flush(){
    if(flushing)return flushing;
    if(Date.now()<retryAt){schedule(retryAt-Date.now());return;}
    flushing=(async()=>{
      await Promise.resolve();
      try{
        if(!stats){await refresh();if(!stats||Date.now()<retryAt)return;}
        // A bounded pass keeps large offline queues responsive. Other passes
        // continue through the same idempotent high-water endpoint.
        const items=records().filter(item=>belongsHere(item)&&item.total>ackOf(item)).slice(0,20);
        for(const item of items){
          if(!stats||!belongsHere(item))continue;
          const destination=stats.instanceId;
          if(bind(item,destination)!==destination)continue;
          const result=await request('/api/community/woodfish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({streamId:item.id,total:item.total,instanceId:destination})});
          if(result.instanceId!==destination||result.instanceId!==stats?.instanceId){const error=new Error('统计服务已更换，请刷新');error.status=409;throw error;}
          applyStats(result);acknowledge(item,result.acceptedTotal);render();
        }
      }catch(error){if(error.status===409)stats=null;failed(error);}
      finally{flushing=null;render();if(records().some(item=>(!stats||belongsHere(item))&&item.total>ackOf(item)))schedule(500);}
    })();
    return flushing;
  }
  function tap(){
    let item=currentId?memory.get(currentId):null;
    if(!item||item.closed||item.total>=1000||instanceOf(item)&&stats&&instanceOf(item)!==stats.instanceId){
      if(item&&!item.closed)save({...item,closed:true});
      currentId=crypto.randomUUID();item={id:currentId,total:0,closed:false,instanceId:stats?.instanceId||null,ack:0};
    }
    item={...item,total:item.total+1};if(item.total===1000)item.closed=true;
    save(item);render();schedule(500);
  }
  function closeCurrent(){
    const item=currentId?memory.get(currentId):null;
    if(item){save({...item,closed:true});if(ackOf(item)>=item.total){remove(keyOf(item.id));memory.delete(item.id);}}
    currentId=null;
  }
  window.addEventListener('pagehide',()=>{
    closeCurrent();
    if(!stats||Date.now()<retryAt)return;
    // Keep the durable outbox until a later page gets a confirmed ACK. A lost
    // keepalive response is retried with the same stream and cumulative total.
    for(const item of records().filter(row=>belongsHere(row)&&row.total>ackOf(row)).slice(0,5)){
      if(!stats||!belongsHere(item))continue;
      const destination=stats.instanceId;
      if(bind(item,destination)!==destination)continue;
      fetch('/api/community/woodfish',{method:'POST',credentials:'omit',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({streamId:item.id,total:item.total,instanceId:destination})}).catch(()=>{});
    }
  });
  window.addEventListener('online',()=>{retryAt=0;void refresh();schedule(0);});
  window.addEventListener('storage',event=>{if(event.key?.startsWith(prefix)){render();if(pending())schedule();}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){void refresh();schedule(0);}});
  document.addEventListener('click',event=>{if(event.target.closest('[data-community-refresh]')){retryAt=0;void refresh();schedule(0);}});
  setInterval(()=>{if(!document.hidden){void refresh();if(pending())schedule(0);}},30000);
  window.ConfCommunity={tap,refresh,render,flush};
  render();void refresh();
})();
