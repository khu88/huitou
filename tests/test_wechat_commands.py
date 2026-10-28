import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from server import DEFAULT_STATE, validate_state_patch
from wechat_commands import MAX_TEXT, execute, reminder_due, reminder_problem


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)


class WechatCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'data/conferences.json').read_text())

    def setUp(self):
        self.state = copy.deepcopy(DEFAULT_STATE)

    def run_command(self, text, state=None, catalog=None, now=NOW):
        return execute(text, catalog or self.catalog, self.state if state is None else state, now)

    def test_read_queries_are_bounded_and_do_not_modify_inputs(self):
        before = copy.deepcopy(self.state)
        commands = ['帮助', '你好', 'AAAI', '查会议 ICLR', '人工智能 A类会议', '未来30天',
                    '这个月截止', '我的收藏', '我的提醒', '会议 第2页']
        for c in self.catalog['conferences']:
            if c.get('detail'):
                commands += [c['acronym'] + ' ' + intent for intent in
                             ['截止', '投稿', '模板', '录用率', '参会', '论文', '论文 第2页']]
        for command in commands:
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result['patch'], {})
                self.assertTrue(result['text'])
                self.assertLessEqual(len(result['text']), MAX_TEXT)
        self.assertEqual(before, self.state)

    def test_deadline_conversion_and_original_source_are_visible(self):
        result = self.run_command('CVPR 截止')['text']
        self.assertIn('2026-11-11 19:59', result)  # November 10 AoE -> UTC+8 next evening.
        self.assertIn('2026-11-10T23:59:00-12:00', result)
        self.assertIn('剩余', result)
        self.assertIn('openreview.net', result)
        self.assertIn('2026-10-28', result)

    def test_www_conflicts_preserve_portal_and_cfp_distinction(self):
        result = self.run_command('WWW 第4轨 截止')['text']
        self.assertIn('2026-11-15T21:00:00Z', result)
        self.assertIn('冲突', result)
        self.assertIn('expdate', result)
        self.assertIn('投稿系统', result)

    def test_unknown_conference_details_not_invented(self):
        catalog = copy.deepcopy(self.catalog)
        next(c for c in catalog['conferences'] if c['id'] == 'icassp').pop('detail', None)
        text = self.run_command('ICASSP 截止', catalog=catalog)['text']
        self.assertIn('详情尚未核验', text)
        self.assertNotIn('剩余', text)
        self.assertIn('CCF B', text)

    def test_date_only_deadlines_are_visible_but_cannot_create_reminders(self):
        catalog = copy.deepcopy(self.catalog)
        c = next(c for c in catalog['conferences'] if c['id'] == 'cvpr')
        c['detail']['tracks'] = [dict(name='Date-only main', primary=True,
                                     fullDeadlineDate='2026-11-20', sources=['https://example.org/cfp'])]
        text = self.run_command('CVPR 截止', catalog=catalog)['text']
        self.assertIn('2026-11-20 · 仅确认日期', text)
        self.assertNotIn('剩余', text)
        result = self.run_command('提醒 CVPR 全文 提前1天', catalog=catalog)
        self.assertEqual(result['patch'], {})

    def test_rolling_and_invitation_only_are_explicit(self):
        catalog = copy.deepcopy(self.catalog)
        c = next(c for c in catalog['conferences'] if c['id'] == 'cvpr')
        c['detail']['tracks'] = [dict(name='Rolling', deadlineMode='rolling'),
            dict(name='Rolling cycle', deadlineMode='rolling', fullDeadline='2026-11-02T12:00:00Z'),
            dict(name='Invited extension', fullDeadline='2026-11-01T12:00:00Z',
                 submissionStage='invitation-only')]
        text = self.run_command('CVPR 截止', catalog=catalog)['text']
        self.assertIn('滚动投稿', text)
        self.assertIn('仅限获邀稿件', text)
        future = self.run_command('未来30天', catalog=catalog)['text']
        self.assertNotIn('Invited extension', future)
        self.assertNotIn('Rolling cycle', future)
        self.assertIn('仅日期、滚动和获邀阶段不计入本查询', future)

    def test_invited_authors_can_save_and_list_reminders_with_current_stage_restriction(self):
        catalog = copy.deepcopy(self.catalog)
        c = next(c for c in catalog['conferences'] if c['id'] == 'cvpr')
        c['detail']['tracks'] = [dict(name='Second Stage', primary=True,
                                     fullDeadline='2026-11-01T12:00:00Z',
                                     submissionStage='invitation-only')]
        result = self.run_command('提醒 CVPR 全文 提前1天', catalog=catalog)
        state = validate_state_patch(result['patch'], self.state)
        row = state['reminders'][0]
        self.assertTrue(row['enabled'])
        self.assertIsNone(reminder_problem(row, catalog))
        self.assertIn('已保存 CVPR', result['text'])
        self.assertIn('仅限获邀稿件；此阶段不接受普通新稿。', result['text'])
        self.assertNotIn('submissionStage', row)
        self.assertIn('仅限获邀稿件', self.run_command('我的提醒', state, catalog)['text'])
        # Existing reminder snapshots use the current catalog instead of stale metadata.
        c['detail']['tracks'][0].pop('submissionStage')
        self.assertNotIn('仅限获邀', self.run_command('我的提醒', state, catalog)['text'])

    def test_reminder_track_choice_labels_invited_stage(self):
        catalog = copy.deepcopy(self.catalog)
        c = next(c for c in catalog['conferences'] if c['id'] == 'cvpr')
        c['detail']['tracks'] = [
            dict(name='Main Papers', fullDeadline='2026-11-01T12:00:00Z'),
            dict(name='Second Stage', fullDeadline='2026-11-05T12:00:00Z',
                 submissionStage='invitation-only')]
        result = self.run_command('提醒 CVPR 全文 提前1天', catalog=catalog)
        self.assertEqual(result['patch'], {})
        self.assertIn('第2轨 · Second Stage · 仅限获邀', result['text'])
        ordinary = self.run_command('提醒 CVPR 第1轨 全文 提前1天', catalog=catalog)
        self.assertNotIn('仅限获邀', ordinary['text'])
        self.assertTrue(ordinary['patch']['reminders'][0]['enabled'])

    def test_statistics_use_actual_counts_and_label_window(self):
        text = self.run_command('ICLR 录用率')['text']
        self.assertIn('2023、2024、2025', text)
        self.assertIn('1574/4938 = 31.88%', text)
        self.assertIn('https://media.iclr.cc/', text)
        unknown = self.run_command('WWW 录用率')['text']
        self.assertIn('2023：未取得可核验的成对数量', unknown)

    def test_attendance_does_not_infer_current_year(self):
        text = self.run_command('ICLR 是否必须线下参会')['text']
        self.assertIn('历史届次', text)
        self.assertIn('2024：未确认', text)
        self.assertIn('不能仅据此判定', text)

    def test_papers_keep_labels_prioritize_awards_and_paginate(self):
        first = self.run_command('CVPR 论文')['text']
        second = self.run_command('CVPR 论文 第2页')['text']
        self.assertIn('共10篇', first)
        self.assertIn('[Best Paper] VGGT', first)
        self.assertIn('[Best Student Paper]', first)
        self.assertIn('[Oral]', first)
        self.assertIn('10.', second)
        self.assertNotIn('11.', second)
        self.assertIn('标签来源', second)

    def test_favorite_and_remove_pause_only_target(self):
        result = self.run_command('收藏 AAAI')
        self.assertEqual(result['patch'], {'favorites': ['aaai']})
        self.assertIn('不会自动创建提醒', result['text'])
        state = validate_state_patch(result['patch'], self.state)
        state['reminders'] = [dict(id='one', conferenceId='aaai', enabled=True),
                              dict(id='two', conferenceId='cvpr', enabled=True)]
        result = self.run_command('取消收藏 AAAI', state)
        self.assertEqual(result['patch']['favorites'], [])
        self.assertFalse(result['patch']['reminders'][0]['enabled'])
        self.assertTrue(result['patch']['reminders'][1]['enabled'])
        self.assertTrue(state['reminders'][0]['enabled'])

    def test_mutation_requires_unambiguous_explicit_command(self):
        for text in ['不要收藏 AAAI', '收藏 AAAI 吗', '收藏 AAAI ICLR', '提醒 CVPR 全文 提前7天 但不要保存',
                     '提醒 CVPR 摘要和全文 提前7天', '恢复全部提醒', '删除提醒 missing']:
            with self.subTest(text=text):
                self.assertEqual(self.run_command(text)['patch'], {})
        for text in ['删除 AAAI', '我想收藏 AAAI', 'AAAI 提醒']:
            self.assertIn('未执行修改', self.run_command(text)['text'])

    def test_state_capacity_replies_without_invalid_patch(self):
        self.state['favorites'] = ['saved-' + str(i) for i in range(1000)]
        for text in ['收藏 AAAI', '提醒 CVPR 全文 提前7天']:
            result = self.run_command(text)
            self.assertEqual(result['patch'], {})
            self.assertIn('1000', result['text'])
        self.state['favorites'][-1] = 'cvpr'
        existing = self.run_command('提醒 CVPR 全文 提前7天')['patch']
        validate_state_patch(existing, self.state)
        self.state['reminders'] = [dict(existing['reminders'][0], id='saved-' + str(i),
                                       trackName='Old Track ' + str(i)) for i in range(200)]
        result = self.run_command('提醒 CVPR 全文 提前7天')
        self.assertEqual(result['patch'], {})
        self.assertIn('200', result['text'])

    def test_reminder_valid_and_idempotent_with_shared_state_schema(self):
        result = self.run_command('提醒 CVPR 全文 提前7天')
        state = validate_state_patch(result['patch'], self.state)
        self.assertEqual(state['favorites'], ['cvpr'])
        reminder = state['reminders'][0]
        self.assertEqual(reminder['leadMinutes'], 10080)
        self.assertEqual(reminder['kind'], 'full')
        self.assertEqual(reminder['deadline'], '2026-11-16T23:59:00-12:00')
        self.assertIsNone(reminder_problem(reminder, self.catalog))
        again = self.run_command('提醒 CVPR 全文 提前7天', state)
        state2 = validate_state_patch(again['patch'], state)
        self.assertEqual(state2['reminders'], state['reminders'])
        self.assertEqual(self.state['reminders'], [])

    def test_multiple_tracks_require_track_number(self):
        unselected = self.run_command('提醒 ACL 全文 提前7天')
        self.assertEqual(unselected['patch'], {})
        self.assertIn('第1轨', unselected['text'])
        self.assertIn('第2轨', unselected['text'])
        selected = self.run_command('提醒 ACL 第1轨 全文 提前7天')
        self.assertEqual(len(selected['patch']['reminders']), 1)
        validate_state_patch(selected['patch'], self.state)
        invalid = self.run_command('提醒 ACL 第99轨 全文 提前7天')
        self.assertEqual(invalid['patch'], {})

    def test_unknown_or_past_dates_and_unsupported_leads_fail_closed(self):
        for text in ['提醒 ACL 第1轨 摘要 提前7天', '提醒 ICLR 全文 提前7天',
                     '提醒 ICASSP 全文 提前1天', '提醒 CVPR 全文 提前2天',
                     '提醒 CVPR 全文']:
            with self.subTest(text=text):
                self.assertEqual(self.run_command(text)['patch'], {})
        late = self.run_command('提醒 CVPR 全文 提前7天', now='2026-11-15T00:00:00Z')
        self.assertEqual(late['patch'], {})
        self.assertIn('时间已过', late['text'])

    def test_pause_resume_delete_and_reconciliation(self):
        state = validate_state_patch(self.run_command('提醒 CVPR 全文 提前7天')['patch'], self.state)
        identifier = state['reminders'][0]['id']
        paused = self.run_command('暂停提醒 ' + identifier, state)
        state = validate_state_patch(paused['patch'], state)
        self.assertFalse(state['reminders'][0]['enabled'])
        resumed = self.run_command('恢复提醒 ' + identifier, state)
        self.assertTrue(resumed['patch']['reminders'][0]['enabled'])
        state['reminders'][0]['deadline'] = '2026-11-30T00:00:00Z'
        refused = self.run_command('恢复提醒 ' + identifier, state)
        self.assertEqual(refused['patch'], {})
        self.assertIn('日期已变化', refused['text'])
        deleted = self.run_command('删除提醒 ' + identifier, state)
        self.assertEqual(deleted['patch']['reminders'], [])

    def test_pause_all_and_list_share_stable_ids(self):
        state = validate_state_patch(self.run_command('提醒 CVPR 全文 提前7天')['patch'], self.state)
        text = self.run_command('我的提醒', state)['text']
        self.assertIn(state['reminders'][0]['id'], text)
        self.assertIn('2026-11-10 19:59', text)
        self.assertFalse(self.run_command('暂停全部提醒', state)['patch']['reminders'][0]['enabled'])

    def test_snapshot_changes_and_malformed_dates_rejected(self):
        row = self.run_command('提醒 CVPR 全文 提前7天')['patch']['reminders'][0]
        for deadline in ['bad', '2026-11-16T23:59:00', None]:
            bad = dict(row, deadline=deadline)
            self.assertIsNone(reminder_due(bad))
            self.assertEqual(reminder_problem(bad, self.catalog), '提醒格式无效')
        changed = dict(row, deadline='2026-12-01T00:00:00Z')
        self.assertEqual(reminder_problem(changed, self.catalog), '日期已变化，请重新设置')
        absent = dict(row, trackName='Unknown')
        self.assertEqual(reminder_problem(absent, self.catalog), '当前节点日期待核验')
        equivalent = dict(row, deadline='2026-11-17T11:59:00Z')
        self.assertIsNone(reminder_problem(equivalent, self.catalog))

    def test_upcoming_subset_and_month_boundary(self):
        self.state['favorites'] = ['cvpr']
        text = self.run_command('我的收藏截止')['text']
        self.assertIn('CVPR', text)
        self.assertNotIn('WWW', text)
        self.assertIn('2个已核验节点', text)
        month = self.run_command('这个月截止')['text']
        self.assertIn('2026-11-01 00:00', month)
        self.assertNotIn('CVPR', month)

    def test_queries_match_complete_alias_and_english_names(self):
        self.assertIn('ICLR', self.run_command('请问ICLR什么时候交')['text'])
        self.assertNotIn('CCF', self.run_command('SOMEICLRSTRING')['text'].splitlines()[0])
        self.assertIn('ACM SIGOPS ATC', self.run_command('USENIX ATC')['text'])
        search = self.run_command('人工智能 A类会议')['text']
        self.assertIn('AAAI · A', search)
        self.assertNotIn('ICASSP · B', search)

    def test_limits_empty_text_and_timezone_fallback(self):
        self.assertEqual(self.run_command('x' * 2001)['patch'], {})
        self.assertIn('文字', self.run_command('')['text'])
        self.state['settings']['timezone'] = 'not/a/timezone'
        self.assertIn('UTC', self.run_command('CVPR 截止')['text'])


if __name__ == '__main__':
    unittest.main()
