'use strict';
(() => {
  const LEADS = {10080:'提前 7 天',4320:'提前 3 天',1440:'提前 1 天',180:'提前 3 小时',60:'提前 1 小时',5:'提前 5 分钟',0:'截止时'};
  const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const time = r => Date.parse(r.deadline) - r.leadMinutes * 60000;
  const currentTrack = (r, catalog) => catalog.find(c=>c.id===r.conferenceId)?.detail?.tracks?.find(t=>t.name===r.trackName);
  const stageLabel = track => track?.submissionStage==='invitation-only'?' · 仅限获邀':'';
  const stageNotice = track => track?.submissionStage==='invitation-only'?'仅限获邀稿件；此阶段不接受普通新稿。':'';
  function validDate(value) {
    const match=typeof value==='string'&&value.match(/^(\d{4})-(\d{2})-(\d{2})T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})$/);
    if(!match||!Number.isFinite(Date.parse(value)))return false;
    const clock=value.slice(11,19).match(/^(\d{2}):(\d{2})(?::(\d{2}))?/);if(!clock||Number(clock[1])>23||Number(clock[2])>59||Number(clock[3]||0)>59)return false;
    const [,y,m,d]=match.map(Number),probe=new Date(Date.UTC(y,m-1,d));
    return probe.getUTCFullYear()===y&&probe.getUTCMonth()===m-1&&probe.getUTCDate()===d;
  }
  function problem(r, conferences) {
    if (!r || !r.id || !Object.hasOwn(LEADS,r.leadMinutes) || typeof r.leadMinutes!=='number' || !['abstract','full'].includes(r.kind) || typeof r.enabled!=='boolean' || !validDate(r.deadline)) return '提醒格式无效';
    const track = currentTrack(r,conferences);
    const value = track?.[r.kind==='abstract'?'abstractDeadline':'fullDeadline'];
    if (!value) return '当前节点日期待核验';
    if (Date.parse(value)!==Date.parse(r.deadline)) return '日期已变化，请重新设置';
    return null;
  }
  const icsText = s => String(s).replace(/\\/g,'\\\\').replace(/\r\n|\r|\n/g,'\\n').replace(/;/g,'\\;').replace(/,/g,'\\,');
  const stamp = d => new Date(d).toISOString().replace(/[-:]/g,'').replace(/\.\d{3}/,'');
  function calendar(reminders, conferences, now=Date.now()) {
    const lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Conf Atlas//Deadline reminders//ZH','CALSCALE:GREGORIAN'];
    for (const r of reminders) {
      if (!r.enabled || problem(r,conferences) || time(r)<=now) continue;
      const c=conferences.find(c=>c.id===r.conferenceId);
      const track=currentTrack(r,conferences),title=`${c.acronym||c.name} · ${r.trackName} · ${r.kind==='abstract'?'摘要':'全文'}截止${stageLabel(track)}`;
      lines.push('BEGIN:VEVENT',`UID:${encodeURIComponent(r.id)}@conf-atlas.local`,`DTSTAMP:${stamp(now)}`,`DTSTART:${stamp(r.deadline)}`,`SUMMARY:${icsText(title)}`,`DESCRIPTION:${icsText(stageNotice(track)+'请在提交前复核会议官方时间。')}`,'BEGIN:VALARM',`TRIGGER:${r.leadMinutes?'-PT'+r.leadMinutes+'M':'PT0M'}`,'ACTION:DISPLAY',`DESCRIPTION:${icsText(title)}`,'END:VALARM','END:VEVENT');
    }
    lines.push('END:VCALENDAR');
    // RFC 5545 folds content lines at 75 UTF-8 octets, never inside a character.
    return lines.map(line=>{let output='',part='',bytes=0;for(const char of line){const size=new TextEncoder().encode(char).length;if(bytes+size>75){output+=part+'\r\n';part=' ';bytes=1;}part+=char;bytes+=size;}return output+part;}).join('\r\n')+'\r\n';
  }
  let conferences=[],portal,notify=()=>{},refresh=()=>{},lastTick=Date.now(),scope='',delivered=new Set(),interval;
  const signedIn=()=>portal?.getScope()!=='guest'&&!!portal?.getScope();
  const loginPrompt=()=>'<section class="detail-section reminder-section"><h3>登录后，记住下一次截止。</h3><p class="muted">会议日期和投稿信息可直接浏览。收藏、设置提醒和微信绑定需要登录会投账号。</p><button class="primary-button" data-require-login>登录 / 注册后设置提醒 ↗</button></section>';
  const date = iso => new Intl.DateTimeFormat('zh-CN',{timeZone:portal.getSettings().timezone,month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(iso));
  function resetScope() {
    const next=portal.getScope();if(next===scope)return;scope=next;lastTick=Date.now();
    try{delivered=new Set(JSON.parse(localStorage.getItem('conf-atlas-delivered:'+scope)||'[]'));}catch{delivered=new Set();}
  }
  const deliveryKey = r => r.id+':'+r.deadline+':'+r.leadMinutes;
  function permission() {return typeof Notification==='undefined'?'不支持系统通知':Notification.permission==='granted'?'系统通知已允许':Notification.permission==='denied'?'系统通知已拒绝':'系统通知未授权';}
  function status(r) {return problem(r,conferences)||(!r.enabled?'已暂停':time(r)<=Date.now()?(delivered.has(deliveryKey(r))?'已在网页触发':'提醒时间已过'):'等待网页触发');}
  function renderConference(id) {
    if(!signedIn())return loginPrompt();
    const c=conferences.find(c=>c.id===id);if(!c)return '';
    const rows=(c.detail?.tracks||[]).flatMap((t,i)=>['abstract','full'].filter(kind=>t[kind+'Deadline']&&Date.parse(t[kind+'Deadline'])>Date.now()).map(kind=>({t,i,kind,deadline:t[kind+'Deadline']})));
    const existing=portal.getReminders().filter(r=>r.conferenceId===id);
    return `<section class="detail-section reminder-section"><h3>让下一次截止，有个提醒。</h3><p>选择摘要或全文节点，可添加多个提前量。保存后会同时收藏会议。</p><div class="notice amber">网页提醒需要页面保持运行。登录后可在「微信助手」绑定微信、开启 DDL 提醒；本机服务须持续运行。也可导入系统日历。</div>${rows.some(r=>stageNotice(r.t))?'<p class="notice amber">标注“仅限获邀”的节点只适用于已收到邀请的稿件，不接受普通新稿。</p>':''}${rows.length?`<form data-reminder-form="${esc(id)}"><label class="form-field"><span>截止节点</span><select name="node">${rows.map(r=>`<option value="${r.i}:${r.kind}">${esc(r.t.name)}${esc(stageLabel(r.t))} · ${r.kind==='abstract'?'摘要':'全文'} · ${esc(date(r.deadline))}</option>`).join('')}</select></label><fieldset class="reminder-leads"><legend>提前多久</legend>${Object.entries(LEADS).reverse().map(([value,label])=>`<label><input type="checkbox" name="lead" value="${value}" ${value==='1440'?'checked':''}>${label}</label>`).join('')}</fieldset><button class="primary-button" type="submit">保存提醒与收藏</button><p class="muted" data-reminder-message role="status"></p></form>`:'<p class="muted">当前会议没有已核验且尚未截止的节点。</p>'}<div class="reminder-toolbar"><button class="outline-button" data-reminder-permission>${permission()}</button><button class="outline-button" data-reminder-test>测试网页提醒</button></div><h3>这场会议的提醒 <small>${existing.length} 条</small></h3>${list(existing)}${existing.some(r=>r.enabled&&!problem(r,conferences)&&time(r)>Date.now())?`<button class="outline-button" data-reminder-export="${esc(id)}">导出提醒日历 .ics ↓</button>`:''}</section>`;
  }
  function list(items) {
    if(!items.length)return '<p class="muted">还没有提醒。进入会议详情 → 截止提醒，选择你要准备的节点。</p>';
    return `<div class="reminder-list">${items.slice().sort((a,b)=>time(a)-time(b)).map(r=>{const c=conferences.find(c=>c.id===r.conferenceId);return `<article class="reminder-item"><div><strong>${esc(c?.acronym||r.conferenceId)} · ${r.kind==='abstract'?'摘要':'全文'} · ${esc(LEADS[r.leadMinutes]||'未知提前量')}</strong><p>${esc(r.trackName)}${esc(stageLabel(currentTrack(r,conferences)))} · ${Number.isFinite(time(r))?esc(date(time(r))):'时间无效'}</p><span class="soft-pill">${esc(status(r))}</span></div><div class="reminder-actions"><button class="text-button" data-reminder-toggle="${esc(r.id)}">${r.enabled?'暂停':'启用'}</button><button class="text-button danger-text" data-reminder-remove="${esc(r.id)}">移除</button></div></article>`;}).join('')}</div>`;
  }
  function renderSummary(){resetScope();if(!signedIn())return loginPrompt();const items=portal.getReminders();return `<section class="panel reminder-summary"><div class="panel-heading"><div><h3>我的截止提醒 <span class="count-badge">${items.filter(r=>r.enabled).length}</span></h3><p class="muted">网页打开时提醒；也可在微信助手开启 DDL 推送，或导入系统日历。</p></div><button class="outline-button" data-reminder-export="all">导出日历 ↓</button></div>${list(items)}</section>`;}
  async function tick() {
    resetScope();const now=Date.now(),since=lastTick;lastTick=now;
    if(!signedIn())return;
    for (const r of portal.getReminders()) {
      const at=time(r),key=deliveryKey(r);if(!r.enabled||problem(r,conferences)||at>now||at<=since||now-at>120000||delivered.has(key))continue;
      delivered.add(key);try{localStorage.setItem('conf-atlas-delivered:'+scope,JSON.stringify([...delivered].slice(-2000)));}catch{}
      const c=conferences.find(c=>c.id===r.conferenceId),message=`${c.acronym||c.name} ${r.kind==='abstract'?'摘要':'全文'}截止${stageLabel(currentTrack(r,conferences))} · ${LEADS[r.leadMinutes]}`;
      notify(message);if(typeof Notification!=='undefined'&&Notification.permission==='granted'){try{new Notification('会投 · 截止提醒',{body:message,tag:key});}catch{}}
      refresh();
    }
  }
  function download(id) {
    if(!signedIn()){portal.requireLogin();return;}
    const reminders=portal.getReminders().filter(r=>(id==='all'||r.conferenceId===id)&&r.enabled&&!problem(r,conferences)&&time(r)>Date.now());
    if(!reminders.length){notify('没有可导出的未来提醒。');return;}
    const url=URL.createObjectURL(new Blob([calendar(reminders,conferences)],{type:'text/calendar;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='conf-atlas-reminders.ics';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);notify('日历已导出，请导入日历应用并检查通知设置。');
  }
  function init(options){({conferences,portal,notify,refresh}=options);resetScope();clearInterval(interval);interval=setInterval(tick,15000);document.addEventListener('visibilitychange',tick);
    document.addEventListener('submit',async e=>{
      const form=e.target;if(!form.matches('[data-reminder-form]'))return;e.preventDefault();if(!signedIn()){portal.requireLogin();return;}const button=form.querySelector('button[type=submit]');button.disabled=true;
      try{const c=conferences.find(c=>c.id===form.dataset.reminderForm),fd=new FormData(form),[index,kind]=fd.get('node').split(':'),track=c.detail.tracks[Number(index)],deadline=track[kind+'Deadline'];const leads=fd.getAll('lead').map(Number);
        if(!leads.length)throw new Error('请至少选择一个提前量。');
        const newItems=leads.map(leadMinutes=>({id:crypto.randomUUID(),conferenceId:c.id,trackName:track.name,kind,deadline,leadMinutes,enabled:true}));
        if(newItems.some(r=>time(r)<=Date.now()))throw new Error('部分提醒时间已过，请选择更接近截止的提前量。');
        const existing=portal.getReminders().filter(r=>!newItems.some(n=>n.conferenceId===r.conferenceId&&n.trackName===r.trackName&&n.kind===r.kind&&n.leadMinutes===r.leadMinutes));
        await portal.setReminders([...existing,...newItems],c.id);refresh();notify('提醒已保存。'+stageNotice(track)+'请保持网页打开，或导出日历。');
      }catch(error){form.querySelector('[data-reminder-message]').textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}
    });
    document.addEventListener('click',async e=>{const b=e.target.closest('[data-reminder-toggle],[data-reminder-remove],[data-reminder-export],[data-reminder-permission],[data-reminder-test]');if(!b)return;e.stopPropagation();if(!signedIn()){portal.requireLogin();return;}b.disabled=true;
      try{
        if(b.hasAttribute('data-reminder-export')){download(b.dataset.reminderExport);return;}
        if(b.hasAttribute('data-reminder-permission')){if(typeof Notification==='undefined'){notify('此浏览器不支持系统通知，可以使用日历提醒。');return;}if(Notification.permission==='denied'){notify('请在浏览器的网站权限中修改通知设置。');return;}await Notification.requestPermission();refresh();return;}
        if(b.hasAttribute('data-reminder-test')){notify('测试提醒：网页内提醒正常。');if(typeof Notification!=='undefined'&&Notification.permission==='granted'){try{new Notification('会投 · 测试提醒',{body:'测试系统通知；正式提醒仍需要网页保持运行。'});}catch{notify('系统通知不可用，网页内提醒仍可用。');}}return;}
        let next=portal.getReminders();if(b.dataset.reminderRemove)next=next.filter(r=>r.id!==b.dataset.reminderRemove);else next=next.map(r=>r.id===b.dataset.reminderToggle?{...r,enabled:!r.enabled}:r);
        await portal.setReminders(next);refresh();notify('提醒已更新');
      }catch(error){notify(error.message);}finally{if(b.isConnected)b.disabled=false;}
    });
  }
  window.ConfReminders={init,renderConference,renderSummary,stateChanged:()=>{if(portal)resetScope();}};window.ReminderModel={time,problem,calendar};
})();
