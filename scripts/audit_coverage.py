#!/usr/bin/env python3
"""Write an offline field-level coverage report, distinct from catalog coverage."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def audit(data):
    rows=[]
    totals=Counter()
    for c in data['conferences']:
        d=c.get('detail') or {}
        tracks=d.get('tracks',[])
        acceptance={a['year'] for a in d.get('acceptance',[]) if type(a.get('accepted')) is int and type(a.get('submitted')) is int}
        attendance={a['year'] for a in d.get('attendance',[]) if a.get('status')!='unknown'}
        papers=d.get('curatedPapers',{}).get('items',[])
        missing=[]
        if not d:missing.append('verified-edition')
        if not d.get('event',{}).get('start') or not d.get('event',{}).get('end'):missing.append('event-dates')
        if not d.get('event',{}).get('location'):missing.append('event-location')
        if not tracks:missing.append('independent-submission-tracks')
        for y in data['acceptanceWindow']:
            if y not in acceptance:missing.append('acceptance-'+str(y))
            if y not in attendance:missing.append('attendance-'+str(y))
        if not papers:missing.append('curated-papers-2025')
        track_gaps=[]
        for t in tracks:
            fields=[]
            if not t.get('submissionUrl'):fields.append('submission-url')
            if not (t.get('template') or {}).get('url'):fields.append('template-or-format')
            if not any(t.get(k) for k in ['abstractDeadline','fullDeadline','abstractDeadlineDate','fullDeadlineDate','deadlineMode']):
                fields.append('submission-dates')
            elif not (t.get('abstractDeadline') or t.get('fullDeadline')) and t.get('deadlineMode')!='rolling':
                fields.append('exact-time-or-timezone')
            if fields:track_gaps.append({'track':t['name'],'fields':fields})
        if len(acceptance)==3:totals['allThreeAcceptanceYears']+=1
        if len(attendance)==3:totals['allThreeAttendanceYears']+=1
        if papers:totals['conferencesWithCuratedPapers']+=1
        fallback_links=sum(p.get('linkType') in ('award-list','program-entry') for p in papers)
        totals['curatedPapersWithIndependentLinks']+=len(papers)-fallback_links
        totals['curatedPapersUsingAwardOrProgramLinks']+=fallback_links
        event_end=d.get('event',{}).get('end')
        historical=bool(event_end and event_end<data['asOf'])
        if historical:totals['verifiedEditionAlreadyEnded']+=1
        rows.append({'id':c['id'],'acronym':c.get('acronym'),'areaId':c['areaId'],
                     'auditStatus':c.get('detailAudit',{}).get('status','pending'),
                     'edition':d.get('year'),'editionAlreadyEnded':historical,
                     'acceptanceYears':sorted(acceptance),'attendanceYears':sorted(attendance),
                     'curatedPaperCount':len(papers),'curatedPaperLinkGaps':fallback_links,'missingFields':missing,'trackGaps':track_gaps})
    return {'asOf':data['asOf'],'note':'字段覆盖报告，不代表有值数据已经实时更新；缺失可能为未公布、未取得证据或尚待专题核验。轨道列表不保证穷尽。',
            'catalogCount':len(rows),'coverage':data['coverage'],'auditCoverage':data.get('detailAuditCoverage'),
            'fieldCoverage':dict(totals),'conferences':rows}

if __name__=='__main__':
    report=audit(json.loads((ROOT/'data/conferences.json').read_text()))
    target=ROOT/'research/data-quality-report.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['fieldCoverage'],ensure_ascii=False))
    print('Wrote',target)
