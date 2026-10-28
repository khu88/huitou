#!/usr/bin/env python3
"""Merge locally verified evidence into the app snapshot; no network access."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / 'research' / name).read_text())


def normalized_detail(raw):
    d = copy.deepcopy(raw)
    d['year'] = d.pop('edition', d.get('year'))
    event = d.setdefault('event', {})
    event['source'] = event.get('source') or event.get('sourceUrl')
    event['additionalLocations'] = event.get('satellites', event.get('additionalLocations', []))
    if event.get('note'):
        d.setdefault('notes', []).append(event['note'])
    for track in d.get('tracks', []):
        track['fullDeadline'] = track.pop('paperDeadline', track.get('fullDeadline'))
        track.setdefault('abstractDeadline', None)
        if 'template' not in track:
            track['template'] = copy.deepcopy(d.get('template'))
        template = track.get('template')
        if template and template.get('status') in ['previous-year', 'previous-edition']:
            template['status'] = 'fallback'
        if 'AoE' in (track.get('timezone') or ''):
            track['timezone'] = 'AoE (UTC−12)'
        track.setdefault('sources', [track['cfpUrl']] if track.get('cfpUrl') else [])
        if track.get('commitmentDeadline'):
            # Keep this separate from the new-paper deadline; display explicitly.
            track['note'] = (track.get('note') or '') + ' Commitment 截止：' + track['commitmentDeadline']
    d['acceptance'] = d.pop('acceptanceHistory', d.get('acceptance', []))
    for row in d['acceptance']:
        row['scope'] = row.pop('track', row.get('scope'))
        row.setdefault('sources', [row['source']] if row.get('source') else [])
        row.pop('ratePercent', None)
        row.pop('percent', None)
    papers = d.get('bestPapers', {})
    if isinstance(papers, list):
        for p in papers:
            p['source'] = p.pop('sourceUrl', p.get('source'))
        d['bestPapers'] = {'year': d.get('bestPapersYear', 2025), 'items': papers[:10], 'source': papers[0].get('source') if papers else None, 'note': d.get('bestPapersNote')}
    d.setdefault('notes', [])
    return d


def build():
    catalog = read('ccf-catalog.json')
    records = catalog['conferences']
    n_records = read('n-conferences.json')['conferences']
    for c in n_records:
        c['inclusionReason'] = c.get('selectionReason')
    records += n_records
    comparison = read('conference-rankings.json')
    rankings = {row['id']: row['rankings'] for row in comparison['conferences']}
    if len(rankings) != len(comparison['conferences']) or set(rankings) != {c['id'] for c in records}:
        raise ValueError('Comparison rankings must cover the current conference catalog exactly once')
    for c in records:
        c['rankings'] = copy.deepcopy(rankings[c['id']])
    catalog['rankingSources'] = comparison['rankingSources']
    catalog['rankingCoverage'] = comparison['coverage']
    catalog['rankingMatchingPolicy'] = comparison['matchingPolicy']
    aliases = {'kdd': 'sigkdd', 'neurips': 'nips', 'www': 'www'}
    for filename in ['ai-details.json', 'other-details.json']:
        for raw in read(filename)['conferences']:
            target = aliases.get(raw['acronym'].lower(), raw['acronym'].lower())
            matches = [c for c in records if c['id'] == target or c['acronym'] and c['acronym'].lower() == raw['acronym'].lower()]
            if len(matches) != 1:
                raise ValueError(f'Ambiguous conference match: {raw["acronym"]}: {len(matches)}')
            c = matches[0]
            c['detail'] = normalized_detail(raw)
            c['officialUrl'] = raw['officialUrl']
            if raw['acronym'] == 'NeurIPS':
                c['aliases'] = list(set(c.get('aliases', []) + ['NeurIPS', 'NIPS']))
                c['acronym'] = 'NeurIPS'
    def match(acronym):
        target = aliases.get(acronym.lower(), acronym.lower())
        matches = [c for c in records if c['id'] == target or (c.get('acronym') or '').lower() == acronym.lower()]
        if len(matches) != 1:
            raise ValueError(f'Ambiguous correction match: {acronym}')
        return matches[0]

    revision = read('revision-dates-attendance.json')
    for correction in revision['corrections']:
        d = match(correction['acronym'])['detail']
        assert d['year'] == correction['year'], 'Correction must match the exact edition'
        if correction.get('event'):
            d['event'].update(correction['event'])
            if correction['event'].get('note'):
                d['notes'].append(correction['event']['note'])
            if correction.get('sources'):
                d['event']['source'] = correction['sources'][0]['url']
        for patch in correction.get('tracks', []):
            target = [t for t in d['tracks'] if t['name'] == patch['name']]
            assert len(target) == 1, f'Unknown track correction: {patch["name"]}'
            t = target[0]
            old_note, old_sources = t.get('note') or '', t.get('sources', [])
            t.update(patch)
            t['note'] = '\n'.join(filter(None, [old_note, patch.get('note')]))
            combined = old_sources + patch.get('sources', [])
            t['sources'] = list({(s if isinstance(s, str) else s['url']): s for s in combined}.values())
        d.setdefault('sources', []).extend(correction.get('sources', []))
        d.setdefault('correctionNotes', []).append(correction['reason'])
    for entry in revision['attendance']:
        match(entry['acronym'])['detail']['attendance'] = entry['years']
    curated = read('curated-papers.json')
    for entry in curated['conferences']:
        match(entry['acronym'])['detail']['curatedPapers'] = entry
    catalog['curatedPaperPolicy'] = curated['policy']
    catalog['auditNotes'] = revision['auditNotes']
    expanded_ids = set()
    for filename in sorted((ROOT / 'research' / 'expanded-details').glob('*.json')):
        shard = json.loads(filename.read_text())
        for entry in shard.get('conferences', []):
            cid = entry['id']
            if cid in expanded_ids:
                raise ValueError(f'Duplicate expanded detail: {cid}')
            expanded_ids.add(cid)
            matches = [c for c in records if c['id'] == cid]
            if len(matches) != 1 or matches[0]['areaId'] != filename.stem:
                raise ValueError(f'Invalid conference/area in {filename.name}: {cid}')
            c = matches[0]
            c['detailAudit'] = copy.deepcopy(entry['audit'])
            if entry.get('detail') is not None:
                c['detail'] = normalized_detail(entry['detail'])
                c['officialUrl'] = c['detail']['officialUrl']
    catalog['detailAuditCoverage'] = {
        'total': len(records), 'recorded': len(expanded_ids),
        'pending': sum(c.get('detailAudit', {}).get('status', 'pending') == 'pending' for c in records),
        'partial': sum(c.get('detailAudit', {}).get('status') == 'partial' for c in records),
        'unavailable': sum(c.get('detailAudit', {}).get('status') == 'unavailable' for c in records),
        'complete': sum(c.get('detailAudit', {}).get('status') == 'complete' for c in records),
    }
    for c in records:
        if not c.get('detail'):
            continue
        for i, t in enumerate(c['detail']['tracks']):
            # Preserve a deliberately selected primary track; default only when none is set.
            if not any(track.get('primary') for track in c['detail']['tracks']):
                t['primary'] = i == 0
            t.setdefault('primary', False)
            for key in ['abstract', 'full']:
                value = t.get(key + 'Deadline')
                if value:
                    t[key + 'Timezone'] = 'UTC' if value.endswith('Z') else ('AoE (UTC−12)' if value.endswith('-12:00') else 'UTC' + value[-6:])
    catalog['acceptanceWindow'] = [2023, 2024, 2025]
    catalog['bestPaperYear'] = 2025
    details = [c['detail'] for c in records if c.get('detail')]
    catalog['coverage'] = {
        'catalog': len(records) - len(n_records), 'unranked': len(n_records),
        'details': len(details), 'tracks': sum(len(d['tracks']) for d in details),
        'acceptanceRecords': sum(isinstance(r.get('accepted'), int) and isinstance(r.get('submitted'), int) for d in details for r in d['acceptance']),
        'bestPapers': sum(len(d['bestPapers']['items']) for d in details),
        'curatedPapers': sum(len(d.get('curatedPapers', {}).get('items', [])) for d in details),
        'eventDates': sum(bool(d.get('event', {}).get('start')) for d in details),
        'eventLocations': sum(bool(d.get('event', {}).get('location')) for d in details),
        'submissionLinks': sum(bool(t.get('submissionUrl')) for d in details for t in d['tracks']),
        'templateLinks': sum(bool((t.get('template') or {}).get('url')) for d in details for t in d['tracks']),
        'preciseDeadlines': sum(bool(t.get(k+'Deadline')) for d in details for t in d['tracks'] for k in ['abstract','full']),
        'dateOnlyDeadlines': sum(bool(t.get(k+'DeadlineDate')) and not t.get(k+'Deadline') for d in details for t in d['tracks'] for k in ['abstract','full']),
        'attendanceVerified': sum(r['status'] != 'unknown' for d in details for r in d.get('attendance', [])),
    }
    (ROOT / 'data').mkdir(exist_ok=True)
    target = ROOT / 'data' / 'conferences.json'
    target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(catalog['coverage'], ensure_ascii=False))
    print(f'Built {target}')


if __name__ == '__main__':
    build()
