"""Reproducibly extract factual conference rows from the CCF 2026 formal PDF.
Run with the Codex bundled Python (pdfplumber is already installed there).
No network calls; original PDF and provenance are retained in research/.
"""
from pathlib import Path
import re, json, hashlib
from collections import Counter
import pdfplumber

ROOT = Path(__file__).resolve().parent
PDF = ROOT / 'ccf-2026-official-catalog.pdf'
OFFICIAL = 'https://www.ccf.org.cn/Academic_Evaluation/By_category/'
PDF_URL = 'https://lib.zjgsu.edu.cn/_upload/article/files/f5/b1/f4f7201343b88c0f10564f590ebe/854a3c68-36a6-4698-a359-5184d5e30a0c.pdf'
AREAS = ['计算机体系结构/并行与分布计算/存储系统', '计算机网络', '网络与信息安全', '软件工程/系统软件/程序设计语言', '数据库/数据挖掘/内容检索', '计算机科学理论', '计算机图形学与多媒体', '人工智能', '人机交互与普适计算', '交叉/综合/新兴']
SLUGS = ['architecture','network','security','software','database','theory','graphics','ai','hci','interdisciplinary']
PATHS = ['ARCH_DCP_SS','CN','NIS','TCSE_SS_PDL','DM_CS','TCS','CGAndMT','AI','HCIAndPC','Cross_Compre_Emerging']

def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()

confs=[]; area=None; kind=None; rank=None; seq={}
with pdfplumber.open(PDF) as doc:
    for page_no,page in enumerate(doc.pages,1):
        tx=page.extract_text(x_tolerance=1) or ''
        compact=re.sub(r'\s+', '',tx)
        if '中国计算机学会推荐国际学术期刊' in compact: kind='journal'
        elif '中国计算机学会推荐国际学术会议' in compact and page_no>1: kind='conference'
        for a in AREAS:
            if a in compact: area=a
        m=re.search('[一二三]、([ABC])类',compact)
        if m: rank=m.group(1)
        if kind!='conference': continue
        assert area and rank
        for table in page.find_tables():
            for row in table.extract(x_tolerance=1):
                if not row or not (row[0] or '').strip().isdigit(): continue
                assert len(row)==5, (page_no,row)
                n,abbr,name,publisher,url=map(clean,row)
                n=int(n); key=(area,rank)
                assert n==seq.get(key,0)+1, (page_no,key,n,seq.get(key))
                seq[key]=n
                # PDF line wraps / historical aliases are normalized without changing identity.
                abbr=abbr.replace('SIG- METRICS','SIGMETRICS').replace('CODES+ ISSS','CODES+ISSS').replace('INTER- SPEECH','INTERSPEECH')
                aliases=[]
                # Repair missing spaces caused by source typesetting; retain original below.
                source_name=name
                name=name.replace('EngineeringLanguages','Engineering Languages').replace('ACMSIGPLAN','ACM SIGPLAN').replace('onComputer','on Computer').replace('Human- Computer','Human-Computer')
                m=re.search(r'（原\s*(.*?)）',abbr)
                if m:
                    aliases.append(m.group(1)); abbr=abbr[:m.start()].strip()
                url=re.sub(r'\s+','',url)
                idx=AREAS.index(area)
                id_=re.sub(r'[^a-z0-9]+','-',(abbr or name).lower()).strip('-')
                confs.append(dict(id=id_, acronym=abbr, name=name, sourceName=source_name, displayName=abbr or name, rank=rank, area=area, areaId=SLUGS[idx], publisher=publisher, officialUrl=None, catalogUrl=url or None, ccfSource=OFFICIAL, ccfCategorySource=f'https://www.ccf.org.cn/Academic_Evaluation/{PATHS[idx]}/', sourcePdf=PDF_URL, sourcePage=page_no, aliases=aliases))

# Ensure one record per unambiguous conference identifier.
ids=Counter(c['id'] for c in confs)
for c in confs:
    if ids[c['id']]>1: c['id'] += '-' + c['areaId']
assert len({c['id'] for c in confs}) == len(confs)
out = dict(version='CCF 第七版（2026）',publishedAt='2026-03-31',errataAt='2026-04-09',asOf='2026-10-28',
    scope='CCF 官方 10 个学科的全部会议条目；不含期刊。',
    rankScope='CCF 目录会议分级适用于正式发表的 Full paper / Regular paper；Short、Demo、Technical Brief、Summary、Findings 与伴随 Workshop 不计入目录考虑范围。',
    provenanceNote='正式版 CCF 原始 PDF，经浙江工商大学图书馆公开镜像取得；CCF 发布页可通过搜索索引核验，但直接抓取遇到访问验证。该 PDF 与独立 GitHub 镜像字节一致。',
    sourceSha256=hashlib.sha256(PDF.read_bytes()).hexdigest(),
    sources=[dict(label='CCF 第七版正式发布及 4 月 9 日勘误说明',url=OFFICIAL),dict(label='浙江工商大学图书馆转载页',url='https://lib.zjgsu.edu.cn/2026/0414/c1056a221631/page.htm'),dict(label='CCF 正式目录 PDF（大学图书馆镜像）',url=PDF_URL)],
    areas=[dict(id=s,name=a) for s,a in zip(SLUGS,AREAS)],
    conferences=confs)
(ROOT/'ccf-catalog.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print('TOTAL',len(confs),'RANKS',dict(Counter(c['rank'] for c in confs)))
for a in AREAS: print(a,dict(Counter(c['rank'] for c in confs if c['area']==a)))
print('ALL CONFERENCES:')
for c in confs: print(c['sourcePage'],c['rank'],c['acronym'],':',c['name'])
