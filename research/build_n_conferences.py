from pathlib import Path
import json,re
root=Path(__file__).resolve().parent
catalog=json.loads((root/'ccf-catalog.json').read_text())
rows=[
 {'id':'colm','acronym':'COLM','name':'Conference on Language Modeling','area':'人工智能','areaId':'ai','officialUrl':'https://colm.cc/','selectionReason':'持续举办的语言建模研究会议；官方征稿页确认 2026 为第三届，并设置独立研究论文征稿和同行评审。适合语言模型研究投稿导航。','sources':[{'label':'COLM 2026 官方网站','url':'https://colm.cc/'},{'label':'COLM 主办方官方征稿源文件','url':'https://github.com/COLM-org/colm-org.github.io/blob/main/cfp.md'}]},
 {'id':'corl','acronym':'CoRL','name':'Conference on Robot Learning','area':'人工智能','areaId':'ai','officialUrl':'https://www.corl.org/home','selectionReason':'机器人与机器学习交叉领域的年度国际研究会议；官方列有 2026 议程及录用论文，Robot Learning Foundation 是其治理机构。','sources':[{'label':'CoRL 2026 官方网站','url':'https://www.corl.org/home'},{'label':'Robot Learning Foundation','url':'https://www.robot-learning.org/'}]},
 {'id':'mlsys','acronym':'MLSys','name':'Conference on Machine Learning and Systems','area':'交叉/综合/新兴','areaId':'interdisciplinary','officialUrl':'https://mlsys.org/Conferences/2026','selectionReason':'聚焦机器学习与系统交叉的年度会议；官方确认 2026 为第九届，提供公开论文集、研究论文与产业 Track。','sources':[{'label':'MLSys 2026 官方网站及历届目录','url':'https://mlsys.org/Conferences/2026'}]},
 {'id':'rss','acronym':'RSS','name':'Robotics: Science and Systems','area':'人工智能','areaId':'ai','officialUrl':'https://roboticsconference.org/','selectionReason':'持续举办的机器人研究会议；官方确认 2026 为第 22 届，公开同行评审征稿与录用论文，并已公布 2027 届。','sources':[{'label':'RSS 2026 官方网站','url':'https://roboticsconference.org/2026/'},{'label':'RSS 2026 官方征稿','url':'https://roboticsconference.org/information/cfp/index.html'}]}
]
def norm(s): return re.sub('[^a-z0-9]','',s.lower())
for c in rows:
 assert not any(norm(c['acronym'])==norm(x['acronym']) or norm(c['name'])==norm(x['name']) for x in catalog['conferences'])
 c.update(rank='N',displayName=c['acronym'],asOf='2026-10-28',ccfSource=catalog['sources'][0]['url'],catalogUrl=None,rankBasis='应用自定义 N 类；未列入 CCF 第七版（2026）386 个会议条目。非 CCF 官方分级。',ccfMatchChecked=True,activityYear=2026)
out={'asOf':'2026-10-28','policy':'N 为本站补充收录的、未列入当前 CCF 会议目录的活跃研究会议，收录不代表 CCF 认可或与 A/B/C 等价。主流性为编辑选择，依据公开同行评审征稿、持续举办记录与学术社区定位，不构造客观排名。','catalogVersion':catalog['version'],'catalogSha256':catalog['sourceSha256'],'conferences':rows,'excludedCandidates':[{'acronym':'AISTATS','rank':'C','sourcePage':59,'reason':'已在 CCF 第七版，不应归入 N'},{'acronym':'UAI','rank':'B','sourcePage':58,'reason':'已在 CCF 第七版，不应归入 N'},{'acronym':'ICLR','rank':'A','sourcePage':57,'reason':'已在 CCF 第七版，不应沿用旧分级或归入 N'}]}
(root/'n-conferences.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print('N candidates validated:',', '.join(c['acronym'] for c in rows))
