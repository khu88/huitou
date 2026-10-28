#!/usr/bin/env python3
"""Build versioned comparison rankings from saved official sources, offline.

The default build uses only the Python standard library. Pass --extract-thcpl
with an existing pypdf environment to regenerate the PDF text and conference
rows. No command downloads files or installs dependencies.
"""
import argparse
import collections
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research'
SOURCES = RESEARCH / 'sources'
CHECKED_AT = '2026-10-28'
CORE_URL = 'https://portal.core.edu.au/conf-ranks/'
CORE_EXPORT = CORE_URL + '?search=&by=all&source=ICORE2026&sort=atitle&page=1&do=Export'
TH_URL = 'https://numbda.cs.tsinghua.edu.cn/~yuwj/TH-CPL.pdf'
CORE_RANKS = {'A*', 'A', 'B', 'C', 'Australasian B', 'Australasian C'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_title(value):
    # Deliberately conservative: no fuzzy match and no acronym-only inference.
    return re.sub(r'[^a-z0-9]', '', value.lower().replace('&', 'and'))


def extract_thcpl():
    from pypdf import PdfReader
    reader = PdfReader(SOURCES / 'th-cpl-2019-08-13.pdf')
    assert len(reader.pages) == 17
    contents = '\n'.join(f'PAGE {i + 1}\n' + page.extract_text(extraction_mode='layout')
                         for i, page in enumerate(reader.pages))
    (SOURCES / 'th-cpl-2019-08-13.txt').write_text(contents, encoding='utf-8')
    rows = []
    page, rank, area, current, active = 0, None, None, None, False
    for line in contents.splitlines():
        if line.startswith('PAGE '):
            page = int(line[5:])
            continue
        if re.match(r'^\s*（[一二三四五六七八九十]+）', line):
            area, current = line.strip(), None
            continue
        heading = re.match(r'^\s*\d+[.．]\s*([AB])\s*类(会议|期刊)', line)
        if heading:
            rank, active, current = heading[1], heading[2] == '会议', None
            continue
        if not active or not line.strip() or re.match(r'^\s*\d+\s*$', line) or '序号' in line:
            continue
        row = re.match(r'^\s*(\d+)\s{2,}(.+?)\s*$', line)
        if row:
            cells = re.split(r'\s{3,}', row[2])
            assert len(cells) <= 2, f'Unexpected table cells on page {page}: {cells}'
            current = {'id': f'thcpl-p{page}-{rank}-{row[1]}', 'rank': rank,
                       'page': page, 'area': area, 'number': int(row[1]),
                       'title': cells[0], 'acronym': cells[1] if len(cells) > 1 else ''}
            rows.append(current)
        elif current:
            current['title'] += ' ' + line.strip()
        else:
            raise ValueError(f'Unrecognized conference content on page {page}: {line}')
    # Count only conference tables, not the adjacent journal tables.
    assert collections.Counter(row['rank'] for row in rows) == {'A': 77, 'B': 148}
    assert len({row['id'] for row in rows}) == len(rows)
    write(SOURCES / 'th-cpl-2019-08-13-conferences.json', rows)


def build():
    conferences = (read(RESEARCH / 'ccf-catalog.json')['conferences'] +
                   read(RESEARCH / 'n-conferences.json')['conferences'])
    reviewed = read(RESEARCH / 'ranking-matches-reviewed.json')['matches']
    core = []
    with (SOURCES / 'core-icore2026.csv').open(encoding='utf-8', newline='') as stream:
        for row in csv.reader(stream):
            assert len(row) == 9 and row[3] == 'ICORE2026', 'Unexpected CORE export schema/version'
            core.append({'id': row[0], 'title': row[1].strip(), 'acronym': row[2],
                         'rank': row[4], 'fieldsOfResearch': [v for v in row[6:] if v]})
    assert len(core) == 987 and len({r['id'] for r in core}) == 987
    assert sum(r['rank'] in CORE_RANKS for r in core) == 825
    thcpl = read(SOURCES / 'th-cpl-2019-08-13-conferences.json')
    assert len(thcpl) == 225 and all(r['rank'] in {'A', 'B'} for r in thcpl)
    sources = {
        'core': {
            'version': 'ICORE2026', 'source': CORE_URL, 'sourceLabel': 'CORE / ICORE · ICORE2026',
            'verifiedAt': CHECKED_AT, 'exportUrl': CORE_EXPORT,
            'snapshot': 'research/sources/core-icore2026.csv',
            'sha256': digest(SOURCES / 'core-icore2026.csv'),
            'recordCount': 987, 'rankedRecordCount': 825,
            'note': '读取 ICORE 官方门户的 ICORE2026 导出。不同评价体系不可直接等同；其他状态按官方原文保留。',
        },
        'thcpl': {
            'version': '2019-08-13', 'source': TH_URL,
            'sourceLabel': '清华 TH-CPL · 2019-08-13', 'verifiedAt': CHECKED_AT,
            'snapshot': 'research/sources/th-cpl-2019-08-13.pdf',
            'sha256': digest(SOURCES / 'th-cpl-2019-08-13.pdf'),
            'extractedSnapshot': 'research/sources/th-cpl-2019-08-13-conferences.json',
            'extractedSha256': digest(SOURCES / 'th-cpl-2019-08-13-conferences.json'),
            'recordCount': 225, 'rankedRecordCount': 225, 'pageCount': 17,
            'note': '清华大学官方域名公开 PDF；封面注明 2019-08-13 会议通过，只提取 A/B 类会议，排除期刊。不声称这是最新版本。',
        },
    }
    output = []
    for c in conferences:
        result = {'id': c['id'], 'rankings': {}}
        for key, rows in [('core', core), ('thcpl', thcpl)]:
            meta = sources[key]
            entry = {field: meta[field] for field in ('version', 'source', 'sourceLabel', 'verifiedAt')}
            entry.update(rank=None, status='unconfirmed',
                         note='本次版本中未完成可靠匹配；不表示官方未评级或未收录。')
            titles = {normalized_title(c['name']), normalized_title(c.get('sourceName', ''))} - {''}
            matches = [row for row in rows if normalized_title(row['title']) in titles]
            method, reason = 'normalized-title', '与目录全称规范化后唯一一致（忽略大小写、标点及 &/and）。'
            review = reviewed[key].get(c['id'])
            if review:
                assert review['catalogTitle'] == c['name'], f'Stale catalog match: {c["id"]}'
                matches = [row for row in rows if row['id'] == review['sourceRecordId']]
                assert len(matches) == 1 and matches[0]['title'] == review['sourceTitle'], f'Stale source match: {c["id"]}'
                method, reason = 'reviewed-name-and-acronym', review['reason']
            if len(matches) == 1:
                row = matches[0]
                ranked = key == 'thcpl' or row['rank'] in CORE_RANKS
                entry.update(rank=row['rank'] if ranked else None,
                             status='verified' if ranked else 'listed-unranked',
                             sourceRank=row['rank'], sourceTitle=row['title'], sourceAcronym=row['acronym'],
                             sourceRecordId=row['id'], matchMethod=method, matchNote=reason,
                             note='' if ranked else f'官方此版本标注为“{row["rank"]}”，未给出 A*/A/B/C 字母分级。')
                if key == 'core':
                    entry['source'] = f'{CORE_URL}{row["id"]}/'
                    entry['fieldsOfResearch'] = row['fieldsOfResearch']
                else:
                    entry['sourcePage'] = row['page']
                    entry['sourceArea'] = row['area']
                    if c['id'] == 'icws':
                        entry['scope'] = 'Research Track'
                        entry['note'] = 'TH-CPL 2019 原条目限定 Research Track，不扩大为所有投稿轨道。'
                    if c['id'] == 'cade':
                        entry['note'] = '原目录将 CADE/IJCAR 合并列为 B 类；此处对应 CADE。'
                if c['id'] == 'acm-sigops-atc':
                    entry['note'] = '此版本按历史名称 USENIX ATC 收录；当前 CCF 目录使用 ACM SIGOPS ATC。'
            result['rankings'][key] = entry
        output.append(result)
    assert len({c['id'] for c in output}) == len(output) == 390
    coverage = {key: dict(collections.Counter(c['rankings'][key]['status'] for c in output))
                for key in sources}
    document = {
        'schemaVersion': 1, 'asOf': CHECKED_AT, 'rankingSources': sources,
        'matchingPolicy': '全称规范化唯一匹配，或人工复核全称与简称/历史别名后按来源ID匹配；不使用 CCF 等级推算，简称碰撞与无可靠对应均保留未确认。',
        'coverage': coverage, 'conferences': output,
    }
    write(RESEARCH / 'conference-rankings.json', document)
    print(json.dumps(coverage, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract-thcpl', action='store_true')
    args = parser.parse_args()
    if args.extract_thcpl:
        extract_thcpl()
    build()
