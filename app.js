'use strict';
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeUrl = value => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? u.href : ''; } catch { return ''; } };
  const link = (url, title, cls = 'source-link') => safeUrl(url) ? `<a class="${cls}" href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(title)} ↗</a>` : '';
  const DAY = 86400000;
  let CAL_ZONE = 'Asia/Singapore';
  const zoneLabel = () => ({'Asia/Singapore':'UTC+8','UTC':'UTC','America/Los_Angeles':'洛杉矶当地时间'})[CAL_ZONE];
  const PAGE_SIZE = 20;
  const areaLabels = {architecture:'体系结构与分布计算',network:'计算机网络',security:'网络与信息安全',software:'软件工程与程序语言',database:'数据库与信息检索',theory:'计算机科学理论',graphics:'图形学与多媒体',ai:'人工智能',hci:'人机交互与普适计算',interdisciplinary:'交叉与新兴领域'};
  const params = new URLSearchParams(location.search);
  let saved = new Set();
  const signedIn = () => !!window.ConfPortal?.getUser();
  let data, conferences = [], activeId = null, activeTab = 'overview', previousFocus, toastTimer;
  const state = {rank: params.get('rank') || 'all', area: params.get('area') || 'all', q: params.get('q') || '', status: params.get('status') || 'all', coverage: params.get('coverage') || 'all', sort: params.get('sort') || 'deadline', view: params.get('view') || 'explore', page: 1};
  const today = new Date();
  let calendarMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const deadlineEntries = c => (c.detail?.tracks || []).flatMap((t, i) => ['abstractDeadline', 'fullDeadline'].filter(k => t[k]).map(k => ({conf:c,track:t,trackIndex:i,kind:k,date:new Date(t[k]),iso:t[k]}))).filter(e => Number.isFinite(e.date.getTime()));
  const primaryTrack = c => (c.detail?.tracks||[]).find(t=>t.primary)||c.detail?.tracks?.[0];
  const nearest = c => {
    const primary=primaryTrack(c);
    if(!primary||primary.submissionStage==='invitation-only')return null;
    return deadlineEntries(c).find(e=>e.track===primary&&e.kind==='fullDeadline') ||
      (!primary.fullDeadlineDate ? deadlineEntries(c).find(e=>e.track===primary&&e.kind==='abstractDeadline') : null) || null;
  };
  const submissionDay = t => t?.fullDeadlineDate || (!t?.fullDeadline ? t?.abstractDeadlineDate : null);
  const openTrack = t => {
    if(!t || t.submissionStage==='invitation-only')return false;
    if(t.deadlineMode==='rolling')return true;
    const iso=t.fullDeadline||(!t.fullDeadlineDate?t.abstractDeadline:null);
    if(iso)return new Date(iso)>Date.now();
    // A later date even in UTC+14 is safely in the future without guessing the
    // deadline's clock. Boundary dates stay in the date-only filter.
    return !!submissionDay(t)&&submissionDay(t)>zoneDate(new Date(),'Pacific/Kiritimati');
  };
  const otherUpcoming = c => (c.detail?.tracks||[]).filter(t=>t!==primaryTrack(c)&&openTrack(t)).length;
  const statusOf = c => {
    const d=nearest(c),t=primaryTrack(c);
    if(d)return d.date>Date.now()?(d.date-Date.now()<30*DAY?'soon':'upcoming'):'closed';
    if(t?.deadlineMode==='rolling')return 'rolling';
    if(submissionDay(t))return submissionDay(t)<zoneDate(new Date(),'Etc/GMT+12')?'closed':'date-only';
    return 'unknown';
  };
  const zoneDate = (date, zone=CAL_ZONE) => new Intl.DateTimeFormat('en-CA', {timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
  const localDeadline = iso => new Intl.DateTimeFormat('zh-CN', {timeZone:CAL_ZONE,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(iso));
  let deadlineFingerprint = '';
  const rawDate = iso => iso ? iso.slice(0,10) : '待核验';
  const displayDate = date => date ? date.replaceAll('-', '.') : '待核验';
  const conferenceName = c => c.acronym || c.name;
  const eventRange = event => !event?.start ? '日期待核验' : event.end && event.end !== event.start ? `${displayDate(event.start)} — ${displayDate(event.end)}` : displayDate(event.start);
  function countdown(iso) {
    const diff = new Date(iso) - Date.now();
    if (diff <= 0) return '<span class="countdown closed">已截止</span>';
    const days = Math.floor(diff / DAY), hours = Math.floor(diff % DAY / 3600000), minutes = Math.floor(diff % 3600000 / 60000);
    const label = days > 0 ? `剩余 ${days} 天 ${hours} 小时` : hours > 0 ? `剩余 ${hours} 小时 ${minutes} 分` : minutes > 0 ? `剩余 ${minutes} 分钟` : '不足 1 分钟';
    return `<span class="countdown ${diff < 30*DAY ? 'soon' : ''}" data-countdown="${esc(iso)}"><i class="countdown-dot"></i>${label}</span>`;
  }
  function persistState() {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) if (k !== 'page' && v && v !== 'all' && !(k==='view' && v==='explore') && !(k==='sort' && v==='deadline')) p.set(k,v);
    try { history.replaceState(null, '', location.pathname + (p.size ? '?' + p : '')); } catch { /* file:// browsers may restrict History; filters still work. */ }
  }
  function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 3000); }
  async function toggleFavorite(id) {
    if(!window.ConfPortal.requireLogin())return;
    if(saved.has(id))saved.delete(id);else saved.add(id);
    render();if(activeId){renderDrawer();$('#detail-drawer [data-save]')?.focus();}
    try{await window.ConfPortal.setFavorites([...saved]);toast(saved.has(id)?'已加入收藏，保存至账号':'已取消收藏');}
    catch(error){saved=new Set(window.ConfPortal.getFavorites());render();if(activeId)renderDrawer();toast('保存失败：'+error.message);}
  }
  function filtered() {
    const q = state.q.trim().toLowerCase();
    const list = conferences.filter(c => (state.coverage==='all'||(state.coverage==='details'?!!c.detail:!c.detail)) && (state.rank === 'all' || c.rank === state.rank) && (state.area === 'all' || c.areaId === state.area) && (state.view !== 'favorites' || saved.has(c.id)) && (!q || [c.acronym,c.name,c.area,...(c.aliases||[]),...(c.detail?.tracks||[]).map(t=>t.name)].join(' ').toLowerCase().includes(q)) && (state.status === 'all' || (state.status === 'any-upcoming' ? (c.detail?.tracks||[]).some(openTrack) : state.status === 'upcoming' ? openTrack(primaryTrack(c)) : state.status==='date-only'?!!submissionDay(primaryTrack(c))&&!nearest(c):state.status === statusOf(c))));
    return list.sort((a,b) => {
      if (state.sort === 'name') return conferenceName(a).localeCompare(conferenceName(b),'en');
      if (state.sort === 'rank') return a.rank.localeCompare(b.rank) || conferenceName(a).localeCompare(conferenceName(b),'en');
      const da = nearest(a), db = nearest(b), now = Date.now();
      const key = (c,d) => d ? (d.date > now ? 0 : 1) : c.detail ? 2 : 3;
      return key(a,da) - key(b,db) || (da && db ? (da.date > now && db.date > now ? da.date-db.date : db.date-da.date) : 0) || conferenceName(a).localeCompare(conferenceName(b),'en');
    });
  }
  function renderMetrics() {
    $('#metric-total').textContent = conferences.length;
    $('#metric-soon').textContent = conferences.filter(c => statusOf(c)==='soon').length;
    const detailed=conferences.filter(c => c.detail).length;
    $('#metric-details').textContent = detailed;
    $('#metric-detail-note').textContent = `有届次资料 · 各字段覆盖率见下方`;
    const cov=data.coverage;
    $('#coverage-note').textContent = `CCF 全部 10 个学科，共 ${conferences.length} 场；${detailed} 场有届次资料，${cov.eventDates||0} 场有会期，${cov.submissionLinks||0} 个 Track 有投稿入口。已核验 ${cov.acceptanceRecords} 条年度录用统计、${cov.attendanceVerified} 条年度参会政策；有详情不代表全部字段齐全。快照日期 ${data.asOf}，不会自动更新；仅有日期的节点不生成倒计时，获邀阶段不作为开放投稿机会。`;
    document.documentElement.dataset.authenticated=String(signedIn());
    $('.nav-item[data-view="favorites"]').hidden=!signedIn();
    for (const rank of ['all','A','B','C','N']) $('#count-'+rank).textContent = rank==='all' ? conferences.length : conferences.filter(c=>c.rank===rank).length;
    $('#favorite-count').textContent = [...saved].filter(id => conferences.some(c=>c.id===id)).length;
  }
  function render() {
    if (!data) return;
    if(state.view==='favorites'&&!signedIn()&&window.ConfPortal.isConnected()!==null)state.view='account';
    persistState(); renderMetrics();
    const names = {explore:['会议探索','下一篇，投向哪里<span>？</span>','从一个好问题出发，找到值得抵达的会议。','探索会议'],favorites:['我的收藏','留给好想法的，下一站。','收藏心仪的会议，把研究节奏掌握在自己手里。','收藏的会议'],calendar:['截止日历','把下一站，放进日程。','摘要与全文各有节点，为充分准备留出时间。','投稿日历'],relax:['研究者解压室','先别卷，敲一下。','好论文值得努力，你也值得休息。',''],wechat:['微信助手','在微信里，问问下一站。','查会议、存收藏、设截止提醒。会投也可以陪你在聊天里安排研究节奏。',''],account:['用户中心','你的研究，有个专属空间。','管理账号，保存收藏，也记住每一点小小的进展。',''],services:['服务与合作','有问题，来信聊聊。','API、论文、AI 服务，以及使用反馈与建议。',''],settings:['设置','舒服一点，才看得更远。','主题、字号、时区与声音，按你的习惯来。','']};
    const ns = names[state.view];
    $('#breadcrumb-view').textContent=ns[0]; $('#page-title').innerHTML=ns[1]; $('#page-subtitle').textContent=ns[2]; $('#list-title').textContent=ns[3];
    $$('.nav-item').forEach(b => b.classList.toggle('active',b.dataset.view === state.view));
    const special=['relax','account','settings','wechat','services'].includes(state.view);$('#secondary-view').hidden=!special;$('#dashboard-view').hidden=special;$('#calendar-shortcut').hidden=special;
    if(special){window.ConfPortal.render(state.view);return;}window.ConfPortal.leave();$('#reminder-overview').hidden=state.view!=='favorites';if(state.view==='favorites')$('#reminder-overview').innerHTML=window.ConfReminders.renderSummary();
    $$('.rank-tab').forEach(b=> {b.classList.toggle('selected', b.dataset.rank === state.rank);b.setAttribute('aria-pressed',String(b.dataset.rank === state.rank));});
    $$('#area-nav button').forEach(b=>b.classList.toggle('selected',b.dataset.area===state.area));
    $('#search').value=state.q; $('#area-select').value=state.area; $('#status-select').value=state.status; $('#sort-select').value=state.sort; $('#coverage-select').value=state.coverage;
    const list=filtered(); $('#result-count').textContent=list.length;
    const active = [];
    if(state.area!=='all') active.push(areaLabels[state.area]||state.area);
    if(state.coverage!=='all')active.push($('#coverage-select').selectedOptions[0]?.textContent||state.coverage);
    if(state.q) active.push(`“${state.q}”`);
    if(state.status!=='all') active.push($('#status-select').selectedOptions[0]?.textContent || state.status);
    $('#active-filter').hidden=!active.length;
    $('#active-filter').innerHTML=active.length ? `${esc(active.join(' · '))} <button data-action="reset">清除筛选</button>` : '';
    $('#table-view').hidden=state.view==='calendar'; $('#calendar-view').hidden=state.view!=='calendar'; $('#pagination').hidden=state.view==='calendar';
    if(state.view==='calendar') renderCalendar(list); else renderTable(list);
  }
  function renderListDeadline(c) {
    const d=nearest(c), primary=primaryTrack(c);
    let output;
    if(d){
      const tz=d.track[d.kind==='fullDeadline'?'fullTimezone':'abstractTimezone']||d.track.timezone||'原时区';
      output=`<div class="deadline-date">${esc(rawDate(d.iso))}<span class="deadline-time">${esc(tz.includes('AoE')?'AoE':tz)}</span></div>${countdown(d.iso)}<div class="subline" title="${esc(d.track.name)}">${d.kind==='abstractDeadline'?'摘要 / 初投 · ':''}${esc(d.track.name)}</div>`;
    }else if(primary?.fullDeadlineDate||primary?.abstractDeadlineDate){
      const day=primary.fullDeadlineDate||primary.abstractDeadlineDate;
      output=`<div class="deadline-date">${esc(day)}</div><div class="subline">${!primary.fullDeadlineDate?'摘要 / 初投 · ':''}仅确认日期 · 时刻或时区待核验</div>`;
    }else output=primary?.deadlineMode==='rolling'?'<span class="area-pill">滚动投稿</span>':'<span class="unknown">主 Track 日期待核验</span>';
    return output+(otherUpcoming(c)?`<span class="other-tracks">另有 ${otherUpcoming(c)} 个其他 Track 未截止 ↗</span>`:'');
  }
  function renderTable(list) {
    const pages=Math.max(1,Math.ceil(list.length/PAGE_SIZE)); state.page=Math.min(state.page,pages);
    const start=(state.page-1)*PAGE_SIZE;
    $('#conference-body').innerHTML=list.length ? list.slice(start,start+PAGE_SIZE).map(c=>{
      const event=c.detail?.event;
      return `<tr data-conf="${esc(c.id)}"><td class="favorite-cell"><button class="star-button ${saved.has(c.id)?'saved':''}" data-save="${esc(c.id)}" title="${signedIn()?(saved.has(c.id)?'取消收藏':'收藏会议'):'收藏会议前请先登录'}" aria-label="${saved.has(c.id)?'取消收藏':'收藏'} ${esc(conferenceName(c))}" aria-pressed="${saved.has(c.id)}">${saved.has(c.id)?'★':'☆'}</button></td><td><button class="conf-name conf-open" data-open="${esc(c.id)}">${esc(conferenceName(c))}${c.detail?.year?`<span class="conf-year">${c.detail.year}</span>`:''}</button><div class="conf-full" title="${esc(c.name)}">${esc(c.name)}</div></td><td><span class="rank-badge ${c.rank}" title="${c.rank==='N'?'本站自定义未分级分类':'CCF 第七版 '+c.rank+' 类'}">${c.rank}</span></td><td><span class="area-pill" title="${esc(c.area)}">${esc(areaLabels[c.areaId]||c.area)}</span></td><td>${event?.location?`<div class="location">${esc(event.location)}</div><div class="subline">${esc(eventRange(event))}</div>`:'<span class="unknown">届次信息待补全</span>'}</td><td>${renderListDeadline(c)}</td><td class="row-arrow">↗</td></tr>`;
    }).join('') : `<tr><td colspan="7"><div class="empty-state"><strong>${state.view==='favorites' && !saved.size?'把下一站，先收藏起来。':'没有找到匹配的会议'}</strong><p>${state.view==='favorites'&&!saved.size?'点击会议左侧的星标，即可加入收藏。':'试试会议英文简称，或放宽分区和学科筛选。'}</p><button class="outline-button" data-action="${state.view==='favorites'&&!saved.size?'explore':'reset'}">${state.view==='favorites'&&!saved.size?'探索会议 ↗':'清除筛选'}</button></div></td></tr>`;
    const nums=[...new Set([1,state.page-1,state.page,state.page+1,pages])].filter(p=>p>=1&&p<=pages).sort((a,b)=>a-b);
    let prev=0;
    $('#pagination').innerHTML=`<span>${list.length ? `${start+1}–${Math.min(start+PAGE_SIZE,list.length)}`:'0'} / ${list.length} 场会议 <span class="pagination-hint">· 点击会议查看详情</span></span><div class="pagination-actions"><button class="page-button" data-page="${state.page-1}" ${state.page===1?'disabled':''} aria-label="上一页">‹</button>${nums.map(p=>{const s=prev&&p-prev>1?'<span>…</span>':'';prev=p;return s+`<button class="page-button ${p===state.page?'current':''}" data-page="${p}" ${p===state.page?'aria-current="page"':''}>${p}</button>`;}).join('')}<button class="page-button" data-page="${state.page+1}" ${state.page===pages?'disabled':''} aria-label="下一页">›</button></div>`;
  }
  function renderCalendar(list) {
    const year=calendarMonth.getFullYear(), month=calendarMonth.getMonth();
    const first=new Date(year,month,1), offset=(first.getDay()+6)%7;
    const start=new Date(year,month,1-offset);
    const events=list.flatMap(deadlineEntries).sort((a,b)=>a.date-b.date);
    const monthPrefix=`${year}-${String(month+1).padStart(2,'0')}`;
    const monthEvents=events.filter(e=>zoneDate(e.date).startsWith(monthPrefix));
    const next=events.find(e=>e.date>Date.now());
    const todayKey=zoneDate(new Date());
    $('#calendar-view').innerHTML=`<div class="calendar-header"><strong>${year} 年 ${month+1} 月 <span class="match-count">${monthEvents.length} 个节点</span></strong><div class="calendar-controls"><button data-month="-1" aria-label="上个月">‹</button><button data-month="today">今天</button><button data-month="1" aria-label="下个月">›</button>${next?'<button data-month="next">下个截止日 ↗</button>':''}</div></div><div class="calendar-scroll"><div class="calendar-grid">${['一','二','三','四','五','六','日'].map(d=>`<div class="calendar-weekday">周${d}</div>`).join('')}${Array.from({length:42},(_,i)=>{const d=new Date(start);d.setDate(start.getDate()+i);const key=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;return `<div class="calendar-cell ${d.getMonth()!==month?'outside':''} ${key===todayKey?'today':''}"><span class="calendar-day">${d.getDate()}</span>${events.filter(e=>zoneDate(e.date)===key).map(e=>`<button class="calendar-event ${e.kind==='abstractDeadline'?'abstract':''}" data-open="${esc(e.conf.id)}" title="${esc(e.track.name+' · '+localDeadline(e.iso))}">${esc(conferenceName(e.conf))} · ${e.kind==='abstractDeadline'?'摘要':'全文'}${e.track.submissionStage==='invitation-only'?' · 仅限获邀':''}</button>`).join('')}</div>`;}).join('')}</div></div><div class="calendar-note">日历显示 ${esc(zoneLabel())}；详情保留来源时区。蓝色为全文截止，橙色为摘要 / 注册截止。仅包含已核验精确时刻的节点；只公布日期、缺少时刻或时区的截止信息保留在详情，不生成提醒节点。未收录节点不代表没有截止日期。</div><div class="calendar-agenda">${monthEvents.length?monthEvents.map(e=>`<button class="agenda-row" data-open="${esc(e.conf.id)}"><time>${esc(localDeadline(e.iso).slice(5))}</time><strong>${esc(conferenceName(e.conf))}</strong><span>${esc(e.track.name)} · ${e.kind==='abstractDeadline'?'摘要':'全文'}${e.track.submissionStage==='invitation-only'?' · 仅限获邀':''}</span></button>`).join(''):'<div class="empty-state"><strong>这个月暂无已核验的截止日期</strong><p>可以切换月份，或跳转到下个截止日。</p></div>'}</div>`;
  }
  function showView(view) {if(view==='favorites'&&!window.ConfPortal.requireLogin())return;state.view=view;state.page=1;render();window.scrollTo({top:0,behavior:'instant'});}
  function resetFilters() {Object.assign(state,{rank:'all',area:'all',q:'',status:'all',coverage:'all',page:1});render();}
  function openDetail(id) {
    if (!conferences.some(c=>c.id===id)) return;
    previousFocus=document.activeElement;activeId=id;activeTab='overview';
    renderDrawer(); $('#detail-drawer').hidden=false;$('#drawer-backdrop').hidden=false;
    $('.app-shell').inert=true;$('.sidebar').inert=true;document.body.style.overflow='hidden';
    $('#close-drawer').focus();
  }
  function closeDetail() {const returnId=activeId;$('#detail-drawer').hidden=true;$('#drawer-backdrop').hidden=true;$('.app-shell').inert=false;$('.sidebar').inert=false;document.body.style.overflow='';activeId=null;if(previousFocus?.isConnected)previousFocus.focus();else (document.querySelector('[data-open="'+returnId+'"]') || $('#search')).focus();}
  const trackTitle = t => t.name || 'Research Track';
  function sourceList(sources) {return (sources||[]).filter(Boolean).map((s,i)=>link(typeof s==='string'?s:s.url,typeof s==='string'?`官方来源 ${i+1}`:s.label||`来源 ${i+1}`)).join(' · ');}
  function renderRankings(c) {
    const cards=[['CORE / ICORE','core'],['TH-CPL','thcpl']].map(([label,key])=>{
      const entry=c.rankings?.[key]||{},source=data.rankingSources?.[key]||{};
      const rank=entry.rank,listed=entry.status==='listed-unranked',version=entry.version||source.version||'版本待核验';
      const sourceUrl=entry.source||source.source||source.url;
      const targetUrl=entry.sourcePage&&sourceUrl?sourceUrl.split('#')[0]+'#page='+entry.sourcePage:sourceUrl;
      const raw=(entry.sourceRank||'').toLowerCase();
      const statusLabel=raw==='multiconference'?'会议群':raw.startsWith('journal')?'期刊发表':raw.startsWith('national')?'地区性会议':raw.startsWith('unranked')?'未评级':entry.sourceRank||'目录未评级';
      return `<div class="ranking-card"><div class="ranking-label">${label}</div><strong class="${rank?'':'rank-unconfirmed'}">${rank?esc(rank):listed?esc(statusLabel):'未确认'}</strong><small>${esc(version)}</small>${link(targetUrl,(entry.sourceLabel||'查看分级来源')+(entry.sourcePage?` · 第 ${entry.sourcePage} 页`:''))}${rank&&entry.note?`<span class="ranking-unknown">${esc(entry.note)}</span>`:''}${!rank?`<span class="ranking-unknown">${listed?esc(entry.note||'该目录已收录，评级状态见来源原文'):'尚未匹配公开目录，不等于未评级'}</span>`:''}</div>`;
    });
    return `<section class="conference-rankings" aria-label="会议分级参考">${cards.join('')}</section><p class="rankings-note">各体系独立分级；TH-CPL 为公开的 2019 版，不能代替当前认定标准。</p>`;
  }
  function renderDrawer() {
    const c=conferences.find(c=>c.id===activeId);if(!c)return;
    const d=c.detail;
    $('#detail-drawer').innerHTML=`<div class="drawer-head"><div class="drawer-top"><div class="drawer-top-left"><span class="rank-badge ${c.rank}">${c.rank}</span>${c.rank==='N'?'本站收录 · CCF 未分级':'CCF 第七版 · '+c.rank+' 类'}<span> / ${esc(areaLabels[c.areaId]||c.area)}</span></div><div class="drawer-controls"><button class="star-button ${saved.has(c.id)?'saved':''}" data-save="${esc(c.id)}" title="${signedIn()?(saved.has(c.id)?'取消收藏':'收藏会议'):'收藏会议前请先登录'}" aria-label="${saved.has(c.id)?'取消收藏':'收藏'} ${esc(conferenceName(c))}" aria-pressed="${saved.has(c.id)}">${saved.has(c.id)?'★':'☆'}</button><button class="icon-button" id="close-drawer" aria-label="关闭会议详情">×</button></div></div><h2 id="detail-title">${esc(conferenceName(c))}${d?.year?`<span>${d.year}</span>`:''}</h2><div class="drawer-fullname">${esc(c.name)}</div><div class="drawer-meta"><span>${esc(d?.event?.location||'举办地点待核验')}</span><span>${esc(d?eventRange(d.event):'届次信息待补全')}</span></div>${renderRankings(c)}</div><div class="drawer-tabs" role="group" aria-label="会议详情栏目">${[['overview','投稿详情'],['reminders','截止提醒'],['stats','录用统计'],['papers','精选论文'],['attendance','参会要求'],['sources','数据来源']].map(([key,title])=>`<button class="drawer-tab ${activeTab===key?'active':''}" data-tab="${key}" aria-pressed="${activeTab===key}">${title}</button>`).join('')}</div><div class="drawer-content">${activeTab==='overview'?renderOverview(c):activeTab==='reminders'?window.ConfReminders.renderConference(c.id):activeTab==='stats'?renderStats(c):activeTab==='papers'?renderPapers(c):activeTab==='attendance'?renderAttendance(c):renderSources(c)}<div class="drawer-footer">${d?`详情核验：${esc(d.verifiedDate||data.asOf)}`:'尚未补全届次详情'} · 分级版本：${esc(data.version)}<br>个人维护不易，信息仅供参考，具体请以会议官网为准。<br>会议分级请同时核对各目录发布方；截止时间可能调整，提交前请再次确认。</div></div>`;
    $('#close-drawer').onclick=closeDetail;
  }
  function renderDetailAudit(c) {
    const a=c.detailAudit;if(!a)return '';
    const labels={pending:'待继续核验',partial:'部分资料已核对',unavailable:'来源暂不可用',complete:'资料已核对'};
    const fields={edition:'最近届次',event:'会期与地点',tracks:'投稿 Track',templates:'模板与格式要求',
      'acceptance2023-2025':'2023–2025 逐年录用整数统计','attendance2023-2025':'2023–2025 作者参会要求',
      curatedPapers2025:'2025 获奖及精选论文',allTracksCoverage:'其他 Track 是否完整',
      'submission-portals':'官方投稿入口','exact-deadline-timezones':'截止的准确时刻与时区',
      'event-dates':'举办日期','event-location':'举办地点','best-papers-2025':'2025 获奖及精选论文'};
    const fieldLabel=x=>fields[x]||x.replace(/^acceptance-(\d{4})$/,'$1 录用整数统计').replace(/^attendance-(\d{4})$/,'$1 作者参会要求');
    return `<div class="notice detail-audit"><strong>${esc(labels[a.status]||'核验进度')}${a.checkedAt?' · '+esc(a.checkedAt):''}</strong>${a.note?`<p>${esc(a.note)}</p>`:''}${a.missingFields?.length?`<details><summary>仍需补全的资料 · ${a.missingFields.length} 项</summary><ul>${a.missingFields.map(x=>`<li>${esc(fieldLabel(x))}</li>`).join('')}</ul></details>`:''}<p>有届次详情不代表所有字段齐全；各栏目继续明确显示未公布或未核实信息。</p></div>`;
  }
  function renderOverview(c) {
    const d=c.detail;
    const rankNote=c.rank==='N' ? `<div class="notice">N 是本站自定义分类，不属于 CCF 分级。${esc(c.inclusionReason||'该会议未见于当前 CCF 目录。')}</div>` : '<div class="notice">CCF 分级适用于目录规定的 Full / Regular papers。下列 Short、Demo、Findings、Workshop 等 Track 不应自动视为同一 CCF 分级。</div>';
    if(!d) return `${rankNote}${renderDetailAudit(c)}<section class="detail-section"><h3>目录已收录，详情正在完善</h3><p>${c.rank==='N'?'此条目已核验会议名称与本站收录依据':'此条目已核验 CCF 目录中的会议名称、学科与分级'}。当前尚未核验最新届次、Track、投稿入口、模板及截止日期。</p>${link(c.officialUrl,'会议官网','link-button')}${link(c.catalogUrl,'历届论文 · DBLP','link-button')}${link(c.sourcePdf?c.sourcePdf+'#page='+c.sourcePage:c.ccfSource,'分级依据','link-button')}</section>`;
    const notices=(d.notes||[]).map(n=>`<p>${esc(n)}</p>`).join('');
    return `${rankNote}${renderDetailAudit(c)}${(d.event?.end ? d.event.end < new Date().toISOString().slice(0,10) : d.year < new Date().getFullYear())?'<div class="notice amber">这里展示的是最近已核验的历史届次，下一届信息尚未补全。</div>':''}<section class="detail-section"><h3>会议与投稿入口</h3>${link(d.officialUrl,'会议官网','link-button')}${link(d.event?.source,'举办信息来源','link-button')}${link(c.catalogUrl,'历届论文 · DBLP','link-button')}${d.event?.additionalLocations?.length?`<p>${esc(d.event.additionalLocations.map(e=>`${e.location}：${eventRange(e)}`).join('；'))}</p>`:''}${notices}</section><section class="detail-section"><h3>Tracks 与截止日期 <small>${d.tracks.length} 个已核验条目 · 非完整列表</small></h3>${d.tracks.map((t,i)=>renderTrack(t,i,c)).join('')||'<div class="notice">Track 信息待核验。</div>'}</section>`;
  }
  function renderTrack(t,i,c) {
    const block=(label,iso,kind)=>{
      const day=t[kind+'DeadlineDate'],rolling=kind==='full'&&t.deadlineMode==='rolling';
      return `<div class="deadline-block"><label>${label}</label><strong>${iso?esc(rawDate(iso)+' '+iso.slice(11,16)):day?esc(day):rolling?'滚动投稿':'待公布 / 待核验'}</strong><small>${iso?esc(t[kind+'Timezone']||t.timezone||'见来源时区'):day?'官方仅确认日期，时刻或时区未核实；不计算倒计时。':rolling?'没有单一年度全文截止时间，请查看官方投稿周期。':esc(t.deadlineNote||'未获得可核验的官方日期')}${iso?`<br>${esc(zoneLabel())}：${esc(localDeadline(iso))}`:''}</small>${iso?countdown(iso):''}</div>`;
    };
    const tm=t.template;
    return `<article class="track-card"><div class="track-title"><span>${esc(trackTitle(t))}</span>${(t.fullDeadline||t.abstractDeadline||t.fullDeadlineDate||t.abstractDeadlineDate||t.deadlineMode==='rolling')?link((t.sources||[])[0]?.url||(t.sources||[])[0],'日期依据'):''}</div><div class="track-body">${t.submissionStage==='invitation-only'?'<div class="notice amber">仅限获邀稿件；此阶段不接受普通新稿。</div>':''}<div class="deadline-grid">${block('摘要 / 注册截止',t.abstractDeadline,'abstract')}${block('全文截止',t.fullDeadline,'full')}</div>${t.deadlineSourceLabel?`<div class="${t.deadlineConflict?'deadline-evidence':'notice'}"><strong>${t.deadlineConflict?'来源存在差异 · ':'已核验 · '}</strong>${esc(t.deadlineSourceLabel)}${t.deadlineConflict?`<br>官网摘要：${esc(t.announcedAbstractDeadline||'未单列')}<br>官网全文：${esc(t.announcedFullDeadline||'未单列')}${t.portalListedFullDeadline?'<br>入口说明的全文时间：'+esc(t.portalListedFullDeadline):''}`:''}</div>`:''}<div class="track-links">${t.submissionUrl?link(t.submissionUrl,t.submissionLabel||'投稿入口','link-button'):'<span class="unknown">投稿入口待核验</span>'}${link(t.submissionInfoUrl,'官方投稿说明','link-button')}${link(t.commitmentUrl,'Commitment 入口','link-button')}${tm?.url?link(tm.url,`${tm.status==='not-required'?'官方格式说明':'论文模板'}${tm.year?' · '+tm.year:''}`,'link-button'):'<span class="unknown">模板待核验</span>'}${(t.fullDeadline||t.abstractDeadline)?`<button class="link-button" data-export="${esc(c.id)}" data-track="${i}">导出日历 ↓</button>`:''}</div>${tm?.status==='fallback'?`<span class="template-fallback">沿用 ${esc(tm.year)} 年模板 · ${esc(tm.note||'最新届次模板未核验，请以官方后续更新为准')}</span>`:tm?.note?`<p class="track-note">${esc(tm.note)}</p>`:''}${t.note?`<p class="track-note">${esc(t.note)}</p>`:''}<div style="margin-top:10px">${sourceList(t.sources)}</div></div></article>`;
  }
  function renderStats(c) {
    const records=c.detail?.acceptance||[];
    return `<section class="detail-section"><h3>近三个完整年度 <small>${data.acceptanceWindow.join(' / ')}</small></h3><p>整数比为「录用篇数 / 投稿篇数」，百分比由同一组整数计算。缺少任一整数时不反推；不同年份的统计口径可能不同。</p><table class="stat-table"><thead><tr><th>年份</th><th>录用 / 投稿</th><th>录用率</th><th>口径与依据</th></tr></thead><tbody>${data.acceptanceWindow.map(year=>{const a=records.find(r=>r.year===year);const valid=Number.isInteger(a?.accepted)&&Number.isInteger(a?.submitted)&&a.submitted>0;const rate=valid?a.accepted/a.submitted*100:null;return `<tr><td>${year}</td><td class="stat-number">${valid?`${a.accepted.toLocaleString('en-US')} / ${a.submitted.toLocaleString('en-US')}`:'— / —'}</td><td>${valid?`<div class="rate-value">${rate.toFixed(2)}%</div><div class="rate-bar"><i style="width:${Math.min(100,rate)}%"></i></div>`:'<span class="unknown">待核验</span>'}</td><td class="stat-scope">${esc(a?.scope||'尚未核验成对原始数量')}<br>${sourceList(a?.sources)}</td></tr>`;}).join('')}</tbody></table>${records.filter(r=>r.note).map(r=>`<p><strong>${r.year}：</strong>${esc(r.note)}</p>`).join('')}<div class="notice" style="margin-top:20px">本页不以混合 Track 的整体数据替代主会录用率。统计口径中的有效送审、撤稿、desk reject、长短论文及 Findings 差异，请连同来源阅读。</div></section>`;
  }
  function renderPapers(c) {
    const selection=c.detail?.curatedPapers;
    const b=c.detail?.bestPapers,items=(selection?.items||b?.items||[]).slice(0,10);
    return `<section class="detail-section"><h3>${data.bestPaperYear} 年精选论文 <small>${items.length} / 10 篇 · Best 优先</small></h3><p>优先保留 Best / Outstanding Paper，名额内以已核验的 Oral / Spotlight 补充。主题标签按论文内容人工归纳，不是官方分类。</p>${selection?.selectionNote?`<div class="notice">${esc(selection.selectionNote)}</div>`:''}${items.length?items.map((p,i)=>`<article class="paper-item"><span class="paper-number">${String(i+1).padStart(2,'0')}</span><div>${link(p.url,p.title,'paper-title')}${['award-list','program-entry'].includes(p.linkType)?`<p class="subline">链接至${p.linkType==='award-list'?'官方获奖名单':'官方议程'}；独立论文地址尚未核验。</p>`:''}<div class="paper-award"><span class="paper-type ${p.presentationType==='best'||(!p.presentationType&&/best|outstanding/i.test(p.award))?'best':''}">${esc(p.award||'类别待核验')}</span>${p.topic?`<span class="topic-tag">${esc(p.topic)}</span>`:''}${p.source?link(p.source,'类别依据'):''}${p.awardSource&&p.awardSource!==p.source?link(p.awardSource,'奖项依据'):''}</div></div></article>`).join(''):'<div class="notice">该会议尚未核验到可列出的精选论文。不会用普通论文冒充 Best、Oral 或 Spotlight。</div>'}${!selection&&b?.note?`<p>${esc(b.note)}</p>`:''}${b?.source?`<p>${link(b.source,'官方奖项列表','link-button')}</p>`:''}${selection?.sources?.length?`<p>${sourceList(selection.sources)}</p>`:''}</section>`;
  }
  function renderAttendance(c) {
    const rows=c.detail?.attendance||[];
    const labels={required:'至少一位作者须现场', 'remote-allowed':'明确允许远程', conditional:'有条件或分 Track', 'not-held':'该年未举办',unknown:'未核实'};
    return `<section class="detail-section"><h3>近三年线下参会要求 <small>${data.acceptanceWindow.join(' / ')}</small></h3><p>这里核验的是作者展示论文的要求。至少一位作者现场，并不等于所有共同作者都必须到场；举办线下会议也不自动意味着强制现场。</p><div class="attendance-list">${data.acceptanceWindow.map(year=>{const r=rows.find(x=>x.year===year)||{year,status:'unknown',summary:'尚未找到足以判断的官方作者展示政策。'};return `<article class="attendance-card"><div class="attendance-card-header"><strong>${year}</strong><span class="policy-badge ${esc(r.status)}">${esc(labels[r.status]||'未核实')}</span></div><p>${esc(r.summary)}</p>${r.scope?`<p>适用范围：${esc(r.scope)}</p>`:''}${sourceList(r.sources)}${r.verifiedDate?`<div class="subline">核验：${esc(r.verifiedDate)}</div>`:''}</article>`;}).join('')}</div><div class="notice" style="margin-top:18px">历史政策帮助了解往届要求，不代表当前届次政策。例外申请、签证豁免和远程形式请查看相应年份的原文。</div></section>`;
  }
  function allSources(c) {
    const list=[]; const add=(url,label)=>{if(safeUrl(url)&&!list.some(s=>s.url===url))list.push({url,label});};
    if(c.rank!=='N') {add(c.ccfSource,'CCF 官方目录发布说明');add(c.sourcePdf,'正式版目录 PDF · 第 '+c.sourcePage+' 页（大学图书馆镜像）');}
    add(c.catalogUrl,'目录收录的 DBLP 文献索引');add(c.officialUrl,'会议官网');
    const d=c.detail;if(d){add(d.officialUrl,'当前届次官网');add(d.event?.source,'举办日期与地点');for(const t of d.tracks||[]){for(const s of t.sources||[])add(s.url||s,t.name+' · 投稿依据');}for(const a of d.acceptance||[])for(const s of a.sources||[])add(s.url||s,a.year+' · 录用统计');add(d.bestPapers?.source,'2025 · 官方奖项');for(const s of d.sources||[])add(s.url||s,s.label||'补充来源');}
    for(const r of d?.attendance||[])for(const s of r.sources||[])add(s.url||s,r.year+' · 参会政策');for(const p of d?.curatedPapers?.items||[])add(p.source,'精选论文 · '+p.award);for(const s of c.sources||[])add(s.url||s,s.label||'收录依据');for(const s of c.detailAudit?.officialSources||[])add(s.url||s,s.label||'本次核对来源');return list;
  }
  function renderSources(c) {return `<section class="detail-section"><h3>从信息，回到证据</h3><p>会议分级、届次和统计分别核验。目录链接可能指向 DBLP 文献索引，并不等同于投稿入口。</p>${allSources(c).map(s=>`<div class="source-item">${link(s.url,s.label,'')}<p>${esc(new URL(s.url).hostname)}</p></div>`).join('')}${c.rank!=='N'?`<p>${esc(data.provenanceNote)}</p>`:''}</section>`;}
  function exportCalendar(id,index) {
    const c=conferences.find(c=>c.id===id), t=c?.detail?.tracks[index];if(!t)return;
    const utc=iso=>new Date(iso).toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z/,'Z');
    const icsText=s=>String(s).replace(/\\/g,'\\\\').replace(/\n/g,'\\n').replace(/,/g,'\\,').replace(/;/g,'\\;');
    const events=['abstractDeadline','fullDeadline'].filter(k=>t[k]).map(k=>['BEGIN:VEVENT',`UID:${id}-${c.detail.year}-${index}-${k}@conf-atlas.local`,`DTSTAMP:${utc(new Date().toISOString())}`,`DTSTART:${utc(t[k])}`,`SUMMARY:${icsText(conferenceName(c)+' '+c.detail.year+' · '+t.name+' · '+(k==='fullDeadline'?'全文截止':'摘要/注册截止')+(t.submissionStage==='invitation-only'?' · 仅限获邀':''))}`,`DESCRIPTION:${icsText((t.submissionStage==='invitation-only'?'仅限获邀稿件；此阶段不接受普通新稿。\n':'')+'官方时区：'+(k==='fullDeadline'?t.fullTimezone:t.abstractTimezone)+'\n来源：'+((t.sources||[])[0]?.url||(t.sources||[])[0]||c.detail.officialUrl))}`,'END:VEVENT'].join('\r\n'));
    const blob=new Blob([['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Conf Atlas//Conference Deadlines//ZH','CALSCALE:GREGORIAN',...events,'END:VCALENDAR',''].join('\r\n')],{type:'text/calendar;charset=utf-8'});
    const url=URL.createObjectURL(blob), a=document.createElement('a');a.href=url;a.download=`${c.id}-${c.detail.year}-deadlines.ics`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出已核验节点，请导入你的日历');
  }
  function showAbout() {
    const counts=data.coverage;
    $('#about-content').innerHTML=`<p>会投是一个面向科研工作者的会议导航。当前收录 <strong>${conferences.length}</strong> 场会议，包括 CCF 第七版 <strong>${conferences.filter(c=>c.rank!=='N').length}</strong> 条正式会议目录及 <strong>${conferences.filter(c=>c.rank==='N').length}</strong> 个本站补充会议。</p><h3>目前补到了哪里</h3><p>${counts.details} 场会议已补充部分届次详情（不代表所有字段齐全），${counts.tracks} 个 Track，${counts.acceptanceRecords} 组含整数分子分母的年度录用统计，${counts.curatedPapers||counts.bestPapers} 篇精选论文；${counts.attendanceVerified||0} 个年度参会政策有明确依据。其余明确保留待补全状态。数据核验日期：${esc(data.asOf)}；此版本为静态核验快照，不会自动抓取或更新官网。</p><h3>如何理解 A / B / C / N</h3><p>A/B/C 使用 ${esc(data.version)}，正式发布于 ${esc(data.publishedAt)}，勘误日期 ${esc(data.errataAt)}。N 为本站自定义收录分类，不是 CCF 官方等级；不等于 C 类之下。</p><p>${esc(data.rankScope)}</p><h3>日期、模板与统计口径</h3><ul><li>日期保留官方时区，倒计时按真实时间戳计算。AoE = UTC−12；日历时区可在设置中调整。</li><li>优先显示最近可核实届次；未知值不猜补。模板如沿用旧年，标明年份与原因。</li><li>近三年按 ${data.acceptanceWindow.join('、')} 三个完整日历年；前一年精选论文指 ${data.bestPaperYear} 年，与页面中的会议届次分开。</li><li>录用率为已核验的录用数 ÷ 投稿数，不从百分比反推整数。长短论文、有效送审和 Findings 等口径在统计详情中单独说明。</li></ul><h3>CORE / ICORE 与 TH-CPL</h3><p>会议详情同时列出各自独立的分级、版本和来源。CORE 使用 ICORE2026；TH-CPL 使用清华域名公开的 2019-08-13 版，不表示已核实为最新版本。未匹配项保留‘未确认’，不能据此断言未评级。</p><h3>目录来源</h3>${data.sources.map(s=>`<p>${link(s.url,s.label,'')}</p>`).join('')}<p>${esc(data.provenanceNote)}</p><h3>日期来源与账号数据</h3><p>列表使用主 Research / Papers Track 截止日期；其他 Track 单独提示。投稿系统与 CFP 冲突时保留各自来源，不把开放状态或宽限期当作正式 DDL。线下要求逐年核验，不从会场地址推断。</p><p>访客可浏览会议和使用解压室；收藏、提醒及微信绑定需先登录。主题与访客解压计数保存在浏览器；真实账号的密码哈希、会话和个人数据保存在本机 SQLite 数据库。木鱼新增敲击还会匿名汇总到当前服务，展示大家共同的累计，不包含账号身份。当前服务只监听本机，不是云端账号服务；不同本地部署不会自动向维护者上传统计。</p>`;
    $('#about-dialog').showModal();
  }
  document.addEventListener('conf-login-required',()=>{if(activeId)closeDetail();showView('account');});
  document.addEventListener('click',e=>{
    const b=e.target.closest('button');
    if(b?.dataset.save){toggleFavorite(b.dataset.save);return;}
    if(b?.dataset.open){openDetail(b.dataset.open);return;}
    if(b?.dataset.view){showView(b.dataset.view);return;}
    if(b?.dataset.rank){state.rank=b.dataset.rank;state.page=1;render();return;}
    if(b?.dataset.area){state.area=state.area===b.dataset.area?'all':b.dataset.area;state.page=1;render();return;}
    if(b?.dataset.page){state.page=Number(b.dataset.page);render();$('.section-heading').scrollIntoView({block:'start',behavior:'smooth'});return;}
    if(b?.dataset.tab){activeTab=b.dataset.tab;renderDrawer();$(`[data-tab="${activeTab}"]`).focus();return;}
    if(b?.dataset.export){exportCalendar(b.dataset.export,Number(b.dataset.track));return;}
    if(b?.dataset.action==='reset'){resetFilters();return;}
    if(b?.dataset.action==='explore'){resetFilters();showView('explore');return;}
    if(b?.dataset.month){const action=b.dataset.month;if(action==='today')calendarMonth=new Date(today.getFullYear(),today.getMonth(),1);else if(action==='next'){const next=filtered().flatMap(deadlineEntries).sort((a,b)=>a.date-b.date).find(e=>e.date>Date.now());if(next){const key=zoneDate(next.date);calendarMonth=new Date(Number(key.slice(0,4)),Number(key.slice(5,7))-1,1);}}else calendarMonth.setMonth(calendarMonth.getMonth()+Number(action));render();return;}
    const row=e.target.closest('tr[data-conf]');if(row)openDetail(row.dataset.conf);
  });
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'&&activeId){closeDetail();return;}
    if(e.key==='Tab'&&activeId){const focusables=$$('a[href],button:not(:disabled),input,select', $('#detail-drawer'));const first=focusables[0],last=focusables.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
  });
  $('#search').addEventListener('input',e=>{state.q=e.target.value;state.page=1;render();});
  for(const [id,key] of [['area-select','area'],['status-select','status'],['coverage-select','coverage'],['sort-select','sort']])$('#'+id).addEventListener('change',e=>{state[key]=e.target.value;state.page=1;render();});
  $('#calendar-shortcut').onclick=()=>showView('calendar');
  $('#drawer-backdrop').onclick=closeDetail;
  $('#about-button').onclick=()=>data&&showAbout();
  $('#mobile-about-button').onclick=()=>data&&showAbout();
  $('#close-about').onclick=()=>$('#about-dialog').close();
  $('.brand').onclick=e=>{e.preventDefault();resetFilters();showView('explore');};
  setInterval(()=>{if(!data)return;for(const el of $$('[data-countdown]'))el.outerHTML=countdown(el.dataset.countdown);const fingerprint=conferences.map(c=>statusOf(c)+':'+nearest(c)?.iso).join(',');if(deadlineFingerprint && fingerprint!==deadlineFingerprint)render();deadlineFingerprint=fingerprint;renderMetrics();},60000);
  async function load() {
    try {
      const embedded = $('#conference-data');
      if (embedded) data=JSON.parse(embedded.textContent);
      else { const response=await fetch('./data/conferences.json');if(!response.ok)throw new Error('HTTP '+response.status);data=await response.json(); }
      conferences=data.conferences;
      if(!Array.isArray(conferences)||!conferences.length)throw new Error('会议目录为空');
      if(!['all','A','B','C','N'].includes(state.rank))state.rank='all';
      if(!['explore','favorites','calendar','relax','account','settings','wechat','services'].includes(state.view))state.view='explore';
      if(!['all','soon','upcoming','any-upcoming','closed','date-only','rolling','unknown'].includes(state.status))state.status='all';
      if(!['all','details','catalog'].includes(state.coverage))state.coverage='all';
      if(!['deadline','name','rank'].includes(state.sort))state.sort='deadline';
      if(state.area!=='all'&&!data.areas.some(a=>a.id===state.area))state.area='all';
      $('#catalog-version').textContent=data.version;
      $('#data-stamp').textContent=`第七版目录 · ${data.asOf} 核验`;
      $('#area-select').innerHTML='<option value="all">全部学科</option>'+data.areas.map(a=>`<option value="${esc(a.id)}">${esc(areaLabels[a.id]||a.name)}</option>`).join('');
      $('#area-nav').innerHTML=data.areas.map(a=>`<button data-area="${esc(a.id)}" title="${esc(a.name)}">${esc(areaLabels[a.id]||a.name)}<span>${conferences.filter(c=>c.areaId===a.id).length}</span></button>`).join('');
      window.ConfReminders.init({conferences,portal:window.ConfPortal,notify:toast,refresh:()=>{render();if(activeId)renderDrawer();}});
      deadlineFingerprint=conferences.map(c=>statusOf(c)+':'+nearest(c)?.iso).join(',');render();
    } catch(error) {
      $('#conference-body').innerHTML=`<tr><td colspan="7"><div class="load-error">会议数据加载失败。请使用本地 HTTP 服务打开本应用。<br><small>${esc(error.message)}</small><br><button class="outline-button" id="retry-load">重新加载</button></div></td></tr>`;$('#retry-load').onclick=load;
    }
  }
  window.ConfPortal.init((profile)=>{window.ConfReminders.stateChanged();saved=new Set(profile.favorites||[]);CAL_ZONE=profile.settings.timezone;render();if(activeId)renderDrawer();},toast);
  load();
})();
