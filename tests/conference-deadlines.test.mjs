import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

// Exercise the real read-only rendering/model functions before UI event wiring.
const source=readFileSync(new URL('../app.js',import.meta.url),'utf8');
const prefix=source.slice(0,source.indexOf("  document.addEventListener('conf-login-required'"));
const epoch=Date.parse('2026-10-28T00:00:00Z');
class Clock extends Date { constructor(...args){super(...(args.length?args:[epoch]));} static now(){return epoch;} }
const context={window:{},location:{search:''},URL,URLSearchParams,Date:Clock,Intl};
vm.runInNewContext(prefix+'window.testModel={nearest,openTrack,filtered,state,setConferences:v=>{conferences=v},deadlineEntries,renderListDeadline,renderTrack,statusOf};})();',context);
const model=context.window.testModel;
const conf=tracks=>({id:'example',acronym:'Example',detail:{year:2027,tracks}});

test('calendar-only deadlines stay visible without invented clocks or countdowns',()=>{
  const c=conf([{name:'Research',primary:true,fullDeadlineDate:'2026-11-20',sources:['https://example.org/cfp']}]);
  assert.equal(model.nearest(c),null);
  assert.equal(model.deadlineEntries(c).length,0);
  const row=model.renderListDeadline(c), detail=model.renderTrack(c.detail.tracks[0],0,c);
  for(const html of [row,detail]){
    assert.ok(html.includes('2026-11-20'));
    assert.ok(html.includes('时刻或时区'));
    assert.ok(!html.includes('data-countdown'));
    assert.ok(!html.includes('data-export'));
  }
});

test('abstract-only first stage is shown and invited full-paper extension is not an open opportunity',()=>{
  const c=conf([{name:'Initial abstract',primary:true,abstractDeadline:'2026-12-04T23:59:00-12:00',abstractTimezone:'AoE'},
    {name:'Invited full paper',fullDeadline:'2027-04-16T23:59:00-12:00',submissionStage:'invitation-only'}]);
  assert.equal(model.nearest(c).kind,'abstractDeadline');
  assert.equal(model.openTrack(c.detail.tracks[0]),true);
  assert.equal(model.openTrack(c.detail.tracks[1]),false);
  assert.ok(model.renderListDeadline(c).includes('摘要 / 初投'));
  assert.ok(!model.renderListDeadline(c).includes('其他 Track 未截止'));
  assert.ok(model.renderTrack(c.detail.tracks[1],1,c).includes('仅限获邀稿件'));
});

test('rolling submissions have a distinct label and no calendar timestamp',()=>{
  const c=conf([{name:'Rolling',primary:true,deadlineMode:'rolling',sources:['https://example.org/cfp']}]);
  assert.ok(model.renderListDeadline(c).includes('滚动投稿'));
  assert.ok(model.renderTrack(c.detail.tracks[0],0,c).includes('没有单一年度全文截止时间'));
  assert.equal(model.deadlineEntries(c).length,0);
});

test('the original stage timezone is used and reused templates are labelled',()=>{
  const c=conf([{name:'Research',primary:true,abstractDeadline:'2026-12-04T20:00:00Z',abstractTimezone:'UTC',
    timezone:'AoE',template:{year:2025,status:'fallback',url:'https://example.org/style.zip'}}]);
  assert.ok(model.renderListDeadline(c).includes('>UTC</span>'));
  assert.ok(model.renderTrack(c.detail.tracks[0],0,c).includes('沿用 2025 年模板'));
});


test('open filters include future calendar dates and rolling submissions without inventing clocks',()=>{
  const dated={...conf([{name:'Main',primary:true,fullDeadlineDate:'2026-12-14'}]),id:'date'};
  const rolling={...conf([{name:'Rolling',primary:true,deadlineMode:'rolling'}]),id:'rolling'};
  const uncertain={...conf([{name:'Main',primary:true,fullDeadlineDate:'2026-10-28'}]),id:'boundary'};
  const past={...conf([{name:'Main',primary:true,fullDeadlineDate:'2026-10-26'}]),id:'past'};
  const invited={...conf([{name:'Invited',primary:true,fullDeadline:'2026-12-14T20:00:00Z',submissionStage:'invitation-only'}]),id:'invited'};
  model.setConferences([dated,rolling,uncertain,past,invited]);
  for(const status of ['upcoming','any-upcoming']){
    model.state.status=status;
    assert.deepEqual(Array.from(model.filtered(),c=>c.id).sort(),['date','rolling']);
  }
  assert.equal(model.nearest(dated),null);
  assert.equal(model.deadlineEntries(dated).length,0);
  assert.equal(model.statusOf(past),'closed');
  assert.equal(model.statusOf(uncertain),'date-only');
  assert.equal(model.statusOf(rolling),'rolling');
  model.state.status='date-only';
  assert.deepEqual(Array.from(model.filtered(),c=>c.id).sort(),['boundary','date','past']);
  model.state.status='rolling';
  assert.deepEqual(Array.from(model.filtered(),c=>c.id),['rolling']);
  model.state.status='all';
});
