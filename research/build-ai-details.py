import json
from pathlib import Path
D='2026-10-28'
def source(url,label='会议官方资料'):return {'label':label,'url':url,'verifiedDate':D}
def deadline(date):return date+'T23:59:00-12:00' if date else None
def track(id,name,abstract,paper,submit,cfp,note='',**extra):return dict(id=id,name=name,abstractDeadline=deadline(abstract),paperDeadline=deadline(paper),timezone='UTC-12 (AoE)',submissionUrl=submit,cfpUrl=cfp,note=note,sources=[source(cfp)],**extra)
def acc(y,a,n,url,note,rate=None):return dict(year=y,accepted=a,submitted=n,ratePercent=round(a/n*100,2) if a is not None and n else rate,track='Main / Research',note=note,sources=[source(url,'官方统计 / 论文集前言')] if url else [],verifiedDate=D)
def base(acronym,year,url,start,end,location,cfp):return dict(acronym=acronym,edition=year,officialUrl=url,event={'start':start,'end':end,'location':location,'sourceUrl':url},tracks=[],template=None,acceptanceHistory=[acc(y,None,None,None,'尚未核验原始投稿数与录用数。') for y in [2023,2024,2025]],bestPapersYear=2025,bestPapers=[],bestPapersNote='仅收录已核验的 Best / Outstanding Paper；不混入 Test of Time。',sources=[source(url),source(cfp,'官方 CFP')],verifiedDate=D)
def template(url,year,status,sourceUrl,note=''):return dict(url=url,year=year,status=status,sourceUrl=sourceUrl,note=note)
def paper(title,url,award,src):return dict(title=title,url=url,award=award,year=2025,sourceUrl=src)
C=[]
u='https://aaai.org/conference/aaai/aaai-27/';cfp=u+'main-technical-track-call/'
x=base('AAAI',2027,u,'2027-02-16','2027-02-23','Montréal, Canada',cfp)
x['tracks']=[track('main','Main Technical Track','2026-07-21','2026-07-28','https://openreview.net/group?id=AAAI.org/2027/Conference',cfp),track('aisi','AI for Social Impact','2026-07-21','2026-07-28','https://openreview.net/group?id=AAAI.org/2027/Conference',u+'aisi-call/'),track('alignment','AI Alignment','2026-08-14','2026-08-21','https://openreview.net/group?id=AAAI.org/2027/Conference',u+'aia-call/','此 Track 的截止日期不同于主赛道；时区沿用大会统一 AoE 约定。')]
x['template']=template('https://aaai.org/authorkit27/',2027,'current',cfp,'官网已链接 AAAI-27 Author Kit；抓取工具访问此下载入口返回 403，未验证压缩包内容。')
a='https://aaai.org/about-aaai/aaai-awards/aaai-conference-paper-awards-and-recognition/'
x['bestPapers']=[paper(t,'https://ojs.aaai.org/index.php/AAAI/article/view/'+i,'Outstanding Paper',a) for t,i in [('Every Bit Helps: Achieving the Optimal Distortion with a Few Queries','33507'),('Efficient Rectification of Neuro-Symbolic Reasoning Inconsistencies by Abductive Reflection','33905'),('Revelations: A Decidable Class of POMDPs with Omega-Regular Objectives','34845')]]
C.append(x)
u='https://2027.aclweb.org/';cfp=u+'calls/main/'
x=base('ACL',2027,u,'2027-08-17','2027-08-22','Kyoto, Japan',cfp)
x['event']['note']='主会 8 月 20–22 日；Tutorials 8 月 17 日；Workshops 8 月 18–19 日。'
x['tracks']=[track('main','Main Conference · Long / Short',None,'2027-01-04',None,cfp,'先提交 ARR，再 commitment 至 ACL。Commitment 日期与 2027 提交入口尚未公布；官网当前 ARR 链接指向 2026，请从 ARR 官方页面核对。',submissionInfoUrl='https://aclrollingreview.org/cfp',commitmentDeadline=None),track('theme','Theme · Homogenization and knowledge collapse in LLMs',None,'2027-01-04',None,cfp,'与主会共同通过 ARR 提交。',submissionInfoUrl='https://aclrollingreview.org/cfp')]
x['template']=template('https://github.com/acl-org/acl-style-files',None,'rolling','https://aclrollingreview.org/cfp','ARR 官方指定的通用 ACL 模板，持续更新，无单独年度版本。')
x['acceptanceHistory']=[acc(2023,1074,4864,'https://aclanthology.org/2023.acl-long.0.pdf','主会长短文合计；含直接投稿及 ARR commitment；不含 Findings、TACL/CL。'),acc(2024,940,4407,'https://aclanthology.org/2024.acl-long.0.pdf','按官方论文集前言：主会长短文；分母为官方 ARR 口径，非仅 commitment 数；不含 Findings。'),acc(2025,1699,8360,'https://aclanthology.org/2025.acl-long.0.pdf','按 Program Chairs 前言：主会长短文；分母为 2024 年 12 月与 2025 年 2 月 ARR 的 unique submissions；不含 Findings。')]
a='https://2025.aclweb.org/program/awards/'
x['bestPapers']=[paper(t,'https://aclanthology.org/2025.acl-long.'+i+'/', 'Best Paper',a) for t,i in [('A Theory of Response Sampling in LLMs: Part Descriptive and Part Prescriptive','1454'),('Fairness through Difference Awareness: Measuring Desired Group Discrimination in LLMs','341'),('Language Models Resist Alignment: Evidence From Data Compression','1141'),('Native Sparse Attention: Hardware-Aligned and Natively Trainable Sparse Attention','1126')]]
C.append(x)
u='https://2026.emnlp.org/';cfp=u+'calls/main_conference_papers/'
x=base('EMNLP',2026,u,'2026-10-24','2026-10-29','Budapest, Hungary',cfp)
x['tracks']=[track('main','Main Conference · Long / Short',None,'2026-05-25','https://openreview.net/group?id=aclweb.org/ACL/ARR/2026/May',cfp,'需先 ARR 投稿，再 commitment；不得把 commitment 当成新论文提交截止。',commitmentDeadline=deadline('2026-08-02'),commitmentUrl='https://openreview.net/group?id=aclweb.org/EMNLP/2026/Conference'),track('industry','Industry Track',None,'2026-06-16',None,u+'calls/industry_track/','独立投稿入口见 CFP。')]
x['template']=template('https://github.com/acl-org/acl-style-files',None,'rolling','https://aclrollingreview.org/cfp','ARR 官方通用 ACL 模板，无单独年度版本。')
x['acceptanceHistory']=[acc(2023,1047,4909,'https://aclanthology.org/2023.emnlp-main.0.pdf','主会长短文；含 ARR commitment；不含 Findings、TACL/CL、Industry 与 Demo。'),acc(2024,1271,6105,'https://aclanthology.org/2024.emnlp-main.0.pdf','主会决定时录用数；分母排除 70 篇未获 3 份评审即撤稿及 220 篇 desk reject；3 篇后续撤稿未从此录用数扣除。'),acc(2025,1811,8174,'https://aclanthology.org/2025.emnlp-main.0.pdf','主会长短文；分母含 778 篇未获 3 份评审即撤稿及 670 篇 desk reject，与 2024 口径不同；不含 Findings。')]
a='https://2025.emnlp.org/program/awards/'
x['bestPapers']=[paper('Infini-gram mini: Exact n-gram Search at the Internet Scale with FM-Index','https://aclanthology.org/2025.emnlp-main.1268/','Best Paper',a)]
C.append(x)
u='https://neurips.cc/Conferences/2026';cfp=u+'/CallForPapers'
x=base('NeurIPS',2026,u,'2026-12-06','2026-12-12','Sydney, Australia · 主会',cfp)
x['event']['satellites']=[{'location':'Atlanta, USA','start':'2026-12-09','end':'2026-12-13'},{'location':'Paris, France','start':'2026-12-09','end':'2026-12-13'}]
x['event']['note']='Sydney 主会 12/6–12；Atlanta 与 Paris 卫星会 12/9–13。'
x['tracks']=[track('main','Main Track','2026-05-04','2026-05-06','https://openreview.net/group?id=NeurIPS.cc/2026/Conference',cfp),track('evaluations','Evaluations & Datasets','2026-05-04','2026-05-06',None,u+'/CallForEvaluationsDatasets','2026 更名自 Datasets & Benchmarks；独立投稿入口见 CFP。'),track('position','Position Papers','2026-05-04','2026-05-06','https://openreview.net/group?id=NeurIPS.cc/2026/Position_Paper_Track',u+'/CallForPositionPapers')]
x['template']=template('https://media.neurips.cc/Conferences/NeurIPS2026/Formatting_Instructions_For_NeurIPS_2026.zip',2026,'current',cfp)
x['acceptanceHistory']=[acc(2023,3218,12343,'https://media.neurips.cc/Conferences/NeurIPS2023/NeurIPS2023-Fact_Sheet.pdf','官方 Fact Sheet 主赛道；不含 Datasets & Benchmarks。'),acc(2024,4037,15671,'https://media.neurips.cc/Conferences/NeurIPS2024/NeurIPS2024-Fact_Sheet.pdf','官方 Fact Sheet 主赛道统计；不含 Datasets & Benchmarks。'),acc(2025,5290,21575,'https://blog.neurips.cc/2025/09/30/reflections-on-the-2025-review-process-from-the-program-committee-chairs/','主赛道有效投稿 valid submissions；不含 Datasets & Benchmarks / Position。')]
a='https://blog.neurips.cc/2025/11/26/announcing-the-neurips-2025-best-paper-awards/'
links=json.loads(Path('research/ai-links.json').read_text())
x['bestPapers']=[paper(p['title'],p['url'],'Best Paper · Datasets & Benchmarks' if i==0 else 'Best Paper',a) for i,p in enumerate(links['neurips_awards'][:4])]
C.append(x)
u='https://iclr.cc/Conferences/2027';cfp=u+'/CallForPapers'
x=base('ICLR',2027,u,'2027-04-26','2027-04-30','California, USA · 具体场馆待公布',cfp)
x['event']['sourceUrl']='https://iclr.cc/'
x['tracks']=[track('main','Conference Papers','2026-09-18','2026-09-25','https://openreview.net/group?id=ICLR.cc/2027/Conference',cfp)]
x['template']=template('https://media.iclr.cc/Conferences/ICLR2027/iclr-2027-style-files.zip',2027,'current',u+'/AuthorGuidelines')
x['acceptanceHistory'][2]=acc(2025,3704,11603,'https://media.iclr.cc/Conferences/ICLR2026/ICLR2026_Fact_Sheet.pdf','2026 官方 Fact Sheet 回顾的 2025 主会数据。')
a='https://blog.iclr.cc/2025/04/22/announcing-the-outstanding-paper-awards-at-iclr-2025/'
x['bestPapers']=[paper(p['title'].rstrip('.'),p['url'],'Outstanding Paper',a) for p in links['iclr_awards'][:3]]
C.append(x)
u='https://icml.cc/Conferences/FutureMeetings';cfp='https://icml.cc/Conferences/2026/CallForPapers'
x=base('ICML',2027,u,None,None,'South America · 城市与会期尚未公布',cfp)
x['tracks']=[track('main','Main Track',None,None,None,u,'2027 CFP 与截止日期尚未核验；不将 2026 日期外推。')]
x['template']=template('https://media.icml.cc/Conferences/ICML2026/Styles/icml2026.zip',2026,'previous-year',cfp,'2027 模板尚未核验；暂提供 2026 官方模板，仅供提前准备。正式投稿前核对 2027 CFP。')
x['previousEdition']={'year':2026,'officialUrl':'https://icml.cc/Conferences/2026','event':{'start':'2026-07-06','end':'2026-07-11','location':'Seoul, South Korea'},'tracks':[track('main','Main Track','2026-01-23','2026-01-28','https://openreview.net/group?id=ICML.cc/2026/Conference',cfp),track('position','Position Papers','2026-01-23','2026-01-28','https://openreview.net/group?id=ICML.cc/2026/Position_Paper_Track','https://icml.cc/Conferences/2026/CallForPositionPapers')]}
x['acceptanceHistory'][2]=acc(2025,3260,12107,'https://aip.riken.jp/news/icml2025/?lang=ja','主赛道；RIKEN AIP 官方新闻报告原始数量，会议官方 Fact Sheet 确认 3260 篇及约 27%。')
x['acceptanceHistory'][2]['sources'].append(source('https://media.icml.cc/Conferences/ICML2025/ICML2025_Fact_Sheet.pdf','ICML 官方 Fact Sheet'))
x['bestPapersSource']='https://icml.cc/virtual/2025/awards_detail'
C.append(x)
c={x['acronym']:x for x in C}
c['AAAI']['tracks'][1]['submissionUrl']='https://openreview.net/group?id=AAAI.org/2027/Artificial_Intelligence_for_Social_Impact_Track'
c['AAAI']['tracks'][2]['submissionUrl']=None
c['AAAI']['tracks'][2]['note']+=' 专用提交入口尚未单独核验，请从该 Track 官方 CFP 进入。'
c['EMNLP']['tracks'][0]['commitmentUrl']='https://openreview.net/group?id=EMNLP'
c['EMNLP']['tracks'][1]['submissionUrl']='https://openreview.net/group?id=EMNLP/2026/Industry_Track'
c['NeurIPS']['tracks'][1]['submissionUrl']='https://openreview.net/group?id=NeurIPS.cc/2026/Evaluations_and_Datasets_Track'
c['ICML']['bestPapers']=json.loads(Path('research/icml-awards.json').read_text())
c['ICLR']['acceptanceHistory'][0]=acc(2023,1574,4938,'https://media.iclr.cc/Conferences/ICLR2023/ICLR2023-Fact_Sheet.pdf','官方 Fact Sheet 主会统计；分母为完整投稿，非摘要注册数。该文件四舍五入显示约 31%，此处百分比由原始整数重算。')
c['ICLR']['acceptanceHistory'][1]=acc(2024,2260,7262,'https://media.iclr.cc/Conferences/ICLR2024/ICLR2024-Fact_Sheet.pdf','官方 Fact Sheet 主会统计；原始分母为 7262，与其他收集日期的 OpenReview 汇总可能不同。')
c['ICML']['acceptanceHistory'][1]=acc(2024,None,None,'https://media.icml.cc/Conferences/ICML2024/ICML2024_Fact_Sheet.pdf','官方仅给出超过 2600 篇和 27.5%；未提供可核验整数分母，不反推。',27.5)
Path('research/ai-details.json').write_text(json.dumps({'asOf':D,'acceptanceWindow':[2023,2024,2025],'bestPapersYear':2025,'conferences':C},ensure_ascii=False,indent=2))
print('Wrote',len(C),'conferences;',sum(len(x['tracks']) for x in C),'tracks;',sum(a['accepted'] is not None and a['submitted'] is not None for x in C for a in x['acceptanceHistory']),'verified ratios')
