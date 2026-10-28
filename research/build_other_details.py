import json
from pathlib import Path
D='2026-10-28'
ACM='https://www.acm.org/publications/proceedings-template'
def track(name,a,p,sub,src,template=None,note=None):
 return dict(name=name,abstractDeadline=(a+'T23:59:00-12:00') if a else None,fullDeadline=(p+'T23:59:00-12:00') if p else None,timezone='AoE (UTC−12)',submissionUrl=sub,template=template,sources=src if isinstance(src,list) else [src],note=note)
def tpl(url,year=2027,status='current',note=None):return dict(url=url,year=year,status=status,note=note)
def rate(y,a=None,s=None,scope='Main / Research Track',sources=None,note=None):return dict(year=y,accepted=a,submitted=s,percent=round(a/s*100,2) if a is not None and s else None,scope=scope,sources=sources or [],note=note)
def paper(title,url,award,source):return dict(title=title,url=url,award=award,source=source)
def conf(ac,year,url,start,end,location,source,tracks,acceptance=None,best=None,notes=None):
 return dict(acronym=ac,year=year,officialUrl=url,event=dict(start=start,end=end,location=location,source=source),tracks=tracks,acceptance=acceptance or [rate(y) for y in [2023,2024,2025]],bestPapers=best or dict(year=2025,items=[],source=None,note='尚未核验具体获奖论文'),verifiedDate=D,notes=notes or [])
cvpr='https://cvpr.thecvf.com/Conferences/2027'
cvpra='https://cvpr.thecvf.com/Conferences/2025/News/Awards_Press'
cs=[]
cs.append(conf('CVPR',2027,cvpr,'2027-06-20','2027-06-25','Seattle, Washington, USA',cvpr+'/Dates',[
 track('Main Conference / Research','2026-11-10','2026-11-16','https://openreview.net/group?id=thecvf.com/CVPR/2027/Conference',[cvpr+'/CallForPapers',cvpr+'/AuthorGuidelines'],tpl('https://media.eventhosts.cc/Conferences/CVPR2027/author-kit-CVPR2027-v1-latex.zip'), '11月10日为强制 Paper Enrollment / 注册截止，官方作者指南也称 abstract deadline。'),
], [rate(2023,2359,9155,sources=['https://cvpr.thecvf.com/Conferences/2023/BlogPaperSubmissions']),rate(2024,2719,11532,sources=['https://cvpr.thecvf.com/Conferences/2024/News/Wrap_Release']),rate(2025,2872,13008,sources=['https://cvpr.thecvf.com/Conferences/2025/News/Technical_Program'],note='采用官方 Technical Program 公布的成对数量；另一 Wrap 新闻稿的 12008 与其 13%增长陈述及 Technical Program 冲突，未采用。')],dict(year=2025,items=[paper('VGGT: Visual Geometry Grounded Transformer','https://openaccess.thecvf.com/content/CVPR2025/html/Wang_VGGT_Visual_Geometry_Grounded_Transformer_CVPR_2025_paper.html','Best Paper',cvpra),paper('Neural Inverse Rendering from Propagating Light','https://openaccess.thecvf.com/content/CVPR2025/html/Malik_Neural_Inverse_Rendering_from_Propagating_Light_CVPR_2025_paper.html','Best Student Paper',cvpra)],source=cvpra),['会议完整日程含6月20–21日workshops/tutorials，主会6月22–25日。']))
www='https://www2027.thewebconf.org'
wwws=www+'/research-track-papers/'
wwwaw='https://actu.epfl.ch/news/philipp-schneider-wins-2025-web-conference-best--3/'
cs.append(conf('WWW',2027,www,'2027-05-10','2027-05-14','Dublin, Ireland',wwws,[
track('Research Papers','2026-10-18','2026-10-25','https://openreview.net/group?id=ACM.org/TheWebConf/2027',wwws,tpl(ACM,note='2027 CFP明确要求 ACM sigconf,anonymous,review 通用模板。')),
track('Industry Papers','2026-10-18','2026-10-25',None,www+'/important-dates/',None,'日期已核验，专用投稿入口与模板待核验。'),
track('Short Papers','2026-11-09','2026-11-16',None,[www+'/important-dates/',wwws],tpl(ACM,note='2027 research CFP规定 short paper 4页，含参考文献和附录。'),'专用投稿入口待核验。'),
track('Demo Papers',None,'2026-11-16','https://openreview.net/group?id=ACM.org/TheWebConf/2027/Demos',[www+'/important-dates/',www+'/demos/'],tpl(ACM)),
], [rate(2023,note='本轮未取得可追溯的成对官方数量。'),rate(2024,405,2008,'Research Tracks / valid submissions',['https://www2024.thewebconf.org/about/newsletters/']),rate(2025,409,2062,'Research Track / 送审有效论文（不含 desk reject）',['https://yom-tov.info/blog/2025/04/30/insights-from-serving-as-one-of-thewebconference-2025-program-chairs/'], '来源为2025程序主席本人报告：2496份全文，434篇desk reject，2062篇送审。若以全部全文为分母，则409/2496=16.39%；此处采用主席报告的送审口径。')],dict(year=2025,items=[paper('Behavioral Homophily in Social Media via Inverse Reinforcement Learning: A Reddit Case Study','https://doi.org/10.1145/3696410.3714618','Best Paper',wwwaw)],source=wwwaw,note='由获奖作者所在机构 EPFL 的公告核验。'),['各研究主题子Track详见 Research CFP；这里单独列可独立投稿的论文类型。']))
chi='https://chi2027.acm.org'
chit=tpl(chi+'/chi-publication-formats/',note='2027官方格式页；审稿用单栏 ACM manuscript,review,anonymous。')
cs.append(conf('CHI',2027,chi,'2027-05-10','2027-05-14','David L. Lawrence Convention Center, Pittsburgh, USA',chi+'/attendees/visa-faq/',[
track('Papers',None,'2026-09-10','https://new.precisionconference.com/',chi+'/authors/papers/',chit,'官方明确没有单独摘要截止；12月3日是已进入修订流程的重投稿截止，不能当作新稿DDL。'),
track('Posters',None,'2027-01-21',None,chi+'/',None,'专用投稿入口与该Track模板尚未核验。'),
track('Interactive Demos',None,'2027-01-21',None,chi+'/',None,'专用投稿入口与该Track模板尚未核验。'),
track('Panels',None,'2026-11-19',None,chi+'/',None,'专用投稿入口与该Track模板尚未核验。')
],[rate(2023,note='未核验最终成对数量。'),rate(2024,1060,4028,'Papers Track / completed submissions',['https://chi2024.acm.org/2023/11/17/chi-2024-papers-track-post-round-one-outcomes-report/','https://chi2024.acm.org/2024/01/29/chi-2024-papers-track-post-pc-outcomes-report/'],'使用同届R1报告完整投稿数4028及post-PC录用数1060计算26.32%；官方post-PC公布26.4%，其说明存在冲突回避导致的分析缺失。后续年度回顾出现4046，故口径不可直接混合。'),rate(2025,1249,5014,'Papers Track / conditional acceptance',['https://chi2025.acm.org/chi-2025-papers-track-post-pc-outcomes-report/'],'PC会后有条件录用，非最终出版篇数。')],dict(year=2025,items=[],source='https://programs.sigchi.org/chi/2025/awards/',note='官方公告确认50篇Best Paper；动态奖项页面未提取到逐篇标题，待补10篇。',evidence='https://chi2025.acm.org/best-paper-and-honorable-mention-awards-at-chi-2025/')))
kdd='https://kdd2027.kdd.org'
kddaw='https://www.kdd.org/awards/view/2025-sigkdd-best-paper-award-winners'
kddTracks=[]
for name,slug,group in [('Research Track · Cycle 1','research-track-call-for-papers','Research_Track'),('Applied Data Science · Cycle 1','applied-data-science-ads-track-call-for-papers','Applied_Data_Science_Track'),('Datasets & Benchmarks · Cycle 1','datasets-and-benchmarks-track-call-for-papers','Datasets_and_Benchmarks_Track'),('AI for Sciences · Cycle 1','ai4sciences-track-call-for-papers','AI4Sciences_Track')]:
 kddTracks.append(track(name,'2026-07-19','2026-07-26','https://openreview.net/group?id=KDD.org/2027/'+group+'_Cycle_1',kdd+'/'+slug+'/',tpl(ACM,note='2027 CFP明确采用 ACM 模板；不同Track的匿名要求不同。')))
cs.append(conf('KDD',2027,kdd,'2027-08-01','2027-08-05','San Jose McEnery Convention Center, San Jose, California, USA',kdd+'/',kddTracks,best=dict(year=2025,source=kddaw,items=[
paper('Improving Group Robustness on Spurious Correlation via Evidential Alignment','https://arxiv.org/abs/2506.11347','Research Track · Best Paper',kddaw),
paper('Taming Recommendation Bias with Causal Intervention on Evolving Personal Popularity','https://arxiv.org/abs/2505.14310','Research Track · Best Student Paper',kddaw),
paper('Evaluating Decision Rules Across Many Weak Experiments','https://arxiv.org/abs/2502.08763','Applied Data Science · Best Paper',kddaw),
paper('When Heterophily Meets Heterogeneity: Challenges and a New Large-Scale Graph Benchmark','https://doi.org/10.1145/3711896.3737421','Datasets & Benchmarks · Best Paper',kddaw)
]),notes=['官网公布两个投稿周期；本轮仅核验到Cycle 1精确截止。Cycle 2未填日期，不以往年推算。']))
icse='https://conf.researchr.org'
icses=icse+'/track/icse-2027/icse-2027-research-track'
icset=track('Research Track','2026-06-23','2026-06-30','https://icse2027.hotcrp.com/',icses,tpl('https://www.ieee.org/conferences/publishing/templates.html',note='2027 Research CFP指向 IEEE会议模板。'),'2027仅一个投稿周期；11月17日为已获修订决定论文的revision due，不能作为新稿投稿。')
icset['abstractDeadline']='2026-06-23T23:59:59-12:00';icset['fullDeadline']='2026-06-30T23:59:59-12:00'
cs.append(conf('ICSE',2027,icse+'/home/icse-2027/','2027-04-25','2027-05-01','Dublin, Ireland',icses,[icset],notes=['其他已存在Tracks包括SEET、SEIP、SEIS、NIER、Journal-first、Tool Demonstration等；逐Track数据待补。','共址会议不等于ICSE主会Track，不混用录用统计或CCF分级。']))
iccv='https://iccv.thecvf.com/Conferences/2027'
cs.append(conf('ICCV',2027,iccv,None,None,'Hong Kong Convention and Exhibition Centre, Hong Kong',iccv,[track('Main Conference / Research',None,None,None,iccv,tpl('https://media.eventhosts.cc/Conferences/ICCV2025/ICCV2025-Author-Kit-Feb.zip',2025,'previous-edition','尚未核验2027模板；ICCV为双年会议，沿用最近一届2025的Author Kit，仅供准备参考。'),'2027 CFP与精确截止尚未公布于本轮所读页面。')],notes=['官网标题显示2027-10-03至10-07，venue正文显示10-02至10-08，未明确分别对应何种日程，保留日期冲突待核验。','2024没有ICCV常规届次；近三日历年与近三届不可混淆。']))
cs[-1]['tracks'][0]['sources'].append('https://iccv.thecvf.com/Conferences/2025/AuthorGuidelines')
cs[-1]['tracks'][0]['status']='pending-current-edition'
out=dict(verifiedDate=D,acceptanceWindow=[2023,2024,2025],bestPaperYear=2025,policy='仅已核验字段有值；未知为null。截止时间保留原时区，AoE为UTC−12。年度窗口按当前日历年2026之前三个完整年份。',conferences=cs)
p=Path('research/other-details.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print('wrote',p,'conferences',len(cs),'tracks',sum(len(c['tracks']) for c in cs))
