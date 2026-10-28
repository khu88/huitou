'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const defaults = {theme:'system',fontSize:'standard',timezone:'Asia/Singapore',sound:false,reducedMotion:false};
  const blank = () => ({favorites:[],reminders:[],settings:{...defaults},relax:{woodfish:0,accepts:0,amen:0}});
  let guest = blank();
  try { const previous=JSON.parse(localStorage.getItem('conf-atlas-guest')||'null'); if(previous)guest={...guest,...previous,settings:{...defaults,...previous.settings},relax:{...guest.relax,...previous.relax}};else guest.favorites=JSON.parse(localStorage.getItem('conf-atlas-favorites')||'[]'); } catch {}
  guest.favorites=Array.isArray(guest.favorites)?guest.favorites:[];
  guest.reminders=Array.isArray(guest.reminders)?guest.reminders:[];
  // Keep legacy guest lists for an explicit signed-in import, without showing
  // or activating them while the visitor is signed out.
  const guestView=()=>({...structuredClone(guest),favorites:[],reminders:[]});
  let accountExtension=null,extensionScript=null;
  let current=guestView(),user=null,csrf=null,connected=null,activeView='',authMode='login',onChange=()=>{},notify=()=>{},saveChain=Promise.resolve(),savePending=false,saveTimer,revision=0,listRevision=0,pendingLists=0,confirmedLists={favorites:[],reminders:[]},pendingRelax={woodfish:0,accepts:0,amen:0};
  const media=matchMedia('(prefers-color-scheme: dark)');
  function applySettings() {
    document.documentElement.dataset.theme=current.settings.theme==='system'?(media.matches?'dark':'light'):current.settings.theme;
    document.documentElement.dataset.font=current.settings.fontSize;
    document.documentElement.dataset.motion=current.settings.reducedMotion?'reduced':'normal';
    const meta=$('meta[name="theme-color"]');if(meta)meta.content=document.documentElement.dataset.theme==='dark'?'#10131d':'#f5f6fa';
    if($('#theme-toggle'))$('#theme-toggle').textContent=document.documentElement.dataset.theme==='dark'?'☀':'☾';
  }
  media.addEventListener('change',applySettings);applySettings();
  function announce(){applySettings();if($('#user-label'))$('#user-label').textContent=user?.displayName||'登录 / 注册';if($('#user-avatar'))$('#user-avatar').textContent=(user?.displayName||'研').slice(0,1);onChange(user?structuredClone(current):{...structuredClone(current),favorites:[],reminders:[]},user);}
  function requireLogin(){
    if(user)return true;
    notify('收藏、提醒和微信功能需要先登录会投账号。');
    document.dispatchEvent(new CustomEvent('conf-login-required'));
    return false;
  }
  function checkAccount(){
    if(requireLogin())return;
    const error=new Error('请先登录会投账号。');error.code='authentication_required';throw error;
  }
  async function api(path,options={}) {
    const requestVersion=revision;
    const response=await fetch(path,{...options,credentials:'same-origin',headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{}),...options.headers}});
    let result;try{result=await response.json();}catch{throw new Error('账号服务未连接，请通过本地服务打开应用。');}
    if(!response.ok){if(response.status===401&&requestVersion===revision&&user&&!path.startsWith('/api/auth/')&&result.error?.code!=='wrong_password'){setSession({user:null});if(activeView==='account')render('account');}const error=new Error(result.error?.message||'操作未成功，请重试。');error.code=result.error?.code;error.status=response.status;throw error;}
    return result;
  }
  async function init(callback,toast) {
    if(callback)onChange=callback;if(toast)notify=toast;
    try {const result=await api('/api/session');connected=true;setSession(result);}catch{connected=false;announce();}
    if(activeView)render(activeView);
  }
  function setSession(result) {
    window.ConfWeChat?.resetSession();
    clearAccountExtension();
    revision++;listRevision++;pendingLists=0;clearTimeout(saveTimer);pendingRelax={woodfish:0,accepts:0,amen:0};user=result.user||null;csrf=result.csrfToken||null;
    current=user?{...blank(),...result.state,settings:{...defaults,...result.state?.settings},relax:{...blank().relax,...result.state?.relax}}:guestView();
    confirmedLists={favorites:[...current.favorites],reminders:structuredClone(current.reminders)};
    announce();loadAccountExtension(result.accountExtension);
  }
  function trackSave(operation) {
    saveChain=operation;savePending=true;
    const settled=()=>{if(saveChain===operation)savePending=false;};
    operation.then(settled,settled);return operation;
  }
  function save(patch) {
    if(!user){guest={...guest,settings:structuredClone(current.settings),relax:structuredClone(current.relax)};try{localStorage.setItem('conf-atlas-guest',JSON.stringify(guest));localStorage.setItem('conf-atlas-favorites',JSON.stringify(guest.favorites));}catch{throw new Error('浏览器未能保存访客数据；本次更改未持久保存。');}return Promise.resolve();}
    const payload=JSON.stringify(patch),version=revision;
    const operation=saveChain.catch(()=>{}).then(async()=>{if(version!==revision)throw new Error('账号会话已改变，未保存该操作。');await api('/api/state',{method:'PUT',body:payload});});
    return trackSave(operation);
  }
  // Only transmit the user's edits. A stale browser list must not replace
  // conferences or reminders added from WeChat (or another browser tab).
  async function saveLists(delta,previous) {
    checkAccount();
    const version=revision,sequence=++listRevision;
    const payload=JSON.stringify(delta);pendingLists++;
    const operation=saveChain.catch(()=>{}).then(async()=>{
      if(version!==revision)throw new Error('账号会话已改变，未保存该操作。');
      const result=await api('/api/state/sync',{method:'POST',body:payload});
      if(version!==revision)return;
      confirmedLists={favorites:[...result.state.favorites],reminders:structuredClone(result.state.reminders)};
      if(sequence===listRevision){current.favorites=[...confirmedLists.favorites];current.reminders=structuredClone(confirmedLists.reminders);announce();}
    }).finally(()=>{if(version===revision)pendingLists--;});
    trackSave(operation);
    try{await operation;}catch(error){
      if(version===revision&&sequence===listRevision){current.favorites=[...confirmedLists.favorites];current.reminders=structuredClone(confirmedLists.reminders);announce();}
      throw error;
    }
  }
  async function setFavorites(values){
    checkAccount();
    const previous={favorites:[...current.favorites],reminders:structuredClone(current.reminders)};
    const next=[...new Set(values)],oldSet=new Set(previous.favorites),newSet=new Set(next);
    const delta={favorites:{add:next.filter(id=>!oldSet.has(id)),remove:previous.favorites.filter(id=>!newSet.has(id))}};
    current.favorites=next;current.reminders=current.reminders.map(r=>newSet.has(r.conferenceId)?r:{...r,enabled:false});
    await saveLists(delta,previous);
  }
  async function setReminders(values,favoriteId){
    checkAccount();
    const previous={favorites:[...current.favorites],reminders:structuredClone(current.reminders)};
    const next=structuredClone(values),oldById=new Map(previous.reminders.map(r=>[r.id,r])),nextIds=new Set(next.map(r=>r.id));
    const delta={reminders:{upsert:next.filter(r=>!oldById.has(r.id)||JSON.stringify(r)!==JSON.stringify(oldById.get(r.id))),remove:previous.reminders.filter(r=>!nextIds.has(r.id)).map(r=>r.id)}};
    current.reminders=next;
    if(favoriteId){current.favorites=[...new Set([...current.favorites,favoriteId])];delta.favorites={add:[favoriteId],remove:[]};}
    await saveLists(delta,previous);
  }

  async function setSetting(key,value) {
    const previous=current.settings[key],version=revision;current.settings[key]=value;announce();
    try{await save({settings:{[key]:value}});notify(user?'设置已保存至账号':'设置已保存在当前浏览器');}catch(error){if(version===revision){current.settings[key]=previous;announce();}notify(error.message);}
    if(activeView==='settings')render('settings');
  }
  async function flushRelax() {
    if(!user){await save({relax:current.relax});return;}
    const delta={...pendingRelax},version=revision;if(!Object.values(delta).some(Boolean))return;
    pendingRelax={woodfish:0,accepts:0,amen:0};
    const operation=saveChain.catch(()=>{}).then(async()=>{
      if(version!==revision)return;
      const response=await api('/api/relax/increment',{method:'POST',body:JSON.stringify(delta)});
      if(version===revision){for(const key of Object.keys(delta))current.relax[key]=response.relax[key]+pendingRelax[key];if($('#woodfish-count'))$('#woodfish-count').textContent=current.relax.woodfish;if($('#accept-count'))$('#accept-count').textContent=current.relax.accepts;if($('#amen-count'))$('#amen-count').textContent=current.relax.amen;}
    });trackSave(operation);await operation;
  }
  // External entry points share this account's state, but never adopt an old response
  // after logout/account switching or discard taps still waiting to be saved.
  async function prepareSync() {
    const version=revision;
    if(!user)throw new Error('请先登录会投账号。');
    const previous=saveChain;
    // A settled failure was already reported by its initiating action. It must
    // not poison all later queries; failures in work still pending do propagate.
    if(savePending)await previous;
    else {await previous.catch(()=>{});if(saveChain===previous)saveChain=Promise.resolve();}
    if(version!==revision||!user)throw new Error('账号已改变，请重新操作。');
    clearTimeout(saveTimer);await flushRelax();await saveChain;
    if(version!==revision||!user)throw new Error('账号已改变，请重新操作。');
    return user.id;
  }
  async function scopedApi(path,options={}) {
    const version=revision,scope=user?.id;
    if(!scope)throw new Error('请先登录会投账号。');
    const result=await api(path,options);
    if(version!==revision||user?.id!==scope)throw new Error('账号已改变，已忽略此前的响应。');
    return result;
  }
  async function refreshState(state,expectedScope=user?.id) {
    const version=revision;
    if(!user||user.id!==expectedScope)return false;
    if(!state){
      await prepareSync();const result=await scopedApi('/api/session');
      if(result.user?.id!==expectedScope)throw new Error('账号状态已改变，请重新登录。');
      state=result.state;
    }
    if(version!==revision||user?.id!==expectedScope)return false;
    const next={...blank(),...state,settings:{...defaults,...state?.settings},relax:{...blank().relax,...state?.relax}};
    for(const key of Object.keys(pendingRelax))next.relax[key]+=pendingRelax[key];
    if(pendingLists){next.favorites=current.favorites;next.reminders=current.reminders;}
    else confirmedLists={favorites:[...next.favorites],reminders:structuredClone(next.reminders)};
    current=next;announce();return true;
  }
  function pageMessage(message,error=false){const target=$('#portal-message');if(target){target.textContent=message;target.className='form-message'+(error?' error':'');target.hidden=false;}else notify(message);}
  function field(label,name,type='text',extra=''){return `<label class="form-field"><span>${label}</span><input name="${name}" type="${type}" ${extra} required></label>`;}
  function accountPage() {
    if(!user)return `<div class="account-layout"><section class="panel auth-panel"><div class="panel-kicker">YOUR RESEARCH, YOUR SPACE</div><h2>${authMode==='login'?'欢迎回来。':'为下一篇，留个位置。'}</h2><p class="muted">查会议、敲木鱼和加入 A / B 门可直接体验。登录后使用收藏、截止提醒和微信绑定。</p><div class="segmented auth-tabs"><button data-portal="auth-mode" data-value="login" class="${authMode==='login'?'selected':''}">登录</button><button data-portal="auth-mode" data-value="register" class="${authMode==='register'?'selected':''}">注册账号</button></div>${connected===false?'<div class="notice amber">账号服务未连接。请运行 <code>python3 serve.py</code> 后从本地地址打开。<button class="text-button" data-portal="reconnect">重新连接 ↻</button></div>':''}<form id="auth-form">${field('用户名','username','text','autocomplete="username" minlength="3" maxlength="32" placeholder="你的用户名"')}${authMode==='register'?field('昵称','displayName','text','autocomplete="nickname" maxlength="40" placeholder="你希望大家如何称呼你"'):''}${field('密码','password','password',`autocomplete="${authMode==='login'?'current-password':'new-password'}" minlength="10" maxlength="128" placeholder="至少 10 个字符"`)}${authMode==='register'?field('确认密码','confirmPassword','password','autocomplete="new-password" minlength="10" maxlength="128" placeholder="再输入一次密码"'):''}<div id="portal-message" class="form-message" role="status" hidden></div><button class="primary-button wide" type="submit" ${connected===false?'disabled':''}>${authMode==='login'?'登录':'创建账号'} <span>→</span></button></form><p class="form-footnote">${authMode==='register'?'用户名支持字母、数字、下划线、点和短横线。':'账号及收藏保存在运行此服务的本机数据库中，当前未连接云端。'}</p></section><section class="account-aside"><div class="account-art">↗</div><h3>研究很长，<br>给自己一个书签。</h3><p>收藏下一站。记住自己的偏好。<br>偶尔，也给自己一个 Accept。</p><div class="account-perks"><span>☆ 独立收藏</span><span>◐ 个性设置</span><span>✦ 解压记录</span></div></section></div>`;
    return `<div class="profile-banner panel"><div class="profile-avatar">${esc(user.displayName.slice(0,1))}</div><div><h2>${esc(user.displayName)}</h2><p>@${esc(user.username)} <span class="role-pill">研究者</span></p></div><button class="outline-button" data-portal="logout">退出登录 ↗</button></div><div class="settings-grid"><section class="panel"><h3>个人资料</h3><form id="profile-form">${field('昵称','displayName','text',`value="${esc(user.displayName)}" maxlength="40" autocomplete="nickname"`)}<button class="primary-button" type="submit">保存昵称</button></form><p class="muted">用户名固定为 ${esc(user.username)}。你的收藏与其他账号相互独立。</p><button class="text-button" data-portal="import-favorites">导入本机访客收藏（${guest.favorites.length}） ↗</button></section><section class="panel"><h3>修改密码</h3><form id="password-form">${field('当前密码','currentPassword','password','autocomplete="current-password" maxlength="128"')}${field('新密码','newPassword','password','autocomplete="new-password" minlength="10" maxlength="128" placeholder="至少 10 个字符"')}<button class="outline-button" type="submit">更新密码</button></form><p class="muted">更新后将退出所有已有会话，需要重新登录。</p></section></div><details class="panel account-delete"><summary>注销当前账号</summary><p class="muted">永久删除当前账号、收藏、设置、提醒和个人解压记录，并退出全部会话。此操作无法撤销。已匿名汇总的全站木鱼次数不会回减。</p><form id="delete-account-form">${field('输入当前密码确认注销','currentPassword','password','autocomplete="current-password" maxlength="128"')}<button class="danger-button" type="submit">确认永久注销此账号</button></form></details><div id="portal-message" class="form-message" role="status" hidden></div><div id="account-extension"></div>`;
  }
  function choices(key,values){return `<div class="choice-grid">${values.map(([value,label,description])=>`<button class="choice ${current.settings[key]===value?'selected':''}" data-portal="setting" data-key="${key}" data-value="${value}" aria-pressed="${current.settings[key]===value}"><span class="choice-icon">${key==='theme'?value==='light'?'☀':value==='dark'?'☾':'◐':'Aa'}</span><strong>${label}</strong><small>${description}</small></button>`).join('')}</div>`;}
  function settingsPage(){return `<div class="settings-grid"><section class="panel setting-wide"><div class="panel-heading"><div><h3>外观主题</h3><p class="muted">明亮一点，或安静一点。由你决定。</p></div><span class="soft-pill">${user?'账号设置':'访客设置'}</span></div>${choices('theme',[['light','亮色','纯白卡片 · 冷灰背景'],['dark','暗色','深色背景 · 清晰对比'],['system','跟随系统','随设备主题自动切换']])}</section><section class="panel setting-wide"><h3>阅读字号</h3><p class="muted">会议全称、Track 与时间信息一起调整。</p>${choices('fontSize',[['standard','标准','14 px 基础字号'],['large','大字','约 16 px 基础字号'],['extra','特大','约 18 px 基础字号']])}</section><section class="panel"><h3>日历显示时区</h3><p class="muted">详情保留来源时区，同时显示你的选择。倒计时始终按同一时刻计算。</p><label class="form-field"><span>显示时区</span><select id="timezone-setting"><option value="Asia/Singapore" ${current.settings.timezone==='Asia/Singapore'?'selected':''}>新加坡 / 北京时间 · UTC+8</option><option value="UTC" ${current.settings.timezone==='UTC'?'selected':''}>协调世界时 · UTC</option><option value="America/Los_Angeles" ${current.settings.timezone==='America/Los_Angeles'?'selected':''}>洛杉矶 · 自动处理夏令时</option></select></label></section><section class="panel"><h3>解压与动效</h3><label class="switch-row"><span><strong>木鱼音效</strong><small>只在主动点击木鱼时播放</small></span><input id="sound-setting" type="checkbox" role="switch" ${current.settings.sound?'checked':''}></label><label class="switch-row"><span><strong>减少动画</strong><small>保留互动，减少飘字和缩放</small></span><input id="motion-setting" type="checkbox" role="switch" ${current.settings.reducedMotion?'checked':''}></label></section></div><div class="notice">${user?'设置随当前账号保存在本机数据库。退出后恢复访客偏好。':'当前为访客模式，设置保存在此浏览器。登录后使用账号自己的设置。'}</div>`;}
  function relaxPage(){return window.ConfRelax.html({counts:current.relax,signedIn:!!user});}
  function render(view){
    activeView=view;const target=$('#secondary-view');if(!target)return;
    accountExtension?.leave?.();
    window.ConfRelax?.leave();
    window.ConfServices?.leave?.();
    if(view==='wechat'&&target.querySelector('#wechat-root')){window.ConfWeChat.mount({portal:window.ConfPortal,notify});return;}
    window.ConfWeChat?.leave();
    target.innerHTML=view==='account'?accountPage():view==='settings'?settingsPage():view==='relax'?relaxPage():view==='wechat'?window.ConfWeChat.html():view==='services'?window.ConfServices.html():'';
    if(view==='relax')window.ConfRelax.mount({getCounts:()=>current.relax,getSettings:()=>current.settings,increment,setSound:value=>setSetting('sound',value),notify});
    if(view==='wechat')window.ConfWeChat.mount({portal:window.ConfPortal,notify});
    if(view==='services')window.ConfServices.mount?.({notify});
    if(view==='account')mountAccountExtension();
  }
  function clearAccountExtension(){
    accountExtension?.dispose?.();accountExtension=null;
    extensionScript?.remove();extensionScript=null;
    const target=$('#account-extension');if(target)target.replaceChildren();
  }
  function loadAccountExtension(path){
    // Only a same-origin API resource explicitly supplied by this session may
    // install optional account UI. Old script nodes cannot register later.
    if(!user||typeof path!=='string'||!/^\/api\/[A-Za-z0-9/_-]+$/.test(path))return;
    const version=revision,node=document.createElement('script');
    node.src=path;node.async=true;extensionScript=node;
    node.onerror=()=>{if(version===revision&&extensionScript===node){const target=$('#account-extension');if(target)target.textContent='附加功能暂不可用，请刷新后重试。';}};
    document.head.append(node);
  }
  function installAccountExtension(extension,source){
    if(!user||!extensionScript||source!==extensionScript||typeof extension?.html!=='function'||typeof extension?.mount!=='function')return false;
    accountExtension?.dispose?.();accountExtension=extension;
    if(activeView==='account')mountAccountExtension();
    return true;
  }
  function mountAccountExtension(){
    const target=$('#account-extension');if(!target||!user||!accountExtension)return;
    const version=revision,owner=user.id,extension=accountExtension;
    target.innerHTML=extension.html();
    extension.mount({target,api:scopedApi,notify,getUser:()=>structuredClone(user),getSettings:()=>({...current.settings}),
      isCurrent:()=>version===revision&&user?.id===owner&&accountExtension===extension&&activeView==='account'&&$('#account-extension')===target});
  }

  function increment(key){if(current.relax[key]>=1000000000)return;current.relax[key]++;pendingRelax[key]++;clearTimeout(saveTimer);saveTimer=setTimeout(()=>flushRelax().catch(e=>notify('记录未保存：'+e.message)),250);}
  document.addEventListener('click',async e=>{if(e.target.closest('[data-require-login]')){requireLogin();return;}const button=e.target.closest('[data-portal]');if(!button)return;const action=button.dataset.portal;
    if(action==='setting'){await setSetting(button.dataset.key,button.dataset.value);return;}
    if(action==='theme-toggle'){await setSetting('theme',document.documentElement.dataset.theme==='dark'?'light':'dark');return;}
    if(action==='sound-toggle'){await setSetting('sound',!current.settings.sound);if(activeView==='relax')render('relax');return;}
    if(action==='auth-mode'){authMode=button.dataset.value;render('account');return;}
    if(action==='reconnect'){await init();return;}
    button.disabled=true;
    try{
      if(action==='logout'){clearTimeout(saveTimer);try{await flushRelax();await saveChain;}catch{}try{await api('/api/auth/logout',{method:'POST',body:'{}'});}catch(error){if(error.status!==401)throw error;}setSession({user:null});render('account');notify('已退出登录');}
      if(action==='import-favorites'){await setFavorites([...current.favorites,...guest.favorites]);announce();notify('访客收藏已合并到当前账号');}
    }catch(error){pageMessage(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
  });
  document.addEventListener('change',e=>{if(e.target.id==='timezone-setting')setSetting('timezone',e.target.value);if(e.target.id==='sound-setting')setSetting('sound',e.target.checked);if(e.target.id==='motion-setting')setSetting('reducedMotion',e.target.checked);});
  document.addEventListener('submit',async e=>{if(!['auth-form','profile-form','password-form','delete-account-form'].includes(e.target.id))return;e.preventDefault();const form=e.target,values=Object.fromEntries(new FormData(form)),button=form.querySelector('button[type="submit"]');button.disabled=true;
    try{
      if(form.id==='auth-form'){
        if(authMode==='register'&&values.password!==values.confirmPassword)throw new Error('两次输入的密码不一致。');
        const payload={username:values.username,password:values.password,...(authMode==='register'?{displayName:values.displayName}:{})};
        const result=await api('/api/auth/'+authMode,{method:'POST',body:JSON.stringify(payload)});connected=true;setSession(result);render('account');notify(authMode==='register'?'账号创建成功':'已登录');
      }else if(form.id==='profile-form'){const result=await api('/api/profile',{method:'PATCH',body:JSON.stringify({displayName:values.displayName})});if(result.user)user=result.user;else user.displayName=values.displayName;announce();render('account');pageMessage('昵称已更新。');}
      else if(form.id==='delete-account-form'){await api('/api/account/delete',{method:'POST',body:JSON.stringify(values)});setSession({user:null});authMode='login';render('account');pageMessage('账号及其数据已删除。');}
      else {await api('/api/password',{method:'POST',body:JSON.stringify(values)});setSession({user:null});authMode='login';render('account');pageMessage('密码已更新，请重新登录。');}
    }catch(error){pageMessage(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
  });
  window.addEventListener('pagehide',()=>{clearTimeout(saveTimer);if(!user){try{save({});}catch{}}else if(Object.values(pendingRelax).some(Boolean)){const delta={...pendingRelax};pendingRelax={woodfish:0,accepts:0,amen:0};fetch('/api/relax/increment',{method:'POST',credentials:'same-origin',keepalive:true,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(delta)}).catch(()=>{});}});
  window.ConfPortal={init,render,installAccountExtension,api:scopedApi,prepareSync,refreshState,requireLogin,isConnected:()=>connected,setFavorites,setReminders,getReminders:()=>user?structuredClone(current.reminders||[]):[],getScope:()=>user?.id||'guest',getSettings:()=>({...current.settings}),getFavorites:()=>user?[...current.favorites]:[],getUser:()=>user,leave:()=>{activeView='';accountExtension?.leave?.();window.ConfRelax?.leave();window.ConfWeChat?.leave();window.ConfServices?.leave?.();}};
})();
