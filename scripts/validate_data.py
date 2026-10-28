#!/usr/bin/env python3
"""Validate the local evidence snapshot without fetching or inferring missing data."""
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RANKING_SYSTEMS = ('core', 'thcpl')
RANKING_STATUSES = ('verified', 'listed-unranked', 'unconfirmed')
RANKING_VALUES = {
    'core': ('A*', 'A', 'B', 'C', 'Australasian B', 'Australasian C'),
    'thcpl': ('A', 'B'),
}


def http_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ('http', 'https') and bool(parsed.hostname)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_rankings(data):
    """Keep a sourced rating distinct from an unverified or unranked entry."""
    sources = data.get('rankingSources')
    assert isinstance(sources, dict), 'rankingSources metadata missing'
    for system in RANKING_SYSTEMS:
        metadata = sources.get(system)
        assert isinstance(metadata, dict), f'{system}: source metadata missing'
        assert nonempty(metadata.get('version')), f'{system}: source version missing'
        assert http_url(metadata.get('source')), f'{system}: invalid official source URL'
        assert nonempty(metadata.get('sourceLabel')), f'{system}: source label missing'
    counts = Counter()
    for conference in data['conferences']:
        rankings = conference.get('rankings')
        assert isinstance(rankings, dict), f'{conference["id"]}: rankings missing'
        for system in RANKING_SYSTEMS:
            prefix = f'{conference["id"]}/{system}'
            entry = rankings.get(system)
            assert isinstance(entry, dict), f'{prefix}: ranking entry missing'
            status = entry.get('status')
            assert status in RANKING_STATUSES, f'{prefix}: invalid ranking status'
            assert entry.get('version') == sources[system]['version'], f'{prefix}: ranking version differs from source metadata'
            assert http_url(entry.get('source')), f'{prefix}: invalid source URL'
            assert urlparse(entry['source']).hostname == urlparse(sources[system]['source']).hostname, f'{prefix}: source does not belong to the recorded publisher'
            assert nonempty(entry.get('sourceLabel')), f'{prefix}: source label missing'
            assert isinstance(entry.get('note'), str), f'{prefix}: ranking note must be explicit'
            if status != 'verified':
                assert nonempty(entry['note']), f'{prefix}: unknown/unranked state explanation missing'
            verified_at = entry.get('verifiedAt')
            assert isinstance(verified_at, str), f'{prefix}: verification date missing'
            try:
                verified_date = date.fromisoformat(verified_at)
            except ValueError as error:
                raise AssertionError(f'{prefix}: invalid verification date') from error
            assert verified_date <= date.fromisoformat(data['asOf']), f'{prefix}: verification is newer than the snapshot'
            if status == 'verified':
                assert entry.get('rank') in RANKING_VALUES[system], f'{prefix}: invalid verified rank'
                if 'sourceRank' in entry:
                    assert entry['sourceRank'] == entry['rank'], f'{prefix}: rank differs from the recorded source rank'
            else:
                assert entry.get('rank') is None, f'{prefix}: unknown/unranked entries must not claim a rank'
            if status == 'listed-unranked':
                assert nonempty(entry.get('sourceRank')), f'{prefix}: official unranked wording missing'
                assert entry['sourceRank'] not in RANKING_VALUES[system], f'{prefix}: a graded source row cannot be labelled unranked'
            if status != 'unconfirmed':
                assert nonempty(entry.get('sourceTitle')), f'{prefix}: matched official title missing'
                assert nonempty(entry.get('matchMethod')), f'{prefix}: matching basis missing'
                if system == 'core':
                    assert nonempty(entry.get('sourceRecordId')), f'{prefix}: official record ID missing'
                else:
                    assert type(entry.get('sourcePage')) is int and 1 <= entry['sourcePage'] <= 17, f'{prefix}: official PDF page missing or out of range'
            counts[system + {'verified': 'Verified', 'listed-unranked': 'ListedUnranked', 'unconfirmed': 'Unconfirmed'}[status]] += 1
    return counts


def check_urls(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and (k.lower().endswith('url') or k in ['sourcePdf', 'ccfSource', 'catalogUrl']) and v:
                assert urlparse(v).scheme in ['http', 'https'], (k, v)
            check_urls(v)
    elif isinstance(obj, list):
        for v in obj:
            check_urls(v)


def validate_data(data):
    rows = data['conferences']
    assert len({r['id'] for r in rows}) == len(rows), 'Duplicate conference ID'
    assert Counter(r['rank'] for r in rows) == {'A': 58, 'B': 132, 'C': 196, 'N': 4}
    assert len(data['areas']) == 10
    assert data['acceptanceWindow'] == [2023, 2024, 2025]
    assert data['bestPaperYear'] == 2025
    counts = Counter()
    counts['catalog'] = sum(r['rank'] != 'N' for r in rows)
    counts['unranked'] = sum(r['rank'] == 'N' for r in rows)
    for r in rows:
        assert r['name'] and r['areaId'] in {a['id'] for a in data['areas']}
        if r['rank'] != 'N':
            assert r['sourcePage'] and r['sourcePdf'] and r['ccfSource']
        else:
            assert r['inclusionReason'] and r['sources'] and r['ccfMatchChecked']
        audit = r.get('detailAudit')
        if audit:
            assert audit.get('status') in ['pending','partial','unavailable','complete'], f'{r["id"]}: invalid audit status'
            assert isinstance(audit.get('missingFields', []), list)
            if audit.get('checkedAt'):
                assert date.fromisoformat(audit['checkedAt']) <= date.fromisoformat(data['asOf'])
            else:
                assert audit['status'] == 'pending', f'{r["id"]}: reviewed record requires checkedAt'
        if not r.get('detail'):
            assert not audit or audit['status'] != 'complete', f'{r["id"]}: complete audit requires edition details'
            continue
        d = r['detail']; counts['details'] += 1
        assert isinstance(d['year'], int) and d['officialUrl'] and d['verifiedDate']
        event = d.get('event', {})
        for key in ('start', 'end'):
            if event.get(key):
                assert date.fromisoformat(event[key]).isoformat() == event[key], f'{r["id"]}: invalid event date'
        if event.get('start') and event.get('end'):
            assert event['start'] <= event['end'], f'{r["id"]}: reversed event range'
        counts['eventDates'] += bool(event.get('start'))
        counts['eventLocations'] += bool(event.get('location'))
        for t in d['tracks']:
            counts['tracks'] += 1
            counts['submissionLinks'] += bool(t.get('submissionUrl'))
            counts['templateLinks'] += bool((t.get('template') or {}).get('url'))
            dates = {}
            for field in ['abstractDeadline', 'fullDeadline']:
                if t.get(field):
                    dates[field] = datetime.fromisoformat(t[field].replace('Z', '+00:00'))
                    assert dates[field].tzinfo, f'{r["id"]}: timezone missing'
                    assert t['sources'] and t['timezone']
                    counts['deadlines'] += 1
                    counts['preciseDeadlines'] += 1
            if len(dates) == 2:
                assert dates['abstractDeadline'] <= dates['fullDeadline']
            for field in ['abstractDeadlineDate', 'fullDeadlineDate']:
                if t.get(field):
                    assert date.fromisoformat(t[field]).isoformat() == t[field], f'{r["id"]}: invalid calendar-only deadline'
                    assert t.get('sources'), f'{r["id"]}: calendar-only deadline requires a source'
                    if t.get(field[:-4]):
                        assert t[field] == t[field[:-4]][:10], f'{r["id"]}: calendar day contradicts timestamp'
                    if not t.get(field[:-4]):
                        counts['dateOnlyDeadlines'] += 1
            if t.get('abstractDeadlineDate') and t.get('fullDeadlineDate'):
                assert t['abstractDeadlineDate'] <= t['fullDeadlineDate'], f'{r["id"]}: calendar-only abstract follows full paper'
            if t.get('deadlineMode') == 'rolling':
                assert not (t.get('fullDeadline') or t.get('fullDeadlineDate')) and t.get('sources'), f'{r["id"]}: rolling submission cannot claim a single full-paper deadline'
            tm = t.get('template')
            if tm and tm.get('status') == 'fallback':
                assert isinstance(tm['year'], int) and tm['year'] < d['year']
        assert len({a['year'] for a in d['acceptance']}) == len(d['acceptance']), f'{r["id"]}: duplicate acceptance year'
        for a in d['acceptance']:
            assert a['year'] in data['acceptanceWindow']
            if a.get('accepted') is None or a.get('submitted') is None:
                continue
            assert type(a['accepted']) is int and type(a['submitted']) is int
            assert 0 <= a['accepted'] <= a['submitted'] and a['submitted'] > 0
            assert a['sources'] and a['scope']
            counts['acceptanceRecords'] += 1
        assert sum(bool(t.get('primary', False)) for t in d['tracks']) == (1 if d['tracks'] else 0), f'{r["id"]}: exactly one known track must be primary'
        assert len({a['year'] for a in d.get('attendance', [])}) == len(d.get('attendance', [])), f'{r["id"]}: duplicate attendance year'
        for policy in d.get('attendance', []):
            assert policy['year'] in data['acceptanceWindow']
            assert policy['status'] in ['required', 'remote-allowed', 'conditional', 'not-held', 'unknown']
            assert policy['summary'] and policy['scope']
            if policy['status'] != 'unknown':
                assert policy['sources']
                counts['attendanceVerified'] += 1
        curated = d.get('curatedPapers', {}).get('items', [])
        assert len(curated) <= 10
        assert len({p['title'].casefold() for p in curated}) == len(curated)
        for p in curated:
            assert p['title'] and p['url'] and p['award'] and p['source'] and p['topic']
            counts['curatedPapers'] += 1
        known_best = d['bestPapers']['items']
        if known_best and len(known_best) <= 10:
            names = {p['title'].casefold().strip() for p in curated}
            assert all(p['title'].casefold().strip() in names for p in known_best), 'Known award papers must be retained'
        b = d['bestPapers']
        assert b['year'] == 2025 and len(b['items']) <= 10
        for p in b['items']:
            assert p['title'] and p['url'] and p['award'] and (p.get('source') or b.get('source'))
            counts['bestPapers'] += 1
        if audit and audit['status'] == 'complete':
            assert not audit.get('missingFields'), f'{r["id"]}: complete audit still has missing fields'
            assert event.get('start') and event.get('end') and event.get('location') and d['tracks'], f'{r["id"]}: complete audit lacks event or tracks'
            assert len(d['acceptance']) == 3 and all(type(a.get('accepted')) is int and type(a.get('submitted')) is int for a in d['acceptance']), f'{r["id"]}: complete audit lacks historical statistics'
            assert len(d.get('attendance', [])) == 3 and all(a['status'] != 'unknown' for a in d['attendance']), f'{r["id"]}: complete audit lacks attendance policies'
            assert curated, f'{r["id"]}: complete audit lacks curated papers'
    check_urls(data)
    for k in ['catalog', 'unranked', 'details', 'tracks', 'acceptanceRecords', 'bestPapers', 'curatedPapers', 'attendanceVerified',
              'eventDates', 'eventLocations', 'submissionLinks', 'templateLinks', 'preciseDeadlines', 'dateOnlyDeadlines']:
        assert counts[k] == data['coverage'][k], (k, counts[k], data['coverage'][k])
    if data.get('detailAuditCoverage'):
        audits = Counter(c.get('detailAudit', {}).get('status') for c in rows if c.get('detailAudit'))
        assert data['detailAuditCoverage']['total'] == len(rows)
        assert data['detailAuditCoverage']['recorded'] == sum(audits.values())
        for status in ('pending', 'partial', 'unavailable', 'complete'):
            assert data['detailAuditCoverage'][status] == audits[status], f'audit coverage mismatch: {status}'
    # UTC−12 is twenty hours behind Singapore: Nov 16 23:59 AoE = Nov 17 19:59 UTC+8.
    test = datetime.fromisoformat('2026-11-16T23:59:00-12:00').astimezone(timezone(timedelta(hours=8)))
    assert test.isoformat() == '2026-11-17T19:59:00+08:00'

    www = next(c for c in rows if c['id'] == 'www')['detail']
    assert www['event']['start'] == '2027-05-12'
    demo = next(t for t in www['tracks'] if t['name'] == 'Demo Papers')
    assert demo['fullDeadline'] == '2026-11-15T21:00:00Z' and demo['deadlineConflict']
    assert demo['fullTimezone'] == 'UTC'
    short = next(t for t in www['tracks'] if t['name'] == 'Short Papers')
    assert short['abstractTimezone'] == 'UTC' and short['fullTimezone'] == 'AoE (UTC−12)'
    counts.update(validate_rankings(data))
    return counts


def main():
    data = json.loads((ROOT / 'data' / 'conferences.json').read_text())
    counts = validate_data(data)
    print('PASS: directory counts/IDs, dates/timezones, source fields, acceptance integers/scopes, awards, coverage, WWW corrections, and sourced CORE/TH-CPL rankings')
    print(json.dumps(dict(counts), ensure_ascii=False))


if __name__ == '__main__':
    main()
