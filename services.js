'use strict';
(() => {
  const EMAIL = 'khu0829y@gmail.com';
  const services = [
    {id:'api',number:'01',icon:'⌘',label:'API ACCESS',title:'低价稳定 API 中转站',
      description:'咨询模型接入、调用方式与用量方案。将你需要的模型和使用场景发来，确认适合的接入安排。',
      tags:['模型接入','用量方案'],subject:'API 中转服务咨询'},
    {id:'paper',number:'02',icon:'✎',label:'RESEARCH & WRITING',title:'论文辅导与润色',
      description:'研究思路讨论、论文结构梳理与中英文表达润色。按你的研究阶段和具体需求沟通。',
      tags:['研究讨论','结构与表达'],subject:'论文辅导与润色咨询'},
    {id:'account',number:'03',icon:'✦',label:'ACCOUNTS & CREDITS',title:'账号、额度与会员充值',
      description:'GPT 账号、Muse 额度、Grok 会员低价直充与代充。具体项目、价格和办理方式请邮件确认。',
      tags:['GPT 账号','Muse 额度','Grok 会员'],subject:'账号、额度与会员充值咨询'},
    {id:'support',number:'04',icon:'↗',label:'SUPPORT & COLLABORATION',title:'售后、合作与反馈',
      description:'售后支持、AI 相关合作与咨询，也欢迎反馈会投中的问题、信息更正和改进建议。',
      tags:['售后支持','AI 合作','反馈与建议'],subject:'售后、AI 合作与反馈'}
  ];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const mailto = subject => `mailto:${EMAIL}?subject=${encodeURIComponent('会投 · '+subject)}`;
  let active = false, notify = () => {}, epoch = 0;

  function html() {
    return `<div id="services-root" class="svc-page">
      <section class="panel svc-contact" aria-labelledby="svc-contact-title">
        <div class="svc-contact-copy"><div class="svc-kicker">LET'S TALK</div><h2 id="svc-contact-title">有需求，也欢迎有建议。</h2><p>API 使用、科研写作、账号服务或 AI 合作，<br>都可以通过邮件联系。会投的问题和建议也欢迎告诉我。</p></div>
        <div class="svc-email-card"><span class="svc-email-label">联系邮箱</span><a class="svc-email" href="${mailto('服务与合作咨询')}">${EMAIL}</a><div class="svc-email-actions"><a class="primary-button" href="${mailto('服务与合作咨询')}">写邮件联系 <span aria-hidden="true">↗</span></a><button class="outline-button" type="button" data-service-copy>复制邮箱</button></div><p id="svc-copy-status" class="svc-copy-status" role="status" aria-live="polite">点击「写邮件联系」会打开你的邮件应用。</p></div>
      </section>
      <div class="svc-section-heading"><h3>服务与支持</h3><span>选择你想了解的方向</span></div>
      <div class="svc-grid">${services.map(item=>`<article class="panel svc-card" data-service="${item.id}" aria-labelledby="svc-${item.id}-title"><div class="svc-card-top"><span class="svc-icon" aria-hidden="true">${item.icon}</span><span class="svc-number" aria-hidden="true">${item.number}</span></div><div class="svc-kicker">${item.label}</div><h3 id="svc-${item.id}-title">${item.title}</h3><p>${item.description}</p><ul class="svc-tags" aria-label="${esc(item.title)}服务方向">${item.tags.map(tag=>`<li>${tag}</li>`).join('')}</ul><a class="svc-card-link" href="${mailto(item.subject)}">${item.id==='support'?'联系与反馈':'邮件咨询'} <span aria-hidden="true">↗</span></a></article>`).join('')}</div>
      <p class="svc-footnote">来信时可以写明需求、当前遇到的问题和期望时间，便于沟通具体安排。</p>
    </div>`;
  }
  function mount(options={}) {active=true;epoch++;notify=options.notify||(()=>{});}
  function leave() {active=false;epoch++;}
  document.addEventListener('click', async event => {
    const button=event.target.closest('[data-service-copy]');
    if(!active||!button||button.disabled)return;
    const version=epoch;button.disabled=true;
    let message;
    try {
      if(!navigator.clipboard?.writeText)throw new Error('clipboard_unavailable');
      await navigator.clipboard.writeText(EMAIL);
      message='邮箱已复制，可以粘贴到邮件应用。';
    } catch {message='暂时无法自动复制，请选中上方邮箱手动复制。';}
    if(active&&version===epoch){
      const target=document.querySelector('#svc-copy-status');
      if(target)target.textContent=message;
      notify(message);
    }
    if(button.isConnected)button.disabled=false;
  });
  window.ConfServices={html,mount,leave};
})();
