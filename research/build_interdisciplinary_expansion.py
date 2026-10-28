#!/usr/bin/env python3
"""Reproduce the manually checked interdisciplinary edition records.

Only facts read in the saved official evidence are entered below. Empty historical
fields describe research still to do, never a claim that the organizers omit them.
"""
import json
import re
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'research/evidence/interdisciplinary'
ASOF = '2026-10-28'
rows = []

def evidence(name):
    return json.loads((EVIDENCE / (name + '.json')).read_text())

def url(name):
    d = evidence(name)
    return d.get('url', d['requestedUrl'])

def sources(*names):
    return [{'url': url(n), 'label': '官方资料 · ' + n} for n in names]

def template(link, year=2026, status='current', note='本届官方投稿说明指定的格式。'):
    return dict(url=link, year=year, status=status, note=note)

def track(name, source, full=None, abstract=None, submission=None, tm=None, zone=None, note='', **extra):
    t = dict(name=name, abstractDeadline=None, fullDeadline=None, timezone=zone,
             submissionUrl=submission, submissionInfoUrl=url(source), template=tm,
             sources=sources(source), note=note)
    for kind, value in [('full', full), ('abstract', abstract)]:
        if value:
            t[kind + ('Deadline' if 'T' in value else 'DeadlineDate')] = value
    t.update(extra)
    return t

def add(id, year, home, start, end, location, tracks=(), note='', extra_sources=()):
    tracks = list(tracks)
    for i, t in enumerate(tracks): t['primary'] = i == 0
    missing = ['2023–2025 逐年录用分子/分母与口径待专题核验',
               '2023–2025 作者参会要求待查各届政策',
               '2025 Best/Outstanding 及 Oral/Spotlight 论文待专题核验']
    if not tracks: missing.append('本届 Track、投稿入口、模板、截止日期未公布或待核验')
    elif any(not t.get('fullDeadline') for t in tracks): missing.append('部分投稿节点缺准确时刻/时区或尚未公布')
    if any(not t.get('submissionUrl') for t in tracks): missing.append('部分投稿系统专用入口待核验')
    if any(not t.get('template') for t in tracks): missing.append('部分 Track 模板待核验')
    src = sources(home, *extra_sources)
    detail = dict(year=year, officialUrl=url(home), event=dict(start=start, end=end, location=location, source=url(home)),
        tracks=tracks, acceptance=[dict(year=y, accepted=None, submitted=None, scope='主会论文；精确统计口径待核验', sources=[], note='历史统计专题尚未完成，未采用第三方百分比反推分子分母。') for y in (2023,2024,2025)],
        attendance=[dict(year=y, status='unknown', summary='该届作者参会政策待专题核验；不从会议城市或 hybrid 标签推断必须线下。', scope='论文作者展示要求', sources=[], verifiedDate=ASOF) for y in (2023,2024,2025)],
        bestPapers=dict(year=2025, items=[], source=None, note='2025 奖项专题尚未完成；空列表不表示未设奖。'),
        curatedPapers=dict(year=2025, items=[], sources=[], selectionNote='待核验 2025 官方获奖及 Oral/Spotlight 名单，最多 10 篇，不用普通录用文章凑数。'),
        verifiedDate=ASOF, notes=[note] if note else [], sources=src)
    rows.append(dict(id=id, detail=detail, audit=dict(checkedAt=ASOF, status='partial', officialSources=src, missingFields=missing,
        note='本轮已核验届次及以下官方投稿资料；历史统计、参会要求和论文精选另行核验。' + note)))
    return detail

ieee = 'https://www.ieee.org/conferences/publishing/templates.html'
lncs = 'https://www.springer.com/gp/computer-science/lncs/conference-proceedings-guidelines'
acm = 'http://www.acm.org/publications/proceedings-template'
aoe = 'AoE (UTC−12)'

add('rtss',2026,'rtss-home','2026-12-09','2026-12-11','Yokohama, Japan',[
    track('Main Papers','rtss-dates','2026-05-26','2026-05-21','https://rtss26.hotcrp.com/',template(ieee),aoe,
          '官方仅给日历日期和 AoE；未给时刻，不生成倒计时。'),
    track('Brief Presentations','rtss-dates','2026-09-14',zone=aoe),
    track('RTSS@Work Demos','rtss-dates','2026-09-30',zone=aoe)],
    '主会 12 月 9–11 日，12 月 8 日为 Hot Topics Day。',('rtss-dates','rtss-submit'))
add('cogsci',2027,'cogsci-2027','2027-07-28','2027-07-31','Bilbao, Spain · Euskalduna Conference Centre',
    note='官方已公布 2027 会期地点；本轮页面尚无可核验的 2027 CFP 和截止日期。')
add('recomb',2027,'recomb-home','2027-05-17','2027-05-20','Toronto, Canada',[
    track('Research Papers','recomb-cfp','2026-11-04T23:59:00-12:00','2026-10-28T23:59:00-12:00',
          'https://easychair.org/conferences/?conf=recomb2027',template(url('recomb-cfp'),2027,'not-required',
          '官方无强制模板：正文 10 页、Letter、至少 10pt、1 英寸边距；LNCS 可选。'),aoe)],
    '5 月 15–16 日为卫星会议，主会为 5 月 17–20 日。',('recomb-cfp',))
add('ismb',2027,'ismb-home','2027-07-18','2027-07-22','Copenhagen, Denmark · Bella Center',[
    track('Proceedings Papers','ismb-proceedings','2027-01-14T23:59:00-12:00',submission='https://easychair.org/conferences/?conf=ismbeccb2027',
          tm=template('https://academic.oup.com/bioinformatics/pages/author-guidelines#Manuscript%20Prep',2027,note='本届指定 OUP Bioinformatics 格式，最多 9 页。'),zone=aoe,
          note='官方原文为 January 14, 2027, 11:59 PM in the time zone of your choice；以最后时区 UTC−12 表达。')],extra_sources=('ismb-proceedings',))
add('miccai',2027,'miccai-society','2027-09-26','2027-10-01','Auckland, New Zealand',
    note='MICCAI 学会 Upcoming Conferences 页面已列会期；投稿截止明确为 TBA。',extra_sources=('miccai-home',))
add('wine',2026,'wine-home','2026-12-01','2026-12-04','Hong Kong, China · University of Hong Kong',[
    track('Research Papers','wine-home','2026-07-02',submission='https://wine26.hotcrp.com/',
          tm=template('https://www.springer.com/cn/computer-science/lncs/conference-proceedings-guidelines',note='初投 LNCS 可选；正文至多 12 页（不含标题页和参考文献），录用稿采用 LNCS。'),zone=aoe)])
add('emsoft',2026,'emsoft-home','2026-10-04','2026-10-09','Barcelona, Spain · ESWEEK',[
    track('Journal Track (IEEE TCAD)','emsoft-home','2026-03-30','2026-03-23','https://emsoft26.hotcrp.com/',
          template('https://ieee-ceda.org/publications/tcad/tcad-paper-submissions',note='本届 Journal Track 使用 IEEE TCAD 双栏格式，初投总共不超过 12 页。'),aoe),
    track('Late Breaking Track (IEEE ESL)','emsoft-home','2026-06-05',submission='https://emsoft26.hotcrp.com/',zone=aoe)],
    '日期为联合 ESWEEK 整体活动范围；Journal Track 与 Late Breaking 分别发表于 TCAD 与 ESL，不能混为同一录用率。',('emsoft-follow-2','emsoft-follow-5'))
add('aft',2026,'aft-home','2026-10-07','2026-10-09','London, UK · London School of Economics',[
    track('Research / SoK Papers','aft-follow-1','2026-05-27','2026-05-20','https://crypto.unibe.ch/aft26/',
          template('https://submission.dagstuhl.de/series/details/LIPIcs#author'),aoe)],
    '官网总体 10 月 6–9 日包含 10 月 6 日 workshop；主会 10 月 7–9 日。',('aft-follow-1',))
add('ieee-bigdata',2026,'bigdata-home','2026-12-14','2026-12-17','Phoenix, AZ, USA · Sheraton Phoenix Downtown',[
    track('Research Papers','bigdata-follow-2','2026-08-21',submission='https://wi-lab.com/cyberchair/2026/bigdata26/index.php',tm=template(ieee))],extra_sources=('bigdata-follow-1','bigdata-follow-2'))
add('bibm',2026,'bibm-official','2026-12-01','2026-12-04','Dallas, TX, USA',[
    track('Research Papers','bibm-cfp','2026-07-05',submission='https://wi-lab.com/cyberchair/2026/bibm26/index.php',
          tm=template('http://www.ieee.org/conferences_events/conferences/publishing/templates.html')),
    track('Posters (initial 1-page submission)','bibm-poster','2026-10-28T23:59:59-12:00',
          submission='https://wi-lab.com/cyberchair/2026/bibm26/scripts/submit.php?subarea=P',tm=template(ieee,note='初投 1 页 Poster Paper 使用 IEEE 模板为可选；录用后 3 页稿为另一阶段。'),zone=aoe)],
    '主站使用嵌入页面，已读取其指向的 Stony Brook 官方内容；Poster 截止独立于主会研究论文。',('bibm-cfp','bibm-poster'))
add('ieee-cloud',2026,'cloud-home','2026-07-13','2026-07-18','Sydney, Australia · IEEE SERVICES',[
    track('Regular Papers','cloud-follow-1','2026-03-22',submission='https://easychair.org/conferences/?conf=ieeecloud2026',tm=template(ieee),
          note='采用 CFP 明确的 extended and firm 截止。')],
    '会期为联合 IEEE SERVICES 范围；官方投稿链接 conf 参数末尾包含编码空格，已移除该空白。',('cloud-follow-1','cloud-author'))
add('isbra',2026,'isbra-home','2026-07-22','2026-07-24','Macau, China',[
    track('Track 1 · LNBI Proceedings & Special Issues','isbra-follow-1','2026-03-22',submission='https://easychair.org/conferences/?conf=isbra2026',tm=template(lncs)),
    track('Track 2 · Presentation & Special Issues','isbra-follow-1','2026-03-22',submission='https://easychair.org/conferences/?conf=isbra2026',tm=template(lncs))],extra_sources=('isbra-follow-1',))
add('cosit',2026,'cosit-home','2026-09-22','2026-09-25','York, UK · The Hospitium',[
    track('Full Papers','cosit-home','2026-02-27',tm=template('https://www.dagstuhl.de/en/publications/lipics/instructions-for-authors'),zone=aoe),
    track('Short Papers','cosit-home','2026-04-30',tm=template('https://www.dagstuhl.de/en/publications/lipics/instructions-for-authors'),zone=aoe)],
    '采用官方 Important Dates 中延后的最终日期。页面未提供可确认的独立投稿系统链接；期刊/图书报告的邮箱不当作主论文系统。')
add('sagt',2026,'sagt-home','2026-09-15','2026-09-18','Augsburg, Germany · University of Augsburg',[
    track('Research Papers','sagt-home','2026-05-26','2026-05-20',tm=template(lncs),zone=aoe,
          note='官网说明使用 EasyChair，但当前正文仅显示 Submission is closed，未保留专用链接。'),
    track('Posters','sagt-home','2026-09-07',note='通过官网所列组织方邮箱提交；非主会 Research 截止。')])
add('icss',2026,'icss-cfp','2026-05-15','2026-05-17','Macau, China · Macau University of Science and Technology',[
    track('Full / Short Papers','icss-cfp',submission='https://easychair.org/conferences/?conf=icss2026',tm=template(lncs,note='本届采用 Springer CCIS 格式：Full 12–15 页，Short 6–11 页。'))],
    '此条目是 CCF Service Science 会议，不是同缩写的 INFORMS ICSS；CFP 提到摘要先于全文一周但未给具体日期，不反推。')
add('ijtcs-faw',2026,'ijtcs-home','2026-11-07','2026-11-10','Beijing, China · Renmin University of China',[
    track('Regular Papers','ijtcs-submit','2026-09-07',submission='https://openreview.net/group?id=IJTCS-FAW/2026/Conference',tm=template(lncs,note='初投鼓励 LNCS，不强制；录用稿采用 LNCS。'),zone=aoe),
    track('WINE / ISAAC Fast Track','ijtcs-submit','2026-09-15',submission='https://openreview.net/group?id=IJTCS-FAW/2026/Conference',tm=template(lncs),zone=aoe,
          note='仅适用于 WINE 2026 / ISAAC 2026 未录用论文，须附原评审与回复。'),
    track('Posters','ijtcs-submit','2026-10-29',note='通过官网所列邮箱投稿，不与 OpenReview 常规投稿混用。')],
    '会期采用官网 10 月 28 日更新后的 11 月 7–10 日；OpenReview 旧会期标签不同。',('ijtcs-submit',))
mlsys = add('mlsys',2027,'mlsys-home','2027-06-21','2027-06-25','Bellevue, WA, USA',[
    track('Research Papers','mlsys-cfp','2026-10-30T20:00:00Z',submission='https://openreview.net/group?id=MLSys.org/2027/Conference',
          tm=template('https://media.mlsys.org/Conferences/MLSYS2025/mlsys2025style.zip',2025,'fallback','2027 CFP 明确继续使用 2025 模板。'),zone='UTC',
          note='采用公开 OpenReview Submission invitation 的 duedate，与 CFP 20:00 UTC 一致；官网首页 12 PM PDT 等于 19:00 UTC，存在一小时差异。expdate 20:30 UTC 不是截止。',
          deadlineConflict=True, announcedFullDeadline='2026-10-30T20:00:00Z', deadlineSourceLabel='投稿系统公开 duedate 与 CFP 一致；首页时区换算有冲突')],extra_sources=('mlsys-cfp',))
mlsys['tracks'][0]['sources'].insert(0, dict(url=evidence('mlsys-openreview-submission')['url'], label='OpenReview Submission invitation 原始 duedate'))
industry = json.loads(json.dumps(mlsys['tracks'][0]));industry.update(name='Industrial Track', primary=False)
industry['note'] += ' Industrial Track 使用同一入口，提交表单中选择 Track。'
mlsys['tracks'].append(industry)

sig_tracks=[]
for n, name, absday, fullday, portal in [
    (1,'Research Papers','05-29','06-05','acmsigspatial2026'),
    (3,'Vision Papers','06-05','06-12','acmsigspatial2026vis'),
    (4,'Applications Papers','06-12','06-19','sigspatial2026app'),
    (5,'Industrial Papers','06-12','06-19','sigspatial26industri'),
    (6,'Short Papers','06-16','06-19','acmsigspatial2026sho'),
    (8,'Demos',None,'07-06','sigspatial2026demo')]:
    sig_tracks.append(track(name,'sigspatial-extra-'+str(n),'2026-'+fullday+'T23:59:00-07:00',
        '2026-'+absday+'T23:59:00-07:00' if absday else None,'https://easychair.org/conferences/?conf='+portal,
        template(acm), 'Pacific Daylight Time (UTC−7)','采用本 Track CFP 最后延期日期；夏季 Pacific Time 为 UTC−7。'))
add('sigspatial',2026,'sigspatial-home','2026-11-04','2026-11-06','Riverside, California, USA · Riverside Convention Center',sig_tracks,
    '主会 11 月 4–6 日；11 月 3 日为 Workshops，整体活动 11 月 3–6 日。')
smc_tm=template('https://www.ieeesmc2025.org/files/content/test-files/IEEE-ConfPaper-Template-LaTeX.zip',2025,'fallback','2026 官方 CFP 仍指向 2025 站点提供的模板。')
add('smc',2026,'smc-home','2026-10-04','2026-10-07','Bellevue, WA, USA',[
    track('Regular / Special Session / Workshop Papers','smc-follow-2','2026-05-03',submission='https://conf.papercept.net/conferences/scripts/start.pl',tm=smc_tm),
    track('Work-in-Progress / Industry Papers','smc-follow-2','2026-05-17',submission='https://conf.papercept.net/conferences/scripts/start.pl',tm=smc_tm),
    track('Journal Presentation-only','smc-follow-2','2026-05-31',submission='https://conf.papercept.net/conferences/scripts/start.pl'),
    track('Two-page Abstracts','smc-follow-2','2026-07-12',submission='https://conf.papercept.net/conferences/scripts/start.pl')],
    '8 月 9 日延期公告针对 final/camera-ready 和注册，不作为新稿截止。',('smc-follow-1','smc-follow-3'))

# The three remaining editions use the same official, bounded evidence contract.
add('icic',2027,'icic-home','2027-07-24','2027-07-28','Jinan, Shandong, China',
    note='本届主页面已公布会期地点；已检查嵌入的 Important Dates，正文暂无日期；CFP 页面当前返回服务端错误，不据此猜测截止。',extra_sources=('icic-menu','icic-important','icic-cfp'))
add('apbc',2026,'apbc-home','2026-10-21','2026-10-24','Hsinchu, Taiwan · National Yang Ming Chiao Tung University',[
    track('Full Papers','apbc-dates','2026-07-17',note='采用官方 FINAL EXTENSION 日期；模板和提交控件未在可读取正文中返回有效 URL，请通过官方 CFP 查看。'),
    track('Poster Abstracts','apbc-poster',abstract='2026-09-30',note='官方 Poster Call 公告延期至 9 月 30 日；不假定具体时刻/时区。')],extra_sources=('apbc-cfp','apbc-poster','apbc-dates'))

# AMIA's direct fetch returns 403, but the same official page is readable through
# web search. Store a small structured source extract instead of inventing a fetch.
amia_url='https://amia.org/education-events/amia-2026-annual-symposium/call-participation'
(EVIDENCE/'amia-web-cfp.json').write_text(json.dumps(dict(requestedUrl=amia_url,url=amia_url,checkedAt=ASOF,
    method='public web page read; direct urllib returned 403',facts=dict(event='November 7–11, 2026; Dallas, TX',
    manuscriptDeadline='March 10, 2026',tracks=['Paper','Student Paper','Podium Abstract','Poster','Panel','Informatics Debate','Systems Demonstration','Tutorials','Collaborative Workshop'],
    templateSection='File Format Requirements; official template download linked on the CFP')),ensure_ascii=False,indent=2)+'\n')
add('amia',2026,'amia-web-cfp','2026-11-07','2026-11-11','Dallas, Texas, USA',[
    track('Papers / Student Papers','amia-web-cfp','2026-03-10',tm=template(amia_url,note='请使用本届 CFP 的 Download the template 链接；正文 5–10 页。'))],
    '本地直接抓取返回 403，已通过公开网页读取官方 CFP；只记录已确认的 manuscript 截止。')

rows.append(dict(id='www',detail=None,audit=dict(checkedAt=ASOF,status='partial',officialSources=sources('www-home'),
    missingFields=['2023 录用分子/分母待核验','2025 作者线下参会政策待核验','2025 Oral/Spotlight 补充名单待核验'],
    note='保留此前已逐 Track 核验的 WWW 2027 CFP、OpenReview 冲突、2024–2025 录用率和 Best Paper；不以本轮空值覆盖。')))
assert len(rows)==23 and len({r['id'] for r in rows})==23

# Integer pairs transcribed from official proceedings/report passages, with scope
# preserved. Repository aggregates are discovery leads, never the cited evidence.
def stat(id, year, accepted, submitted, source, scope, note=''):
    row=next(r for r in rows if r['id']==id)
    item=next(a for a in row['detail']['acceptance'] if a['year']==year)
    item.update(accepted=accepted,submitted=submitted,scope=scope,note=note,sources=sources(source))

for y,a,n in [(2023,31,100),(2024,30,106),(2025,35,135)]:
    stat('aft',y,a,n,f'aft-preface-{y}','主会论文 · LIPIcs 官方前言')
for y,a,n in [(2023,44,188),(2024,57,352),(2025,55,339)]:
    stat('recomb',y,a,n,f'recomb-stats-{y}','主会 Research 投稿选中论文（含作者选择以短摘要发表的论文）',
         '不含单独 Highlights Track；短摘要是发表方式选择，不以短稿篇数替代研究论文录用口径。')
for y,a,n in [(2023,730,2250),(2024,857,2781),(2025,1027,3447)]:
    stat('miccai',y,a,n,f'miccai-stats-{y}','主会 Full Papers · Springer 官方论文集概述')
for y,a,n in [(2023,66,221),(2024,66,248),(2025,67,225)]:
    stat('wine',y,a,n,f'wine-stats-{y}','主会 Research 投稿选中论文 · Springer 前言',
         '按录用决定统计；作者可选择全文或一页摘要发表，不按论文集实际全文数反推录用数。')
for y,a,n in [(2024,93,236),(2025,66,167)]:
    stat('isbra',y,a,n,f'isbra-stats-{y}','投稿中选为论文集 Full Publication 的论文 · Springer 前言')
stat('emsoft',2023,21,90,'emsoft-stats-2023','Journal Track，不含 LB / WiP',
     '主席报告给出 21/90，但文中括号误写 21%；本站按整数计算 23.33%。')
stat('emsoft',2025,27,100,'emsoft-stats-2025','Journal Track，不含 LB / WiP',
     'IEEE CEDA 2025 年 10 月报告第 99 页；166 是摘要注册数，117 是跨 Track 合计，均不作此分母。')
stat('sigspatial',2023,38,189,'sigspatial-stats-2023','Research 与 Systems/Industrial 合并 · Full 10-page Papers',
     'ACM SIGSPATIAL 官方年报仅给这两类合并分母；明确保留合并口径，不声称为单独 Research Track。')
for y,a,n in [(2023,60,336),(2024,58,318),(2025,67,395)]:
    stat('ismb',y,a,n,f'ismb-editorial-{y}','Proceedings Track · 全部全文投稿',
         '2025 有 371 篇符合规则进入评审，采用全部 395 篇投稿为分母；67 篇最终录用中有 1 篇在录用后主动撤回。' if y==2025 else '')

def papers(id, source, entries, note):
    row=next(r for r in rows if r['id']==id);items=[]
    for title,link,award,topic in entries:
        items.append(dict(title=title,url=link,award=award,topic=topic,source=url(source),presentationType='best'))
    assert len(items)<=10
    row['detail']['bestPapers']=dict(year=2025,items=items,source=url(source),note=note)
    row['detail']['curatedPapers']=dict(year=2025,items=items,sources=sources(source),selectionNote=note)
    row['audit']['missingFields']=[s for s in row['audit']['missingFields'] if not s.startswith('2025 Best/')]
    row['audit']['missingFields'].append('2025 Oral/Spotlight 跨主题补充待核验；已保留已知主奖论文')

wine_links={l['label']:l['url'] for page in ('wine-book-2025','wine-book-2025-page2','wine-book-2025-page3') for l in evidence(page).get('links',[])}
wine_papers=[]
for title,award,topic in [
    ('The Limits of Interval-Regulated Price Discrimination','Best Paper','价格歧视与市场机制'),
    ('Degree-Bounded Online Bipartite Matching: OCS vs. Ranking','Best Student Paper','在线算法与二分匹配'),
    ('Improved Budget-Feasible Mechanisms for Submodular Valuations: Beating 4 Deterministically in Linear Time','Outstanding Paper','预算可行机制与次模优化'),
    ('Constant Inapproximability of Pacing Equilibria in Second-Price Auctions','Outstanding Paper','拍卖均衡与计算复杂性'),
    ('Bounds on the Revenue Gap of Linear Posted Pricing for Selling a Divisible Item','Outstanding Paper','定价与收入界')]:
    wine_papers.append((title,wine_links[title],award,topic))
papers('wine','wine-stats-2025',wine_papers,'官方论文集前言核实 1 篇 Best、1 篇 Best Student、3 篇 Outstanding；覆盖匹配、机制、拍卖、定价等主题，未用普通录用稿补足十篇。')
recomb_links=evidence('recomb-awards')['links']
papers('recomb','recomb-awards',[
    ('ralphi: a deep reinforcement learning framework for haplotype assembly',next(l['url'] for l in recomb_links if 'ralphi:' in l['label']),'Best Paper','基因组单倍型组装与强化学习'),
    ('TarDis: Achieving Robust and Structured Disentanglement of Multiple Covariates',next(l['url'] for l in recomb_links if 'TarDis:' in l['label']),'Best Student / Young Scientist Paper','生物数据表征与协变量解耦')],
    'RECOMB 系列官网确认 2025 主奖与学生/青年科学家论文奖。Test of Time 和 Best Poster 不混入主会 Best Paper。')
papers('miccai','miccai-awards',[
    ('Fit Pixels, Get Labels: Meta-Learned Implicit Networks for Image Segmentation','https://papers.miccai.org/miccai-2025/0340-Paper3113.html','Best Paper','元学习与隐式神经表示'),
    ('Multifrequency Neural Network-based Wave Inversion in MR Elastography','https://papers.miccai.org/miccai-2025/0599-Paper3156.html','Best Paper Runner-up','磁共振弹性成像与逆问题'),
    ('Learning Segmentation from Radiology Reports','https://papers.miccai.org/miccai-2025/0488-Paper0049.html','Best Paper Runner-up','医学文本监督与肿瘤分割')],
    '学会官方主奖名单的获奖论文与两篇 Runner-up 均保留，明确区分奖项等级；论文链接使用学会开放获取版本。其他 Young Scientist / Oral 名单继续核验。')
papers('rtss','rtss-awards-2025',[
    ('Requirement-Based Analysis of Self-Suspending Tasks under EDF','https://doi.org/10.1109/RTSS66672.2025.00049','Best Paper / Outstanding Paper','实时调度与自挂起任务'),
    ('WCDFP Analysis for Real-Time Tasks with Stochastic Release Patterns using Chernoff Bound','https://doi.org/10.1109/RTSS66672.2025.00051','Best Student Paper / Outstanding Paper','随机实时任务与概率分析'),
    ('LEFT-RS: A Lock-Free Fault-Tolerant Resource Sharing Protocol for Multicore Real-Time Systems','https://doi.org/10.1109/RTSS66672.2025.00050','Outstanding Paper','多核容错与资源共享'),
    ('LeMix: Unified Scheduling for LLM Training and Inference on Multi-GPU Systems','https://doi.org/10.1109/RTSS66672.2025.00052','Outstanding Paper','大模型训练推理调度')],
    '官网 Awards 核实四篇 Outstanding，其中两篇同时获得 Best / Best Student；去重保留最高奖项，论文 DOI 取自官方 Program。')
next(r for r in rows if r['id']=='rtss')['detail']['curatedPapers']['sources']+=sources('rtss-program-2025')

# Award names are supplied by the official accepted-papers page's image title
# attributes, which plain text extraction alone omits. Match them to the official
# proceedings links; no ordinary accepted papers are promoted to award winners.
mlsys_links={l['label']:l['url'] for l in evidence('mlsys-proceedings-2025')['links']}
mlsys_topics=['机器学习系统资源冗余','大模型推理注意力算子','大模型重分片推理',
              '低内存优化器','虚拟机分配与预测','混合架构前缀缓存','混合专家通信计算重叠']
mlsys_awards=[]
for row_html, topic in zip(evidence('mlsys-award-rows-2025')['rows'], mlsys_topics):
    title=unescape(re.search(r'<strong>(.*?)</strong>',row_html,re.S).group(1)).strip()
    award=unescape(re.search(r'<img title="([^"]+)"',row_html).group(1))
    mlsys_awards.append((title,mlsys_links[title],award,topic))
assert len(mlsys_awards)==7
papers('mlsys','mlsys-accepted-2025',mlsys_awards,
       '官方 Accepted Papers 的奖章说明确认 2 篇 Outstanding Paper Award 和 5 篇 Honorable Mention；分别标注，全部保留，覆盖系统资源、训练优化与推理等主题。')
mlsys['curatedPapers']['sources']+=sources('mlsys-proceedings-2025')

papers('ieee-cloud','cloud-archive-2025-follow1',[
    ('Dynamic In-node Group-aware Scheduling for Multi-tenant Machine Learning Services on Kubernetes',
     'https://doi.org/10.1109/CLOUD67622.2025.00017','Best Paper','多租户机器学习服务与容器调度'),
    ('Helm-ET: Reducing Exposure to Lateral Movement in Kubernetes Artifacts',
     'https://doi.org/10.1109/CLOUD67622.2025.00021','Best Student Paper','Kubernetes 网络隔离与云安全')],
    'IEEE SERVICES 官方奖项页中 CLOUD 的 Best Paper 与 Best Student Paper 均保留；不混入同页 ICWS / EDGE 等其他会议奖项。')

papers('cogsci','cogsci-archive-2025',[
    ('Wild Possibilities: Evidence of Modal Cognition in Free-Ranging Rhesus Macaques (Macaca mulatta)',
     'https://repositories.cdlib.org/uc/item/2n33k1ks','Marr Prize · Best Student Paper','非人灵长类的可能性推理'),
    ('AIPsychoBench: Understanding the Psychometric Differences between LLMs and Humans',
     'https://escholarship.org/uc/item/39k8f46q','Diversity & Social Inequality Award','大模型与人类心理测量'),
    ('A Normative Model of Delay Discounting Across the Lifespan: Tradeoffs Between Mortality, Fertility, and Parenting',
     'https://escholarship.org/uc/item/59x0r7x8','Disciplinary Diversity & Integration Award','跨期决策与生命周期建模'),
    ('Visual moral inference and communication',
     'https://escholarship.org/uc/item/2wn1n4rn','Disciplinary Diversity & Integration Award','视觉道德推断与多模态传播'),
    ('Emotion influences behavioral outcomes and attention during goal-directed reading',
     'https://escholarship.org/uc/item/3sr2t2zc','Sayan Gul Award','情绪、注意力与阅读理解')],
    '保留已核验的 Marr 最佳学生论文及官方逐题列出的其他论文奖，题名和独立地址对应学会 eScholarship 论文集。计算建模四个领域奖只公开获奖作者，本轮未完成论文题名匹配；不是完整获奖名单。学位论文奖、个人终身成就奖及参会资助不当作论文奖。')
next(r for r in rows if r['id']=='cogsci')['audit']['missingFields'].append('2025 四个 Computational Modeling Prizes 的论文题名与链接待核验')
cloud2025=next(a for r in rows if r['id']=='ieee-cloud' for a in r['detail']['acceptance'] if a['year']==2025)
cloud2025.update(sources=sources('cloud-program-2025'),note='官方2025总程序册第7页仅公布 CLOUD 28.15%，未给该会议整数分子分母；700是六个联办会议合计投稿数，不能作CLOUD分母。')

def policy(id, year, status, source, summary, scope='主会论文作者展示要求'):
    row=next(r for r in rows if r['id']==id)
    target=next(a for a in row['detail']['attendance'] if a['year']==year)
    target.update(status=status,summary=summary,scope=scope,sources=sources(source),verifiedDate=ASOF)

for y in (2023,2024,2025):
    policy('aft',y,'conditional',f'aft-archive-{y}-follow0',
           'CFP 要求至少一位作者注册；如为线下会议，应到场报告，可直接向程序主席询问例外安排。')
    policy('ismb',y,'conditional',f'ismb-archive-{y}-extra36',
           '强烈优先线下报告；产育、照护、疾病/残障、经济困难或签证等情况可申请远程豁免，须在录用确认时向组织方申请。')
    policy('isbra',y,'unknown',f'isbra-archive-{y}' if y==2024 else f'isbra-archive-{y}-follow0',
           '已检查该届 CFP：至少一位作者须注册并报告，但未明确说明必须线下还是允许远程；不将注册要求等同于到场要求。')
policy('ieee-cloud',2023,'remote-allowed','cloud-archive-2023-follow1',
       '作者可选择现场或虚拟注册，均须按完整作者费率注册并现场或线上直播报告。','IEEE SERVICES 旗下 CLOUD 作者注册及展示')
policy('ieee-cloud',2024,'remote-allowed','cloud-archive-2024-follow0',
       '官方明确可现场、远程或录播展示；每篇须作者注册，远程作者没有单独优惠费率。','IEEE SERVICES 旗下 CLOUD 作者注册及展示')
policy('ieee-cloud',2025,'conditional','cloud-archive-2025-extra16',
       '无法按计划到场时允许远程展示，须提前准备录播备份；未获批准的不展示会导致论文从论文集移除。','IEEE SERVICES 旗下 CLOUD 作者展示政策')
policy('miccai',2023,'unknown','miccai-archive-2023-follow0',
       '该届 CFP 称为 hybrid 并强调线下参与，但该段未明确论文作者远程展示条件；尚不能断言作者必须到场。')
for y in (2024,2025):
    policy('miccai',y,'conditional',f'miccai-archive-{y}-follow3',
           '录用论文须由注册作者现场报告；缺少差旅经费或不愿出行不是豁免理由，突发紧急情况须向程序委员会申请豁免。')
policy('emsoft',2024,'conditional','emsoft-archive-2024-extra132',
       '以当届 Speaker Instructions 为准：通常现场；无法取得美国签证者须事先获主席批准，远程使用预录视频，不能视频连线直播报告。')
policy('rtss',2025,'conditional','rtss-archive-2025-follow2',
       '尽可能由作者到场报告；不展示不入论文集，不接受预录视频。所有作者签证受阻等特殊情况须联系程序主席另行安排。')
for y in (2024,2025):
    policy('sigspatial',y,'required',f'sigspatial-archive-{y}-follow0',
           '每篇论文须单独作者注册，并至少一位作者现场报告；否则不进入会议论文集和 ACM Digital Library。')
policy('wine',2023,'conditional','wine-archive-2023-follow1',
       '注册作者须现场报告；如全体作者均不能到场，官网建议安排代理报告。')
for y in (2023,2024):
    policy('mlsys',y,'unknown',f'mlsys-archive-{y}',
           '官网明确本届仅线下、不支持 hybrid/virtual attendance；尚未进一步核验作者不出席时的发表规则或例外，先保留未知。')
for y in (2023,2024):
    policy('cogsci',y,'unknown',f'cogsci-archive-{y}',
           ('官网说明本届 fully hybrid，但作者远程展示具体规则仍待核验。' if y==2023 else '官网说明本届为线下会议，但作者是否有远程豁免未在已读页面明确。'))

for row in rows:
    if row['detail']:
        confirmed=[a['year'] for a in row['detail']['acceptance'] if a.get('accepted') is not None]
        if confirmed:
            missing=[str(y) for y in (2023,2024,2025) if y not in confirmed]
            row['audit']['missingFields']=[s for s in row['audit']['missingFields'] if not s.startswith('2023–2025 逐年录用')]
            if missing:row['audit']['missingFields'].append('、'.join(missing)+' 录用分子/分母尚待核验')
            row['audit']['note']+=' 已补 '+ '、'.join(map(str,confirmed))+' 官方整数录用统计。'
        attendance= row['detail']['attendance']
        if any(a['status']!='unknown' for a in attendance):
            row['audit']['missingFields']=[s for s in row['audit']['missingFields'] if not s.startswith('2023–2025 作者参会')]
            unresolved=[str(a['year']) for a in attendance if a['status']=='unknown']
            if unresolved:row['audit']['missingFields'].append('、'.join(unresolved)+' 作者线下/远程展示要求仍未核实')
target=ROOT/'research/expanded-details/interdisciplinary.json'
target.write_text(json.dumps(dict(asOf=ASOF,conferences=rows),ensure_ascii=False,indent=2)+'\n')
print('Wrote',len(rows),'audited interdisciplinary records:',target)
