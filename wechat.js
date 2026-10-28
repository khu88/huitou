'use strict';
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const $ = selector => document.querySelector(selector);
  const EXAMPLES = ['CVPR 截止','AAAI 投稿','ICLR 论文','未来30天','我的收藏','收藏 AAAI','我的提醒','帮助'];
  let portal, notify=()=>{}, active=false, scope='', generation=0, timer, busy=false, sending=false, snapshot=null, messages=[], draft='', message='', error=false;
  const current = version => active && version===generation && scope===(portal?.getScope()||'guest');
  const formatTime = value => value && Number.isFinite(Number(value)) ? new Intl.DateTimeFormat('zh-CN',{timeZone:portal?.getSettings().timezone||'Asia/Singapore',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value*1000)) : '尚无记录';
  function linkedText(value) {
    return String(value ?? '').split(/(https?:\/\/[^\s<>]+)/g).map(part=>{
      if(!/^https?:\/\//.test(part))return esc(part);
      const trimmed=part.replace(/[。；，）)]+$/, '');
      try {const url=new URL(trimmed);if(!['https:','http:'].includes(url.protocol)||url.username||url.password)return esc(part);return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(trimmed)}</a>${esc(part.slice(trimmed.length))}`;}catch{return esc(part);}
    }).join('');
  }
  const safeQr = value => typeof value==='string' && /^data:image\/svg\+xml;base64,[A-Za-z0-9+/=]+$/.test(value) ? value : '';
  function safeLoginUrl(value) {
    try {const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password&&!url.port&&(url.hostname==='weixin.qq.com'||url.hostname.endsWith('.weixin.qq.com'))?url.href:'';} catch {return '';}
  }
  function html() {
    return `<div id="wechat-root" class="wx-layout">
      <section class="panel wx-chat-panel" aria-labelledby="wx-chat-title">
        <div class="panel-heading"><div class="wx-heading"><span class="wx-mark" aria-hidden="true">会</span><div><div class="wx-kicker">CONF. ATLAS · CHAT</div><h2 id="wx-chat-title">先聊一句，试试看。</h2></div></div><span class="soft-pill">本机体验</span></div>
        <p class="muted wx-intro">这里使用与微信相同的查询指令。收藏和提醒会保存到当前会投账号；本框中的消息不会发送到微信。</p>
        <div id="wx-chat-log" class="wx-chat-log" role="log" aria-label="本机指令体验记录" aria-live="polite"></div>
        <div class="wx-examples" aria-label="试试这些指令">${EXAMPLES.map(text=>`<button type="button" data-wx-example="${esc(text)}">${esc(text)}</button>`).join('')}</div>
        <form id="wx-chat-form"><label class="sr-only" for="wx-chat-input">输入会议问题或指令</label><textarea id="wx-chat-input" name="text" rows="2" maxlength="1000" placeholder="例如：CVPR 什么时候截稿？" required></textarea><div class="wx-compose-footer"><span id="wx-chat-hint">Enter 发送 · Shift + Enter 换行</span><button type="submit" class="primary-button">查询 / 执行 <span aria-hidden="true">↗</span></button></div></form>
        <p class="wx-small muted">按已核验的会议目录回答，缺失信息会注明。支持常用中文指令，不调用付费大模型。</p>
      </section>
      <aside class="wx-sidebar"><section class="panel wx-connect-panel" aria-labelledby="wx-connect-title"><div class="panel-heading"><div><div class="wx-kicker">BRING IT TO WECHAT</div><h3 id="wx-connect-title">把会投带到微信</h3></div><span class="wx-channel-icon" aria-hidden="true">☏</span></div><div id="wx-status"></div><button class="text-button wx-refresh" data-wx="refresh">刷新连接状态 ↻</button><div class="wx-runtime-note"><strong>本机运行说明</strong><p>关机、休眠或结束服务进程后，微信查询与提醒暂时不可用。使用同一数据库重新启动后，会自动续处理本机已接收但未完成的命令。</p><p>会话失效或发送结果不明时，请重新发起查询；停机期间的新消息是否保留取决于微信平台。错过的 DDL 提醒不会补发。</p></div><div id="wx-message" class="form-message" role="status" hidden></div></section>
        <section class="panel wx-guide"><h3>你可以这样问</h3><dl><dt>会议与投稿</dt><dd>查会议 ACL · AAAI 投稿 · ICLR 模板</dd><dt>证据与选读</dt><dd>ACL 录用率 · CVPR 参会 · ICLR 论文</dd><dt>安排下一步</dt><dd>收藏 AAAI · 我的提醒<br>提醒 CVPR 全文 提前7天</dd></dl><p class="wx-small muted">存在多个 Track 时，会先列出选项，再按指定 Track 设置提醒。</p><button class="text-button" type="button" data-wx-example="帮助">查看完整指令 ↗</button></section>
      </aside>

    </div>`;
  }
  function setMessage(value,isError=false) {message=value;error=isError;const target=$('#wx-message');if(!target)return;target.hidden=!message;target.textContent=message;target.classList.toggle('error',error);}
  function drawStatus() {
    const target=$('#wx-status');if(!target)return;
    if(!portal.getUser()) {
      target.innerHTML=`<div class="wx-state"><span class="wx-state-dot"></span><strong>先登录会投账号</strong></div><p class="muted">微信只连接你自己的收藏和提醒。登录后可体验指令，再扫码绑定。</p>${portal.isConnected()===false?'<p class="notice amber">当前为静态页面或本地账号服务未启动。微信连接需要运行 Python 本地服务。</p>':''}<button class="primary-button" data-view="account">前往登录 / 注册 ↗</button>`;
      drawControls();return;
    }
    if(!snapshot) {target.innerHTML='<p class="muted">正在读取本机微信连接状态…</p><button class="text-button" data-wx="refresh">重新读取 ↻</button>';drawControls();return;}
    const binding=snapshot.binding,login=snapshot.login;
    if(binding) {
      const title=!binding.enabled?'微信连接已暂停':binding.lastError?'连接需要处理':binding.contextReady?'已绑定 · 已有会话':'已绑定 · 等待首次消息';
      target.innerHTML=`<div class="wx-state ${binding.enabled&&!binding.lastError?'ready':''}"><span class="wx-state-dot"></span><strong>${title}</strong></div><p class="muted">${binding.contextReady?'在微信中向会投发消息，即可查询会议和管理收藏。':'请在微信 ClawBot 会话中发送「帮助」，建立可回复的会话。'}</p>
        <label class="switch-row"><span><strong>接收并回复微信消息</strong><small>暂停后保留绑定和会投数据</small></span><input type="checkbox" role="switch" data-wx-setting="enabled" ${binding.enabled?'checked':''}></label>
        <label class="switch-row"><span><strong>只推送 DDL 提醒</strong><small>按你保存的摘要 / 全文提醒发送，无日报或推荐消息</small></span><input type="checkbox" role="switch" data-wx-setting="pushEnabled" ${binding.pushEnabled?'checked':''}></label>
        ${!binding.enabled&&binding.pushEnabled?'<p class="notice amber">连接暂停期间不会发送提醒。</p>':''}
        ${binding.lastError?`<p class="notice amber">${esc(binding.lastError)}</p>`:''}
        <div class="wx-connection-meta"><span>绑定时间</span><time>${esc(formatTime(binding.connectedAt))}</time><span>最近收到消息</span><time>${esc(formatTime(binding.lastSeen))}</time></div>
        <p class="wx-small muted">本机服务和网络须保持运行。微信会话失效时需重新发送消息或绑定；接口接受不等于手机通知已送达。</p><button class="text-button danger-text" data-wx="disconnect">解除本机绑定</button>`;
    } else if(login && !['expired','cancelled','failed'].includes(login.status)) {
      const qr=safeQr(login.qrSvg),link=safeLoginUrl(login.qrUrl),labels={wait:'用微信扫一扫，绑定会投',scaned:'已扫码，请在微信中确认',scanned:'已扫码，请在微信中确认',need_verifycode:'请按微信提示完成安全验证',verify_code_blocked:'微信验证暂不可用，请稍后重试',scaned_but_redirect:'正在确认微信绑定',binded_redirect:'正在确认微信绑定'};
      target.innerHTML=`<div class="wx-state"><span class="wx-state-dot"></span><strong>${esc(labels[login.status]||'正在等待微信确认')}</strong></div>${login.status==='need_verifycode'?'<form id="wx-verify-form"><label class="form-field"><span>微信要求的验证码</span><input name="verifyCode" inputmode="numeric" autocomplete="one-time-code" maxlength="12" required aria-label="微信验证码"></label><button class="primary-button" type="submit">提交验证码</button></form>':''}${qr?`<img class="wx-qr" src="${esc(qr)}" alt="会投微信绑定二维码">`:'<p class="notice amber">二维码暂未生成。可打开下方微信绑定链接，或重新获取。</p>'}${link?`<a class="text-button wx-login-link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">打开微信绑定链接 ↗</a>`:''}<p class="wx-small muted">有效期至 ${esc(formatTime(login.expiresAt))}。请用你自己的微信扫码，绑定当前会投账号。</p><div class="wx-button-row"><button class="outline-button" data-wx="poll">检查扫码结果</button><button class="text-button" data-wx="cancel">取消</button></div>`;
    } else {
      target.innerHTML=`<div class="wx-state"><span class="wx-state-dot"></span><strong>${login?.status==='expired'?'二维码已过期':'尚未绑定微信'}</strong></div><p class="muted">扫码后，在微信 ClawBot 会话里查询会议、保存收藏，再按需开启 DDL 提醒。</p><button class="primary-button" data-wx="login">获取微信绑定二维码</button><p class="wx-small muted">点击后向微信官方服务请求绑定。查询内容和回复通过微信传输；连接凭证只保存在本机数据库。默认关闭主动提醒。</p>`;
    }
    drawControls();setMessage(message,error);
  }
  function drawControls() {
    const signedIn=!!portal?.getUser();
    document.querySelectorAll('[data-wx]').forEach(button=>button.disabled=busy||!signedIn);
    document.querySelectorAll('#wx-verify-form button,#wx-verify-form input').forEach(input=>input.disabled=busy||!signedIn);
    document.querySelectorAll('[data-wx-setting]').forEach(input=>input.disabled=busy||!signedIn);
    document.querySelectorAll('[data-wx-example]').forEach(button=>button.disabled=sending||!signedIn);
    const input=$('#wx-chat-input'),send=$('#wx-chat-form button[type=submit]');
    if(input)input.disabled=sending||!signedIn;if(send)send.disabled=sending||!signedIn;
    if($('#wx-chat-hint'))$('#wx-chat-hint').textContent=!signedIn?'登录后可体验指令':sending?'正在处理本机指令…':'Enter 发送 · Shift + Enter 换行';
  }
  function drawChat() {
    const target=$('#wx-chat-log');if(!target)return;
    target.innerHTML=messages.length?messages.map(item=>`<div class="wx-message ${item.role==='user'?'from-user':'from-assistant'}"><span class="wx-speaker">${item.role==='user'?'你 · 本机':'会投 · 本机'}</span><div class="wx-bubble${item.error?' is-error':''}">${linkedText(item.text)}</div></div>`).join(''):`<div class="wx-welcome"><span aria-hidden="true">↗</span><h3>会议很远，问一句就近了。</h3><p>从「CVPR 截止」开始。<br>也可以发「帮助」，看看会投能做什么。</p></div>`;
    target.scrollTop=target.scrollHeight;
    const input=$('#wx-chat-input');if(input)input.value=draft;drawControls();
  }
  function schedule() {
    clearTimeout(timer);if(!active||!portal?.getUser())return;
    if(snapshot?.login&&snapshot.login.expiresAt*1000<=Date.now()){
      snapshot.login=null;drawStatus();setMessage('二维码已过期，请重新获取。',true);
    }
    if(['need_verifycode','verify_code_blocked'].includes(snapshot?.login?.status))return;
    const pending=snapshot?.login&&!snapshot.binding&&!['expired','cancelled','failed'].includes(snapshot.login.status);
    timer=setTimeout(()=>loadStatus(pending?'poll':'status'),pending?3000:15000);
  }
  async function loadStatus(action='status',payload={}) {
    if(!active||!portal?.getUser()||busy){schedule();return;}
    const version=generation;busy=true;drawControls();
    try {
      const result=await portal.api(action==='poll'?'/api/wechat/login/poll':'/api/wechat/status',action==='poll'?{method:'POST',body:JSON.stringify(payload)}:{});
      if(!current(version))return;
      snapshot=result;drawStatus();
    } catch(err) {if(current(version)){if(err.code==='qr_expired'&&snapshot){snapshot.login=null;drawStatus();}setMessage(err.message,true);}}
    finally {if(current(version)){busy=false;drawControls();schedule();}}
  }
  async function action(name) {
    if(busy||!portal?.getUser())return;
    if(name==='poll'){await loadStatus('poll');return;}
    if(name==='refresh'){
      try{await portal.refreshState();}catch(err){setMessage(err.message,true);}
      await loadStatus();return;
    }
    const routes={login:'/api/wechat/login',cancel:'/api/wechat/login/cancel',disconnect:'/api/wechat/disconnect'};
    if(!routes[name])return;
    const version=generation;busy=true;clearTimeout(timer);setMessage('');drawControls();
    try {
      const result=await portal.api(routes[name],{method:'POST',body:'{}'});
      if(!current(version))return;snapshot=result;drawStatus();
      if(name==='disconnect')setMessage('本机绑定已解除，收藏和提醒设置仍保留。');
    }catch(err){if(current(version))setMessage(err.message,true);}
    finally{if(current(version)){busy=false;drawControls();schedule();}}
  }
  async function setSetting(key,value) {
    if(busy||!portal?.getUser())return;
    const version=generation;busy=true;clearTimeout(timer);drawControls();
    try{const result=await portal.api('/api/wechat/settings',{method:'PATCH',body:JSON.stringify({[key]:value})});if(!current(version))return;snapshot=result;setMessage('微信设置已保存。');drawStatus();}
    catch(err){if(current(version)){setMessage(err.message,true);drawStatus();}}
    finally{if(current(version)){busy=false;drawControls();schedule();}}
  }
  async function send(text) {
    text=text.trim();if(!text||sending||!portal?.getUser())return;
    const version=generation,account=scope;sending=true;draft='';messages.push({role:'user',text});messages=messages.slice(-30);drawChat();
    try{
      await portal.prepareSync();if(!current(version))return;
      const result=await portal.api('/api/wechat/chat',{method:'POST',body:JSON.stringify({text})});
      if(!current(version))return;
      messages.push({role:'assistant',text:result.text||'指令已处理。'});messages=messages.slice(-30);
      await portal.refreshState(result.state,account);
    }catch(err){if(current(version))messages.push({role:'assistant',text:err.message,error:true});}
    finally{if(current(version)){sending=false;drawChat();$('#wx-chat-input')?.focus();}}
  }
  function mount(options) {
    portal=options.portal;notify=options.notify||(()=>{});
    const next=portal.getScope();if(active&&scope===next){if(!snapshot)drawStatus();return;}
    if(scope!==next){messages=[];draft='';snapshot=null;message='';}
    scope=next;active=true;generation++;busy=false;sending=false;
    drawChat();drawStatus();if(portal.getUser())loadStatus();
  }
  function leave(){active=false;generation++;clearTimeout(timer);busy=false;sending=false;}
  function resetSession(){leave();scope='';messages=[];draft='';snapshot=null;message='';error=false;}
  document.addEventListener('click',event=>{const button=event.target.closest('[data-wx],[data-wx-example]');if(!button||!active)return;if(button.hasAttribute('data-wx-example')){draft=button.dataset.wxExample;const input=$('#wx-chat-input');if(input){input.value=draft;input.focus();}return;}action(button.dataset.wx);});
  document.addEventListener('change',event=>{if(active&&event.target.matches('[data-wx-setting]'))setSetting(event.target.dataset.wxSetting,event.target.checked);});
  document.addEventListener('input',event=>{if(event.target.id==='wx-chat-input')draft=event.target.value;});
  document.addEventListener('submit',event=>{if(event.target.id==='wx-verify-form'){event.preventDefault();const code=new FormData(event.target).get('verifyCode');event.target.reset();loadStatus('poll',{verifyCode:String(code||'').trim()});return;}if(event.target.id!=='wx-chat-form')return;event.preventDefault();send($('#wx-chat-input')?.value||'');});
  document.addEventListener('keydown',event=>{if(event.target.id==='wx-chat-input'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('#wx-chat-form')?.requestSubmit();}});
  window.addEventListener('pagehide',leave);
  window.ConfWeChat={html,mount,leave,resetSession};
})();
