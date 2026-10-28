"""Ranking provenance checks use synthetic records; no network or user data."""
import csv
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_data import validate_data, validate_rankings


def fixture():
    sources = {
        'core': {'version': 'ICORE2026', 'source': 'https://example.org/core.csv', 'sourceLabel': 'CORE test source'},
        'thcpl': {'version': '2019-08-13', 'source': 'https://example.org/thcpl.pdf', 'sourceLabel': 'TH-CPL test source'},
    }
    rankings = {}
    for system, source in sources.items():
        rankings[system] = {
            **source, 'status': 'verified', 'rank': 'A', 'verifiedAt': '2026-10-28',
            'note': 'Synthetic evidence for validator tests.',
            'sourceTitle': 'Example Conference', 'matchMethod': 'normalized-title',
            **({'sourceRecordId': '123'} if system == 'core' else {'sourcePage': 2}),
        }
    return {'asOf': '2026-10-28', 'rankingSources': sources,
            'conferences': [{'id': 'example', 'rank': 'N', 'rankings': rankings}]}


class RankingValidationTests(unittest.TestCase):
    def test_verified_external_rank_is_independent_of_ccf_rank(self):
        data = fixture()
        counts = validate_rankings(data)
        self.assertEqual(dict(counts), {'coreVerified': 1, 'thcplVerified': 1})
        self.assertEqual(data['conferences'][0]['rank'], 'N')

    def test_unconfirmed_and_officially_unranked_remain_distinct(self):
        data = fixture()
        first = data['conferences'][0]
        first['rankings']['core'].update(status='listed-unranked', rank=None, sourceRank='Unranked')
        first['rankings']['thcpl'].update(status='unconfirmed', rank=None)
        counts = validate_rankings(data)
        self.assertEqual(counts['coreListedUnranked'], 1)
        self.assertEqual(counts['thcplUnconfirmed'], 1)
        self.assertEqual(counts['coreVerified'], 0)

    def test_unconfirmed_cannot_inherit_a_ccf_or_guessed_grade(self):
        for status in ('unconfirmed', 'listed-unranked'):
            with self.subTest(status=status):
                data = fixture()
                data['conferences'][0]['rankings']['core'].update(status=status, rank='A')
                with self.assertRaisesRegex(AssertionError, 'must not claim a rank'):
                    validate_rankings(data)

    def test_verified_requires_a_supported_grade_for_its_own_system(self):
        for system, invalid in [('core', None), ('core', 'N'), ('thcpl', 'A*'), ('thcpl', 'C')]:
            with self.subTest(system=system, invalid=invalid):
                data = fixture()
                data['conferences'][0]['rankings'][system]['rank'] = invalid
                with self.assertRaisesRegex(AssertionError, 'invalid verified rank'):
                    validate_rankings(data)

    def test_each_rating_requires_absolute_http_source_and_version(self):
        for field, value in [('source', None), ('source', '/local.pdf'), ('source', 'https:///missing-host'),
                             ('source', 'javascript:alert(1)'), ('source', 'https://unrelated.example/rank'),
                             ('version', None), ('version', 'older-edition')]:
            with self.subTest(field=field, value=value):
                data = fixture()
                data['conferences'][0]['rankings']['core'][field] = value
                with self.assertRaises(AssertionError):
                    validate_rankings(data)

    def test_global_source_metadata_is_required_even_when_all_ranks_unknown(self):
        data = fixture()
        for item in data['conferences'][0]['rankings'].values():
            item.update(rank=None, status='unconfirmed')
        del data['rankingSources']['core']['version']
        with self.assertRaisesRegex(AssertionError, 'source version missing'):
            validate_rankings(data)

    def test_matched_rating_must_be_traceable_to_the_official_row_or_page(self):
        for system, field, value in [('core', 'sourceRecordId', ''), ('core', 'sourceTitle', ''),
                                      ('core', 'matchMethod', ''), ('thcpl', 'sourcePage', 0),
                                      ('thcpl', 'sourcePage', 18), ('thcpl', 'sourcePage', True)]:
            with self.subTest(system=system, field=field, value=value):
                data = fixture()
                data['conferences'][0]['rankings'][system][field] = value
                with self.assertRaises(AssertionError):
                    validate_rankings(data)

    def test_unranked_claim_requires_the_source_wording(self):
        for source_rank in (None, '', 'A*'):
            with self.subTest(source_rank=source_rank):
                data = fixture()
                data['conferences'][0]['rankings']['core'].update(status='listed-unranked', rank=None, sourceRank=source_rank)
                with self.assertRaises(AssertionError):
                    validate_rankings(data)

    def test_verification_date_must_exist_and_not_exceed_snapshot_date(self):
        for value in (None, '2026-02-30', '2026-10-29'):
            with self.subTest(value=value):
                data = fixture()
                data['conferences'][0]['rankings']['core']['verifiedAt'] = value
                with self.assertRaises(AssertionError):
                    validate_rankings(data)

    def test_each_conference_has_explicit_state_for_both_rankings(self):
        data = fixture()
        del data['conferences'][0]['rankings']['thcpl']
        with self.assertRaisesRegex(AssertionError, 'ranking entry missing'):
            validate_rankings(data)

    def test_shipped_snapshot_retains_reported_coverage_and_unknown_dates(self):
        data = json.loads((ROOT / 'data' / 'conferences.json').read_text())
        counts = validate_data(data)
        self.assertEqual(len(data['conferences']), 390)
        self.assertGreaterEqual(counts['details'], 12)
        self.assertGreaterEqual(counts['tracks'], 27)
        self.assertGreaterEqual(counts['deadlines'], 41)
        self.assertGreaterEqual(counts['acceptanceRecords'], 20)
        self.assertGreaterEqual(counts['curatedPapers'], 88)
        unknown_main = {c['id'] for c in data['conferences'] if c.get('detail') and
                        any(t.get('primary') and not t.get('fullDeadline') for t in c['detail']['tracks'])}
        for c in data['conferences']:
            if c['id'] in unknown_main:
                self.assertTrue(any(t.get('primary') and t.get('fullDeadline') is None for t in c['detail']['tracks']))

    def test_shipped_ratings_match_saved_official_records_and_snapshot_hashes(self):
        data = json.loads((ROOT / 'data' / 'conferences.json').read_text())
        with (ROOT / 'research/sources/core-icore2026.csv').open(newline='') as stream:
            core = {row[0]: row for row in csv.reader(stream)}
        thcpl = {row['id']: row for row in json.loads((ROOT / 'research/sources/th-cpl-2019-08-13-conferences.json').read_text())}
        for system in ('core', 'thcpl'):
            metadata = data['rankingSources'][system]
            self.assertEqual(hashlib.sha256((ROOT / metadata['snapshot']).read_bytes()).hexdigest(), metadata['sha256'])
            used = set()
            for conference in data['conferences']:
                entry = conference['rankings'][system]
                if entry['status'] == 'unconfirmed':
                    continue
                with self.subTest(conference=conference['id'], system=system):
                    record_id = entry['sourceRecordId']
                    self.assertNotIn(record_id, used, 'One official row must not rate two distinct conferences')
                    used.add(record_id)
                    if system == 'core':
                        record = core[record_id]
                        self.assertEqual(entry['sourceTitle'], record[1].strip())
                        self.assertEqual(entry['sourceRank'], record[4])
                        self.assertEqual(entry['version'], record[3])
                    else:
                        record = thcpl[record_id]
                        self.assertEqual(entry['sourceTitle'], record['title'])
                        self.assertEqual(entry['rank'], record['rank'])
                        self.assertEqual(entry['sourcePage'], record['page'])

    def test_same_acronyms_and_historical_names_do_not_cross_map(self):
        conferences = {c['id']: c for c in json.loads((ROOT / 'data' / 'conferences.json').read_text())['conferences']}
        expected = {
            'fse-software': ('52', 'A*'), 'fse-security': ('1475', 'B'),
            'acm-sigops-atc': ('1838', 'A'), 'iclr': ('2273', 'A*'),
            'neurips': ('98', 'A*'), 'sigkdd': ('26', 'A*'),
        }
        for name, (record_id, rank) in expected.items():
            with self.subTest(conference=name):
                entry = conferences[name]['rankings']['core']
                self.assertEqual((entry['sourceRecordId'], entry['rank']), (record_id, rank))
        edge = conferences['sec-architecture']['rankings']['core']
        self.assertEqual((edge['sourceRecordId'], edge['rank'], edge['status']), ('2246', None, 'listed-unranked'))
        security = conferences['sec-security']['rankings']['core']
        if security['status'] == 'verified':
            self.assertEqual((security['sourceRecordId'], security['rank']), ('804', 'B'))
        wisa = conferences['wisa']['rankings']['core']
        self.assertEqual((wisa['rank'], wisa['status']), (None, 'unconfirmed'))
        for system in ('core', 'thcpl'):
            self.assertIn('USENIX', conferences['acm-sigops-atc']['rankings'][system]['note'])
        self.assertEqual(conferences['fse-software']['rankings']['thcpl']['sourcePage'], 8)
        self.assertEqual(conferences['fse-security']['rankings']['thcpl']['sourcePage'], 6)


class ExpandedDetailValidationTests(unittest.TestCase):
    """Reject claims that would turn incomplete evidence into misleading UI data."""
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads((ROOT / 'data/conferences.json').read_text())

    def setUp(self):
        self.data = copy.deepcopy(self.snapshot)
        self.row = next(c for c in self.data['conferences'] if c.get('detail') and c['detail']['tracks'])
        self.track = self.row['detail']['tracks'][0]

    def test_date_only_requires_evidence_even_without_time_or_zone(self):
        self.track.update(abstractDeadline=None, fullDeadline=None,
                          fullDeadlineDate='2027-01-20', sources=[])
        with self.assertRaisesRegex(AssertionError, 'calendar-only deadline requires a source'):
            validate_data(self.data)

    def test_abstract_calendar_date_cannot_follow_full_paper_date(self):
        self.track.update(abstractDeadline=None, fullDeadline=None,
                          abstractDeadlineDate='2027-01-21', fullDeadlineDate='2027-01-20')
        with self.assertRaisesRegex(AssertionError, 'calendar-only abstract follows full paper'):
            validate_data(self.data)

    def test_rolling_does_not_silently_become_one_annual_deadline(self):
        self.track.update(abstractDeadline=None, fullDeadline=None,
                          abstractDeadlineDate=None, fullDeadlineDate='2027-01-20', deadlineMode='rolling')
        with self.assertRaisesRegex(AssertionError, 'rolling submission cannot claim'):
            validate_data(self.data)

    def test_duplicate_statistics_cannot_inflate_three_year_coverage(self):
        self.row['detail']['acceptance'].append(copy.deepcopy(self.row['detail']['acceptance'][0]))
        with self.assertRaisesRegex(AssertionError, 'duplicate acceptance year'):
            validate_data(self.data)

    def test_complete_audit_cannot_hide_documented_gaps(self):
        self.row['detailAudit'].update(status='complete', missingFields=['作者政策未核验'])
        with self.assertRaisesRegex(AssertionError, 'complete audit still has missing fields'):
            validate_data(self.data)

    def test_removing_known_awards_to_make_room_for_other_papers_is_rejected(self):
        row = next(c for c in self.data['conferences'] if (c.get('detail') or {}).get('bestPapers', {}).get('items'))
        target = row['detail']['bestPapers']['items'][0]['title'].casefold().strip()
        row['detail']['curatedPapers']['items'] = [p for p in row['detail']['curatedPapers']['items'] if p['title'].casefold().strip() != target]
        with self.assertRaisesRegex(AssertionError, 'Known award papers must be retained'):
            validate_data(self.data)


if __name__ == '__main__':
    unittest.main()
