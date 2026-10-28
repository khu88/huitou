import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../reminders.js', import.meta.url), 'utf8');
const epoch = Date.parse('2026-10-28T00:00:00Z');
const conference = (deadline='2026-11-10T23:59:00-12:00', name='Main Conference') => ({
  id:'cvpr', acronym:'CVPR', name:'Computer Vision Conference',
  detail:{tracks:[{name, abstractDeadline:deadline, fullDeadline:'2026-11-17T11:59:00Z'}]},
});
const reminder = (patch={}) => ({
  id:'cvpr-main-abstract-1440',conferenceId:'cvpr',trackName:'Main Conference',
  kind:'abstract',deadline:'2026-11-10T23:59:00-12:00',leadMinutes:1440,enabled:true,...patch,
});

// Execute the actual buildless module. The fake clock models scheduler gaps;
// mocked delivery endpoints do not claim browser/OS notification validation.
function harness({start=epoch,conferences=[conference()],scope='user-a',items=[],storage=new Map()}={}) {
  let now=start,activeScope=scope,activeItems=items,interval,loginRequests=0,nextId=0;
  const listeners=new Map(),messages=[],notifications=[];
  class Clock extends Date {static now(){return now;}}
  class Notification {
    static permission='granted';
    static async requestPermission(){return this.permission;}
    constructor(title,options){notifications.push({title,...options});}
  }
  class FormData {
    constructor(form){this.fields=form.fields;}
    get(name){return this.fields[name];}
    getAll(name){return this.fields[name]||[];}
  }
  const context=vm.createContext({
    window:{},Date:Clock,TextEncoder,Intl,Notification,FormData,
    crypto:{randomUUID:()=>`test-reminder-${++nextId}`},
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},
    setInterval:fn=>{interval=fn;return 1;},clearInterval:()=>{},
    document:{addEventListener:(name,fn)=>listeners.set(name,fn)},
  });
  vm.runInContext(source,context,{filename:'reminders.js'});
  const portal={getScope:()=>activeScope,getReminders:()=>structuredClone(activeItems),setReminders:async next=>{activeItems=structuredClone(next);},getSettings:()=>({timezone:'UTC'}),requireLogin:()=>{loginRequests++;return activeScope!=='guest';}};
  context.window.ConfReminders.init({conferences,portal,notify:msg=>messages.push(msg),refresh:()=>{}});
  return {
    model:context.window.ReminderModel,ui:context.window.ConfReminders,messages,notifications,storage,
    setTime:time=>{now=time;},tick:()=>interval(),
    visibility:()=>listeners.get('visibilitychange')(),
    switchAccount:(next,nextItems)=>{activeScope=next;activeItems=nextItems;context.window.ConfReminders.stateChanged();},
    setItems:next=>{activeItems=next;context.window.ConfReminders.stateChanged();},
    get loginRequests(){return loginRequests;},
    get items(){return structuredClone(activeItems);},
    submitReminder:async({node='0:full',leads=['0']}={})=>{
      const button={disabled:false,isConnected:true},message={textContent:''};
      const form={matches:()=>true,dataset:{reminderForm:'cvpr'},fields:{node,lead:leads},querySelector:selector=>selector==='button[type=submit]'?button:message};
      await listeners.get('submit')({target:form,preventDefault(){}});
      assert.equal(message.textContent,'');
      assert.equal(button.disabled,false);
    },
    clickReminderAction:()=>listeners.get('click')({target:{closest:()=>({})},stopPropagation(){}}),
  };
}

test('deadline time uses the explicit offset and the selected lead',()=>{
  const {model}=harness();
  assert.equal(model.time(reminder()),Date.parse('2026-11-10T11:59:00Z'));
  assert.equal(model.problem(reminder({deadline:'2026-11-11T11:59:00Z'}),[conference()]),null);
  assert.equal(model.problem(reminder({kind:'full',deadline:'2026-11-17T11:59:00Z'}),[conference()]),null);
});

test('rejects naive dates, impossible calendar days and normalized 24-hour timestamps',()=>{
  const {model}=harness();
  for(const deadline of ['2026-11-10T23:59:00','2026-02-30T12:00:00Z','2026-11-10T24:00:00Z','2026-11-10T12:60:00Z','2026-11-10T12:00:60Z','2026-13-01T12:00:00Z']){
    assert.equal(model.problem(reminder({deadline}),[conference(deadline)]),'提醒格式无效',deadline);
  }
  assert.equal(model.problem(reminder({leadMinutes:'1440'}),[conference()]),'提醒格式无效');
  assert.equal(model.problem(reminder({leadMinutes:120}),[conference()]),'提醒格式无效');
  assert.equal(model.problem(reminder({enabled:1}),[conference()]),'提醒格式无效');
});

test('a changed official deadline or unavailable track prevents delivery',()=>{
  const {model}=harness();
  assert.equal(model.problem(reminder(),[conference('2026-11-12T11:59:00Z')]),'日期已变化，请重新设置');
  assert.equal(model.problem(reminder({trackName:'Missing'}),[conference()]),'当前节点日期待核验');
  assert.equal(model.problem(reminder({conferenceId:'missing'}),[conference()]),'当前节点日期待核验');
});

test('calendar includes only enabled, verified future reminders and an explicit alarm',()=>{
  const {model}=harness();
  const full=reminder({id:'full',kind:'full',deadline:'2026-11-17T11:59:00Z',leadMinutes:0});
  const text=model.calendar([reminder(),full,reminder({id:'paused',enabled:false}),reminder({id:'changed',deadline:'2026-11-12T00:00:00Z'})],[conference()],epoch);
  assert.equal((text.match(/BEGIN:VEVENT/g)||[]).length,2);
  assert.equal((text.match(/BEGIN:VALARM/g)||[]).length,2);
  assert.ok(text.includes('DTSTART:20261111T115900Z\r\n'));
  assert.ok(text.includes('TRIGGER:-PT1440M\r\n'));
  assert.ok(text.includes('TRIGGER:PT0M\r\n'));
  assert.ok(text.endsWith('END:VCALENDAR\r\n'));
  assert.equal((model.calendar([reminder()],[conference()],Date.parse('2026-11-10T12:00:00Z')).match(/BEGIN:VEVENT/g)||[]).length,0);
});

test('calendar text escapes delimiters/newlines and folds UTF-8 lines within 75 octets',()=>{
  const {model}=harness();
  const track='多模态🪵'.repeat(15)+'\\;逗号,换行\r\n下一行\n再一行\r末行';
  const text=model.calendar([reminder({trackName:track})],[conference(undefined,track)],epoch);
  for(const line of text.split('\r\n'))assert.ok(Buffer.byteLength(line,'utf8')<=75,`line too long: ${line}`);
  assert.ok(!text.replaceAll('\r\n','').includes('\r'),'no bare CR may remain');
  assert.ok(!text.replaceAll('\r\n','').includes('\n'),'no bare LF may remain');
  const unfolded=text.replace(/\r\n[ \t]/g,'');
  const escaped=track.replace(/\\/g,'\\\\').replace(/\r\n|\r|\n/g,'\\n').replace(/;/g,'\\;').replace(/,/g,'\\,');
  assert.ok(unfolded.includes('SUMMARY:CVPR · '+escaped+' · 摘要截止\r\n'));
  assert.equal(Buffer.from(text).toString('utf8'),text);
});

test('invited authors can save reminders with the restriction preserved across UI, calendar and notifications',async()=>{
  const c=conference(null,'Second Stage');
  c.detail.tracks[0].fullDeadline=new Date(epoch+10_000).toISOString();
  c.detail.tracks[0].submissionStage='invitation-only';
  const h=harness({conferences:[c]});
  const form=h.ui.renderConference('cvpr');
  assert.match(form,/<option[^>]*>Second Stage · 仅限获邀 · 全文/);
  assert.ok(form.includes('不接受普通新稿'));
  await h.submitReminder();
  const saved=h.items[0];
  assert.equal(saved.enabled,true);
  assert.equal(h.model.problem(saved,[c]),null);
  assert.ok(h.messages[0].includes('提醒已保存。仅限获邀稿件'));
  assert.ok(h.ui.renderSummary().includes('Second Stage · 仅限获邀'));
  assert.equal(Object.hasOwn(saved,'submissionStage'),false,'restriction comes from current catalog');
  const calendar=h.model.calendar(h.items,[c],epoch).replace(/\r\n[ \t]/g,'');
  assert.ok(calendar.includes('SUMMARY:CVPR · Second Stage · 全文截止 · 仅限获邀\r\n'));
  assert.ok(calendar.includes('DESCRIPTION:仅限获邀稿件；此阶段不接受普通新稿。'));
  assert.ok(calendar.includes('DESCRIPTION:CVPR · Second Stage · 全文截止 · 仅限获邀\r\n'));
  h.setTime(epoch+15_000);await h.tick();
  assert.equal(h.notifications.length,1);
  assert.ok(h.notifications[0].body.includes('仅限获邀'));
  assert.ok(h.messages[1].includes('仅限获邀'));
});

test('existing reminder restrictions reflect current catalog metadata without changing saved records',()=>{
  const c=conference(),item=reminder();
  const h=harness({conferences:[c],items:[item]});
  assert.ok(!h.ui.renderSummary().includes('仅限获邀'));
  c.detail.tracks[0].submissionStage='invitation-only';
  assert.ok(h.ui.renderSummary().includes('仅限获邀'));
  assert.ok(h.model.calendar([item],[c],epoch).replace(/\r\n[ \t]/g,'').includes('仅限获邀'));
  assert.deepEqual(h.items,[item]);
});

test('tick delivers only after the deadline crosses, then deduplicates subsequent ticks',async()=>{
  const deadline=new Date(epoch+10_000).toISOString();
  const h=harness({conferences:[conference(deadline)],items:[reminder({deadline,leadMinutes:0})]});
  h.setTime(epoch+9_000);await h.tick();assert.equal(h.messages.length,0);
  h.setTime(epoch+15_000);await h.tick();assert.equal(h.messages.length,1);assert.equal(h.notifications.length,1);
  h.setTime(epoch+30_000);await h.tick();await h.visibility();assert.equal(h.messages.length,1);
  assert.ok(h.storage.has('conf-atlas-delivered:user-a'));
});

test('tick does not replay past-startup reminders or a sleep gap over two minutes',async()=>{
  const deadline=new Date(epoch+10_000).toISOString();
  const item=reminder({deadline,leadMinutes:0});
  const past=harness({start:epoch+11_000,conferences:[conference(deadline)],items:[item]});
  past.setTime(epoch+15_000);await past.tick();assert.equal(past.messages.length,0);
  const sleep=harness({conferences:[conference(deadline)],items:[item]});
  sleep.setTime(epoch+131_000);await sleep.visibility();assert.equal(sleep.messages.length,0);
});

test('paused or changed reminders never trigger; ordinary preference refresh does not lose a due reminder',async()=>{
  const deadline=new Date(epoch+10_000).toISOString();
  const h=harness({conferences:[conference(deadline)],items:[reminder({deadline,leadMinutes:0})]});
  h.setTime(epoch+5_000);h.setItems([reminder({deadline,leadMinutes:0,enabled:false})]);
  h.setTime(epoch+15_000);await h.tick();assert.equal(h.messages.length,0);
  const active=harness({conferences:[conference(deadline)],items:[reminder({deadline,leadMinutes:0})]});
  active.setTime(epoch+11_000);active.ui.stateChanged();
  active.setTime(epoch+15_000);await active.tick();assert.equal(active.messages.length,1);
  const changed=harness({conferences:[conference(new Date(epoch+20_000).toISOString())],items:[reminder({deadline,leadMinutes:0})]});
  changed.setTime(epoch+15_000);await changed.tick();assert.equal(changed.messages.length,0);
});

test('an immediate account change resets the tick baseline before its first reminder becomes due',async()=>{
  const deadline=new Date(epoch+10_000).toISOString();
  const h=harness({scope:'guest',conferences:[conference(deadline)]});
  h.setTime(epoch+1_000);h.switchAccount('user-a',[reminder({deadline,leadMinutes:0})]);
  h.setTime(epoch+15_000);await h.tick();assert.equal(h.messages.length,1);
  assert.ok(h.storage.has('conf-atlas-delivered:user-a'));
  assert.ok(!h.storage.has('conf-atlas-delivered:guest'));
});

test('A to B to A within a tick cannot replay reminders that elapsed while A was signed out',async()=>{
  const deadline=new Date(epoch+10_000).toISOString();
  const item=reminder({deadline,leadMinutes:0});
  const h=harness({scope:'user-a',conferences:[conference(deadline)],items:[item]});
  h.setTime(epoch+5_000);h.switchAccount('user-b',[]);
  h.setTime(epoch+11_000);h.switchAccount('user-a',[item]);
  h.setTime(epoch+15_000);await h.tick();assert.equal(h.messages.length,0);
});

test('delivery receipts for a different account do not suppress the current account',async()=>{
  const deadline=new Date(epoch+10_000).toISOString();
  const item=reminder({deadline,leadMinutes:0});
  const storage=new Map([['conf-atlas-delivered:user-a',JSON.stringify([item.id+':'+deadline+':0'])]]);
  const h=harness({scope:'user-b',storage,conferences:[conference(deadline)],items:[item]});
  h.setTime(epoch+15_000);await h.tick();assert.equal(h.messages.length,1);
  assert.ok(storage.has('conf-atlas-delivered:user-b'));
});

test('guest reminder views reveal no saved records and cannot trigger notifications or actions',async()=>{
  const deadline=new Date(epoch+10_000).toISOString(),item=reminder({deadline,leadMinutes:0});
  const h=harness({scope:'guest',conferences:[conference(deadline)],items:[item]});
  for(const html of [h.ui.renderConference('cvpr'),h.ui.renderSummary()]){
    assert.ok(html.includes('data-require-login'));
    assert.ok(!html.includes('data-reminder-form'));
    assert.ok(!html.includes(item.id));
    assert.ok(!html.includes('data-reminder-export'));
  }
  h.setTime(epoch+15_000);await h.tick();await h.visibility();
  assert.deepEqual(h.messages,[]);assert.deepEqual(h.notifications,[]);
  assert.equal(h.storage.has('conf-atlas-delivered:guest'),false);
  await h.clickReminderAction();assert.equal(h.loginRequests,1);
});
