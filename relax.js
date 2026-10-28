'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const content = window.ConfRelaxContent;
  const assets = {...{woodfish:'./assets/woodfish.jpg',cat:'./assets/a-men-cat.jpg',knock:'./assets/wood-knock.wav'},...window.ConfRelaxAssets};
  const merits = ['功德 +1','焦虑 −1','灵感 +1','显存 +0','Reviewer 2 温柔 +1','今晚好眠 +1','Bug −1','Accept 缘分 +1'];
  const gateModes = {
    A:{label:'冲顶会 A 门',card:'A 門',badge:'A 门常开',title:'猫猫合十，<br>顶会见面。',description:'愿每个认真写下的句子，都有人读懂。',action:'合十，加入 A 门'},
    B:{label:'保毕业 B 门',card:'B 門',badge:'保毕业 B 门',title:'拜拜焦虑，<br>顺利毕业。',description:'论文有着落，答辩有底气。<br>让猫猫替你许个愿。',action:'合十，接毕业好运'},
    LIFE:{label:'好好生活',card:'好眠',badge:'今天也要好好生活',title:'先接住自己，<br>再接好消息。',description:'论文可以有分数，你不需要。',action:'合十，接住好生活'}
  };
  // Keep the original themes and only the three requested additions.
  const gateThemes = Object.fromEntries([
    ['acl','ACL','A'],['cvpr','CVPR','A'],['icml','ICML','A'],['neurips','NeurIPS','A'],['www','WWW','A'],
    ['aaai','AAAI','A'],['iclr','ICLR','A'],['icassp','ICASSP','B'],['life','生活','LIFE']
  ].map(([id,name,rank])=>[id,{id,name,rank,...content.gateProfiles[id]}]));
  let gateMode = 'A';
  const gateChoices = {A:'acl',B:'icassp',LIFE:'life'};
  const gateTheme = () => gateThemes[selectedWish];
  function gateOptions(){
    return Object.values(gateThemes).filter(theme=>theme.rank===gateMode).map(theme=>
      `<option value="${theme.id}" ${theme.id===selectedWish?'selected':''}>${esc(theme.name)} · ${esc(theme.caption)}</option>`
    ).join('');
  }
  const bags = new Map(), previous = new Map();
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  let hooks = null, room = 'wood', category = 'all', selectedWish = 'acl', tone = 'warm', volume = .5;
  let lastLetter = null, currentBlessing = '', lastMerit = '点击木鱼，把脑内噪声调小一点。', combo = 0, lastTap = 0;
  let audioContext = null, soundBuffer = null, soundLoading = null, audioErrorReported = false, audioEpoch = 0;
  const voices = new Set(), timers = new Set();
  const reduced = () => motion.matches || hooks?.getSettings().reducedMotion;
  const count = name => hooks?.getCounts()[name] || 0;
  const later = (fn, ms) => { const id=setTimeout(()=>{timers.delete(id);fn();},ms);timers.add(id);return id; };
  function draw(key, list) {
    let bag=bags.get(key);
    if(!bag?.length){
      bag=[...list];
      for(let i=bag.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[bag[i],bag[j]]=[bag[j],bag[i]];}
      if(bag.length>1&&bag[bag.length-1]===previous.get(key))[bag[0],bag[bag.length-1]]=[bag[bag.length-1],bag[0]];
      bags.set(key,bag);
    }
    const result=bag.pop();previous.set(key,result);return result;
  }
  function stopAudio(){audioEpoch++;for(const voice of voices){try{voice.stop();}catch{}}voices.clear();}
  async function primeAudio() {
    if(!audioContext)audioContext=new(window.AudioContext||window.webkitAudioContext)();
    await audioContext.resume();
    if(!soundBuffer){
      const loadBytes = () => assets.knock.startsWith('data:')
        ? Promise.resolve(Uint8Array.from(atob(assets.knock.split(',')[1]), char=>char.charCodeAt(0)).buffer)
        : fetch(assets.knock).then(r=>{if(!r.ok)throw new Error('音频资源不可用');return r.arrayBuffer();});
      soundLoading ||= loadBytes().then(value=>audioContext.decodeAudioData(value)).then(buffer=>soundBuffer=buffer).catch(error=>{soundLoading=null;throw error;});
      await soundLoading;
    }
  }
  async function knockSound(){
    if(!hooks?.getSettings().sound||document.hidden)return;
    const epoch=audioEpoch;
    try{
      await primeAudio();
      if(epoch!==audioEpoch||!hooks?.getSettings().sound||document.hidden)return;
      if(voices.size>=8){const old=voices.values().next().value;old.stop();voices.delete(old);}
      const source=audioContext.createBufferSource(),gain=audioContext.createGain();
      source.buffer=soundBuffer;source.playbackRate.value=({warm:1,crisp:1.22,deep:.8})[tone];
      gain.gain.value=volume*.7;source.connect(gain);gain.connect(audioContext.destination);voices.add(source);
      source.onended=()=>{voices.delete(source);source.disconnect();gain.disconnect();};source.start();
    }catch{if(!audioErrorReported){audioErrorReported=true;hooks?.notify('音效暂不可用，请检查浏览器声音权限后重试。');}}
  }
  function html({counts,signedIn}) {
    return `<div class="rx-shell"><div class="rx-intro"><div><span class="rx-status-dot"></span>研究者短暂离线中 <span class="rx-intro-note">好好研究，也好好喘口气。</span></div><span class="rx-entertainment">虚构互动 · 不影响真实审稿</span></div><div class="rx-nav" role="group" aria-label="选择解压玩法">${[['wood','◉','电子木鱼','敲掉一点焦虑'],['accept','✉','接 Accept','收一封好消息'],['gate','✦','A / B 门','顶会与毕业，都有回响']].map(([id,icon,title,sub])=>`<button data-relax="room" data-room="${id}" aria-pressed="${room===id}" class="rx-nav-item ${room===id?'selected':''}"><span class="rx-nav-icon">${icon}</span><span><strong>${title}</strong><small>${sub}</small></span><span class="rx-nav-arrow">↗</span></button>`).join('')}</div><div id="rx-room">${roomHTML(counts)}</div><p class="rx-footnote">${signedIn?'个人计数保存在当前账号。':'个人计数保存在当前浏览器。'} 今天的你，值得一小段没有 KPI 的时间。</p></div>`;
  }
  function reframeHTML(){return `<section class="rx-reframe"><span class="rx-reframe-icon" aria-hidden="true">✺</span><div><h3>给脑内 Reviewer 2 换个语气</h3><p id="reviewer-text">${esc(content.translations[0].original)} → ${esc(content.translations[0].gentle)}</p></div><button class="outline-button" data-relax="reviewer">换个角度 ↻</button></section>`;}
  function roomHTML(counts){return room==='wood'?woodHTML(counts):room==='accept'?acceptHTML(counts)+reframeHTML():gateHTML(counts);}
  function woodHTML(counts){return `<section class="rx-stage rx-wood-room"><div class="rx-visual rx-wood-visual"><button id="woodfish-button" class="rx-wood-image" data-relax="woodfish" aria-label="敲木鱼，学术功德加一"><img src="${assets.woodfish}" alt="暖木色木鱼，置于木桌上" draggable="false"><span class="rx-mallet" aria-hidden="true"><i></i></span><span class="rx-tap-hint">点击敲一敲 · Enter / 空格</span></button><div id="rx-wood-effects" class="rx-effects" aria-hidden="true"></div><span class="rx-scene-badge">01 / 木鱼时间</span></div><div class="rx-stage-copy"><div class="rx-kicker">ONE TAP. ONE SMALL BREATH.</div><h2>功德慢慢攒，<br>焦虑轻轻放。</h2><p class="rx-description">不必每一下都有意义。<br>听一声咚，让脑子歇一歇。</p><div class="rx-counter"><strong id="woodfish-count">${counts.woodfish}</strong><span>我的学术功德</span><span id="rx-combo" class="rx-combo">${combo>1?'连敲 × '+combo:'随自己的节奏'}</span></div><section class="rx-community" aria-label="全站木鱼累计"><div><span>大家一起敲了</span><strong data-community-total>—</strong><span>次木鱼</span></div><p data-community-status>正在连接统计服务…</p><details><summary>累计范围与保存说明</summary><p>访客与登录用户共同累计。同一服务的网页与未来 App 可共享总数；不同本地部署各自统计。个人计数与此累计分开保存。</p><p>从功能启用后新增敲击开始，不追溯导入旧记录；已汇总的匿名次数不会因注销账号减少。<span data-community-started></span></p></details></section><p id="rx-merit" class="rx-feedback" aria-live="polite">${esc(lastMerit)}</p><div class="rx-sound-box"><div class="rx-sound-top"><strong>一声木响</strong><button class="rx-sound-toggle" data-relax="sound" aria-pressed="${hooks?.getSettings().sound||false}">${hooks?.getSettings().sound?'♫ 声音已开':'♪ 开启声音'}</button></div><div class="rx-tones" role="group" aria-label="木鱼音色">${[['warm','温润'],['crisp','清脆'],['deep','沉稳']].map(([id,label])=>`<button data-relax="tone" data-tone="${id}" aria-pressed="${tone===id}" class="${tone===id?'selected':''}">${label}</button>`).join('')}</div><label class="rx-volume"><span>音量</span><input id="rx-volume" type="range" min="0" max="100" step="5" value="${volume*100}" aria-label="木鱼音量"><output id="rx-volume-value">${Math.round(volume*100)}%</output></label><small>木质合成音色 · 点击后播放</small></div></div></section>`;}
  function acceptHTML(counts){return `<section class="rx-stage rx-accept-room"><div class="rx-visual rx-letter-visual"><span class="rx-scene-badge">02 / 平行宇宙邮局</span><div class="rx-envelope ${lastLetter?'opened':''}" id="rx-envelope"><span class="rx-envelope-back" aria-hidden="true"></span><article id="rx-letter" class="rx-letter" aria-live="polite" ${lastLetter?'':'hidden'}><span class="rx-letter-overline">CONF. ATLAS · GOOD NEWS DEPARTMENT</span><span class="rx-letter-icon" aria-hidden="true">✦</span><h3 id="accept-result">${esc(lastLetter?.title||'Dear Author,')}</h3><p id="accept-text">${esc(lastLetter?.body||'有一封好消息，在这里等你。今天请允许自己，先开心一下。')}</p><span id="rx-stamp" class="rx-stamp">${esc(lastLetter?.stamp||'WAITING FOR YOU')}</span><small>平行宇宙来信 · 虚构内容</small></article><span class="rx-envelope-front" aria-hidden="true"><span>TO: YOU, WITH A LITTLE HOPE.</span></span><span class="rx-envelope-flap" aria-hidden="true"></span><span class="rx-envelope-seal" aria-hidden="true">✦</span></div><div id="rx-letter-effects" class="rx-effects" aria-hidden="true"></div></div><div class="rx-stage-copy"><div class="rx-kicker">MANIFESTING GOOD NEWS</div><h2>这一封，<br>没有 however。</h2><p class="rx-description">48 封不同的来信，6 种快乐。<br>让好消息先在这里发生。</p><div class="rx-categories" role="group" aria-label="选择来信类型">${content.categories.map(c=>`<button data-relax="category" data-category="${c.id}" aria-pressed="${category===c.id}" class="${category===c.id?'selected':''}">${esc(c.icon)} ${esc(c.label)}</button>`).join('')}</div><button class="rx-action rx-accept-action" data-relax="accept">${lastLetter?'再接一封好消息':'拆开我的好消息'} <span>↗</span></button><div class="rx-mini-count">已接住 <strong id="accept-count">${counts.accepts}</strong> 封快乐 <span>每类抽完一轮再重复</span></div></div></section>`;}
  function gateHTML(counts){
    const theme=gateTheme(),mode=gateModes[gateMode];
    return `<section class="rx-stage rx-gate-room" data-wish="${esc(selectedWish)}" data-gate="${gateMode}" data-effect="${theme.effect}">
      <div class="rx-visual rx-cat-visual"><span class="rx-scene-badge" id="rx-gate-badge">03 / ${mode.badge}</span><div class="rx-cat-halo" aria-hidden="true"></div>
        <button class="rx-cat-card" id="rx-cat-card" data-relax="amen" aria-label="与橘猫合十，为${esc(theme.name)}祈愿"><span class="rx-cat-header" aria-hidden="true">${mode.card}</span><span class="rx-cat-art"><img src="${assets.cat}" alt="闭眼合十的橘猫" draggable="false"></span><span class="rx-cat-caption"><strong id="rx-card-conference">${esc(theme.name)}</strong><span id="rx-card-caption">${esc(theme.caption)}</span></span></button>
        <div id="rx-cat-effects" class="rx-effects" aria-hidden="true"></div><span class="rx-cat-floor-note">点击猫猫，一起合十。</span>
      </div><div class="rx-stage-copy"><div class="rx-kicker">IN CAT WE TRUST</div>
        <div class="rx-gate-modes" role="group" aria-label="选择祈愿门">${Object.entries(gateModes).map(([id,m])=>`<button data-relax="gate-mode" data-gate="${id}" aria-pressed="${gateMode===id}" class="${gateMode===id?'selected':''}">${m.label}</button>`).join('')}</div>
        <h2>${mode.title}</h2><p class="rx-description">${mode.description}</p>
        <label class="rx-wish-select" for="rx-wish"><span>今天，替什么许个愿？</span><select id="rx-wish">${gateOptions()}</select></label>
        <div id="amen-text" class="rx-blessing" aria-live="polite">${esc(currentBlessing||theme.wishes[0])}</div>
        <button class="rx-action rx-amen-action" data-relax="amen">${mode.action} <span>✦</span></button><div class="rx-mini-count">已与猫猫合十 <strong id="amen-count">${counts.amen}</strong> 次</div>
      </div></section>`;
  }
  function mount(callbacks){hooks=callbacks;updateSound();window.ConfCommunity?.render();window.ConfCommunity?.refresh();}
  function updateSound(){const button=$('[data-relax="sound"]');if(button){const on=hooks.getSettings().sound;button.textContent=on?'♫ 声音已开':'♪ 开启声音';button.setAttribute('aria-pressed',String(on));if(!on)stopAudio();}}
  function pulse(element, name){if(!element||reduced())return;element.classList.remove(name);void element.offsetWidth;element.classList.add(name);}
  function particles(target,kind,amount=kind==='cat'?10:16){
    if(!target||reduced())return;
    const theme=gateTheme(),glyphs=kind==='cat'?theme.words:['✦','✧','ACCEPT','+1','✉'];
    for(let i=0;i<amount;i++){
      const node=document.createElement('span');node.className='rx-burst';node.textContent=glyphs[i%glyphs.length];
      let dx=(Math.random()-.5)*270,dy=-80-Math.random()*190;
      if(kind==='cat'){
        node.dataset.wish=selectedWish;node.style.setProperty('--flight',theme.effect);node.style.left=`${32+i%3*18}%`;node.style.top=`${49+Math.floor(i/3)%2*9}%`;
        if(theme.effect==='rx-focus-flight'){dx=(i%2?1:-1)*(65+Math.random()*90);dy=-40-Math.random()*170;}
        if(theme.effect==='rx-step-flight'){dx=(i%5-2)*46;dy=-90-Math.floor(i/5)*45;}
        if(theme.effect==='rx-orbit-flight'){const angle=i/amount*Math.PI*2;dx=Math.cos(angle)*125;dy=-105+Math.sin(angle)*110;}
        if(theme.effect==='rx-link-flight'){dx=(i%2?1:-1)*(70+Math.random()*100);dy=-30-Math.random()*115;}
        if(theme.effect==='rx-signal-flight'){dx=(i%5-2)*55;dy=-75-Math.floor(i/5)*65;}
        if(theme.effect==='rx-rest-flight'){dx=(Math.random()-.5)*150;dy=-65-Math.random()*130;}
      }
      node.style.setProperty('--dx',`${dx}px`);node.style.setProperty('--dy',`${dy}px`);node.style.setProperty('--mid-x',`${dx*.45}px`);node.style.setProperty('--mid-y',`${dy*.55}px`);node.style.setProperty('--turn',`${(Math.random()-.5)*50}deg`);const delay=kind==='cat'?i*65:Math.random()*130;node.style.setProperty('--delay',`${delay}ms`);node.style.setProperty('--particle',String(i%3));
      target.append(node);later(()=>node.remove(),1500+delay);
    }
  }
  function hitWood(){
    hooks.increment('woodfish');window.ConfCommunity?.tap();$('#woodfish-count').textContent=count('woodfish');
    const now=performance.now();combo=now-lastTap<650?combo+1:1;lastTap=now;lastMerit=draw('merit',merits);
    $('#rx-merit').textContent=lastMerit;$('#rx-combo').textContent=combo>1?'连敲 × '+combo:'随自己的节奏';
    knockSound();pulse($('#woodfish-button'),'rx-struck');
    if(!reduced()){
      const target=$('#rx-wood-effects'),text=document.createElement('span'),ring=document.createElement('span');
      text.className='rx-merit-float';text.textContent=lastMerit;text.style.left=`${38+Math.random()*23}%`;ring.className='rx-knock-ring';target.append(ring,text);later(()=>{ring.remove();text.remove();},1000);
    }
  }
  function acceptLetter(){
    lastLetter=draw('letters:'+category,content.letters.filter(letter=>category==='all'||letter.category===category));
    hooks.increment('accepts');$('#accept-count').textContent=count('accepts');
    $('#accept-result').textContent=lastLetter.title;$('#accept-text').textContent=lastLetter.body;$('#rx-stamp').textContent=lastLetter.stamp;
    const envelope=$('#rx-envelope');$('#rx-letter').hidden=false;envelope.classList.add('opened');pulse(envelope,'rx-deliver');
    $('[data-relax="accept"]').innerHTML='再接一封好消息 <span>↗</span>';particles($('#rx-letter-effects'),'letter');
    const paper=$('#rx-letter'),bounds=paper.getBoundingClientRect();if(bounds.top<16||bounds.bottom>window.innerHeight-80)paper.scrollIntoView({behavior:reduced()?'instant':'smooth',block:'center'});
  }
  function bless(){
    hooks.increment('amen');$('#amen-count').textContent=count('amen');currentBlessing=draw('wish:'+selectedWish,gateTheme().wishes);$('#amen-text').textContent=currentBlessing;
    $('#rx-cat-effects').replaceChildren();pulse($('#rx-cat-card'),'rx-pray');pulse($('.rx-cat-halo'),'rx-glow');particles($('#rx-cat-effects'),'cat');
  }
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-relax]');if(!button||!hooks)return;
    const action=button.dataset.relax;
    if(action==='room'){
      room=button.dataset.room;stopAudio();
      document.querySelectorAll('.rx-nav-item').forEach(item=>{const selected=item.dataset.room===room;item.classList.toggle('selected',selected);item.setAttribute('aria-pressed',String(selected));});
      $('#rx-room').innerHTML=roomHTML(hooks.getCounts());window.ConfCommunity?.render();return;
    }
    if(action==='gate-mode'){
      const next=button.dataset.gate;if(!gateModes[next])return;
      gateMode=next;selectedWish=gateChoices[next];currentBlessing='';
      $('#rx-room').innerHTML=gateHTML(hooks.getCounts());
      $(`[data-relax="gate-mode"][data-gate="${next}"]`).focus();
      pulse($('#rx-cat-card'),'rx-switch');particles($('#rx-cat-effects'),'cat',6);return;
    }
    if(action==='woodfish')hitWood();
    if(action==='accept')acceptLetter();
    if(action==='amen')bless();
    if(action==='tone'){tone=button.dataset.tone;document.querySelectorAll('[data-relax="tone"]').forEach(item=>{const active=item.dataset.tone===tone;item.classList.toggle('selected',active);item.setAttribute('aria-pressed',String(active));});knockSound();}
    if(action==='category'){category=button.dataset.category;document.querySelectorAll('[data-relax="category"]').forEach(item=>{const active=item.dataset.category===category;item.classList.toggle('selected',active);item.setAttribute('aria-pressed',String(active));});}
    if(action==='reviewer'){const item=draw('reviewer',content.translations);$('#reviewer-text').textContent=`${item.original} → ${item.gentle}`;}
    if(action==='sound'){
      const enable=!hooks.getSettings().sound;audioErrorReported=false;
      if(enable)primeAudio().catch(()=>{});else stopAudio();
      button.disabled=true;await hooks.setSound(enable);updateSound();if(button.isConnected)button.disabled=false;
    }
  });
  document.addEventListener('input',event=>{
    if(event.target.id==='rx-volume'){volume=Number(event.target.value)/100;$('#rx-volume-value').textContent=`${Math.round(volume*100)}%`;}});
  document.addEventListener('change',event=>{
    if(event.target.id!=='rx-wish'||!Object.hasOwn(gateThemes,event.target.value))return;
    selectedWish=event.target.value;gateChoices[gateMode]=selectedWish;currentBlessing=gateTheme().wishes[0];
    const theme=gateTheme(),card=$('#rx-cat-card'),halo=$('.rx-cat-halo'),effects=$('#rx-cat-effects');
    // Clear the old theme's effects before showing the new vocabulary.
    effects.replaceChildren();card.classList.remove('rx-pray','rx-switch');halo.classList.remove('rx-glow');
    $('.rx-gate-room').dataset.wish=selectedWish;$('.rx-gate-room').dataset.effect=theme.effect;
    $('#rx-card-conference').textContent=theme.name;$('#rx-card-caption').textContent=theme.caption;
    card.setAttribute('aria-label',`与橘猫合十，为${theme.name}祈愿`);$('#amen-text').textContent=currentBlessing;
    pulse(card,'rx-switch');particles(effects,'cat',6);
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopAudio();});
  function leave(){hooks=null;stopAudio();for(const timer of timers)clearTimeout(timer);timers.clear();}
  window.ConfRelax={html,mount,leave};
})();
