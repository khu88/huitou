"""Rebuild reviewed 2025 selections from existing awards and saved official program indices.
Run from repository root. This writes research/curated-papers.json only.
"""
import json
from pathlib import Path
from urllib.parse import urljoin
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'research/curation-evidence'
old=json.loads((E/'existing-awards-2025.json').read_text())
confs={}
for c in old['conferences']:
    if not c.get('detail'): continue
    p=c['detail'].get('bestPapers',{})
    items=[{k:v for k,v in x.items() if k in ['title','url','award','source']} for x in p.get('items',[])]
    for item in items:
        item['presentationType']='best'
        item['source']=item.get('source') or p.get('source')
    confs[c['acronym']]={'acronym':c['acronym'],'selectionNote':'','items':items,'sources':([{'label':'2025 官方奖项','url':p['source']}] if p.get('source') else [])}

def topics(name,arr):
    assert len(arr)==len(confs[name]['items'])
    for x,topic in zip(confs[name]['items'],arr): x['topic']=topic

topics('SIGKDD',['鲁棒性与伪相关','推荐系统与因果推断','在线实验与决策','图学习与数据集'])
topics('AAAI',['社会选择与查询复杂度','神经符号推理','部分可观测决策'])
topics('NeurIPS',['语言模型多样性与评测','注意力机制与效率','自监督强化学习','扩散模型理论'])
topics('ACL',['语言模型采样理论','公平性评测','对齐与数据压缩','稀疏注意力'])
topics('CVPR',['三维几何基础模型','计算成像与逆渲染'])
topics('ICML',['预测与社会福利','自回归生成与创意','共形预测与不确定性','离散扩散模型','协作式语言模型','缺失数据与分数匹配'])
topics('ICLR',['语言模型安全对齐','语言模型微调动力学','模型知识编辑'])
topics('EMNLP',['检索与大规模语料索引'])
topics('WWW',['社交网络与行为建模'])

bases={'iclr':'https://iclr.cc','icml':'https://icml.cc','neurips':'https://neurips.cc','cvpr':'https://cvpr.thecvf.com','iccv':'https://iccv.thecvf.com'}

def oral(name,key,selection):
    idx=json.loads((E/f'{key}-orals.json').read_text())
    source=bases[key]+'/virtual/2025/events/oral'
    confs[name]['sources'].append({'label':'2025 官方 Oral program','url':source})
    for prefix,topic in selection:
        matches=[(t,h) for t,h in idx if t.startswith(prefix)]
        assert len(matches)==1,(name,prefix,matches)
        title,href=matches[0]
        confs[name]['items'].append({'title':title,'url':urljoin(bases[key],href),'award':'Oral','presentationType':'oral','topic':topic,'source':source,'selectionReason':'由官方 Oral 列表补充，以扩展研究主题覆盖；主题标签为编辑归纳。'})

oral('ICLR','iclr',[
 ('miniCTX:','数学与定理证明'),('ProtComposer:','生物分子生成'),('SAM 2:','图像与视频分割'),('Towards a Complete Logical Framework','图神经网络表达能力'),('Flat Reward in Policy Parameter Space','强化学习鲁棒性'),('Simplifying, Stabilizing and Scaling','一致性生成模型'),('Scaling Laws for Precision','模型精度与计算效率')])
oral('ICML','icml',[
 ('rStar-Math:','数学推理'),('DeFoG:','图生成'),('Network Sparsity Unlocks','深度强化学习'),('Learning Smooth and Expressive Interatomic','分子势能与物理预测')])
oral('NeurIPS','neurips',[
 ('RAG4GFM:','图基础模型与检索增强'),('Spectral Perturbation Bounds','隐私与低秩近似'),('SAVVY:','音视频空间理解'),('PhySense:','物理感知与传感器设计'),('High-dimensional neuronal activity','计算神经科学'),('In Search of Adam','优化算法')])
oral('CVPR','cvpr',[
 ('SegEarth-OV:','遥感与开放词表分割'),('RoboSpatial:','机器人空间理解'),('TopoCellGen:','病理图像与细胞生成'),('Motion Prompting:','可控视频生成'),('Closed-Loop Supervised Fine-Tuning','交通与自动驾驶'),('Molmo and PixMo:','视觉语言模型与开放数据'),('UniAP:','自动并行与训练效率'),('Rethinking Vision-Language Model in Face Forensics','人脸伪造检测')])
# Honorary awards remain distinct from the main Best/Outstanding category.
for x in confs['ICLR']['items']:
    if x['title'].startswith('SAM 2:'):
        x['award']='Honorable Mention · Oral'
        x['awardSource']='https://blog.iclr.cc/2025/04/22/announcing-the-outstanding-paper-awards-at-iclr-2025/'
for x in confs['CVPR']['items']:
    if x['title'].startswith('Molmo and PixMo:'):
        x['award']='Best Paper Honorable Mention · Oral'
        x['awardSource']='https://www.thecvf.com/?page_id=413'
confs['CVPR']['sources'].append({'label':'CVF 官方奖项档案','url':'https://www.thecvf.com/?page_id=413'})

confs['ICCV']['sources']=[{'label':'CVF 官方 2025 奖项档案','url':'https://www.thecvf.com/?page_id=413'}]
oral('ICCV','iccv',[
 ('Generating Physically Stable','文本到三维结构生成'),('FlowEdit:','生成图像编辑'),('Spatially-Varying Autofocus','计算成像与自动对焦'),('RayZer:','自监督新视角合成'),('Scaling Laws for Native Multimodal','原生多模态模型'),('Towards a Unified Copernicus','遥感与地球观测'),('GMMamba:','病理全切片分类'),('Moto:','机器人模仿学习'),('NullSwap:','身份隐私与深度伪造防护'),('Soft Local Completeness:','可解释人工智能')])
for x in confs['ICCV']['items']:
    if x['title'].startswith('Generating Physically Stable'):
        x.update(award='Best Paper · Marr Prize',presentationType='best',source='https://www.thecvf.com/?page_id=413',selectionReason='优先保留官方主奖 Best Paper。')
    elif x['title'].startswith('FlowEdit:'):
        x.update(award='Best Student Paper',presentationType='best',source='https://www.thecvf.com/?page_id=413',selectionReason='优先保留官方 Best Student Paper。')
    elif x['title'].startswith(('Spatially-Varying Autofocus','RayZer:')):
        x.update(award='Best Paper Honorable Mention · Oral',awardSource='https://www.thecvf.com/?page_id=413')

def anthology(name,key,selection):
    idx=json.loads((E/f'{key}-selected-anthology-links.json').read_text())
    source={'acl':'https://2025.aclweb.org/program/awards/','emnlp':'https://2025.emnlp.org/program/awards/'}[key]
    for prefix,award,topic,suffix in selection:
        matches=[(t,h) for t,h in idx if t.startswith(prefix) and h.endswith(suffix)]
        unique=list(dict.fromkeys(matches))
        assert len(unique)==1,(name,prefix,unique)
        title,href=unique[0]
        confs[name]['items'].append({'title':title,'url':urljoin('https://aclanthology.org',href),'award':award,'presentationType':'best','topic':topic,'source':source,'selectionReason':'官方获奖论文；优先奖项，同时补充不同研究主题。'})
    confs[name]['sources'].append({'label':'ACL Anthology 官方论文集','url':f'https://aclanthology.org/events/{key}-2025/'})

anthology('ACL','acl',[
 ('AfriMed-QA:','Best Social Impact Paper','医学问答与非洲语境','/2025.acl-long.96/'),
 ('The AI Gap:','Best Social Impact Paper','社会经济差异与语言技术','/2025.acl-long.914/'),
 ('Are Rules Meant to be Broken?','Best Resource Paper','多语言道德推理','/2025.acl-long.294/'),
 ('BRIGHTER:','Best Resource Paper','跨语言情感识别','/2025.acl-long.436/'),
 ('Palm:','Best Resource Paper','阿拉伯语与文化多样性','/2025.acl-long.1579/'),
 ('MaCP:','Best Theme Paper','参数高效适配','/2025.acl-long.1006/')])
anthology('EMNLP','emnlp',[
 ('LingGym:','Outstanding Paper','田野语言学推理','/2025.emnlp-main.69/'),
 ('Mind the Value-Action Gap:','Outstanding Paper','价值对齐与行为一致性','/2025.emnlp-main.154/'),
 ('DiscoSG:','Outstanding Paper','篇章场景图解析','/2025.emnlp-main.398/'),
 ('Generative or Discriminative?','Outstanding Paper','文本分类','/2025.emnlp-main.486/'),
 ('Measuring Chain of Thought Faithfulness','Outstanding Paper','推理链忠实性','/2025.emnlp-main.504/'),
 ('MiCRo: Mixture','Outstanding Paper','个性化偏好学习','/2025.emnlp-main.882/'),
 ('Causal Interventions Reveal','Outstanding Paper','因果分析与句法结构','/2025.emnlp-main.1271/'),
 ('InterIDEAS:','Best Special Theme Paper','哲学文本互文性','/2025.emnlp-main.1180/'),
 ('Autoformalization in the Wild:','Best Resource Paper','数学自动形式化','/2025.emnlp-main.90/')])

chi=json.loads((E/'chi-best-papers.json').read_text())
chi_best={c['id']:c for c in chi['contents'] if c.get('award')=='BEST_PAPER'}
assert len(chi_best)==50
selection=[(188217,'Web 权限与隐私'),(189502,'辅助技术与无障碍'),(188414,'可持续制造与回收'),(188628,'信息可视化'),(189229,'健康与术后生活质量'),(188559,'多模态创作与音乐'),(189110,'触觉交互与舞蹈'),(188973,'增强现实与跨设备交互'),(189580,'人机协作编程'),(189485,'生成内容与人类记忆')]
confs['CHI']['items']=[]
for id,topic in selection:
    c=chi_best[id]
    confs['CHI']['items'].append({'title':c['title'].strip(),'url':c['addons']['doi']['url'],'award':'Best Paper','presentationType':'best','topic':topic,'source':f'https://programs.sigchi.org/chi/2025/program/content/{id}','selectionReason':'从官方 50 篇 Best Paper 中按研究主题多样性选取；不代表官方排序。'})
confs['CHI'].update(totalOfficialBestPapers=50,sources=[{'label':'CHI 官方奖项公告','url':'https://chi2025.acm.org/best-paper-and-honorable-mention-awards-at-chi-2025/'},{'label':'SIGCHI 官方奖项列表','url':'https://programs.sigchi.org/chi/2025/awards/'},{'label':'SIGCHI 官方公开 program 数据','url':'https://files.sigchi.org/conference/program/CHI/2025'}])

notes={
 'ICSE':'2025 具体获奖论文尚未完成逐篇核验，暂不猜测论文或展示类型。',
 'SIGKDD':'保留已核验的研究、应用、数据集与基准主奖和学生奖 4 篇。尚未取得可核验的补充 Oral/Spotlight 标签，暂不凑足 10 篇。',
 'AAAI':'保留已核验的 3 篇 Outstanding Paper（该会议主奖名称）。尚未取得可核验的补充 Oral/Spotlight 标签，暂不凑足 10 篇。',
 'NeurIPS':'保留官方 4 篇 Best Paper，另从官方 Oral 列表选择 6 个互补主题；共 10 篇。',
 'ACL':'保留全部 4 篇主类别 Best Paper，另选 6 篇官方社会影响、资源和主题奖论文；总计 10 篇。其他专项奖及 Outstanding 未完整收录。',
 'CVPR':'保留 Best Paper 和 Best Student Paper，补充 8 篇官方 Oral；其中 Molmo 同时获 Honorable Mention。共 10 篇。',
 'ICCV':'保留 Marr Prize（Best Paper）和 Best Student Paper，另选 8 篇官方 Oral，其中 2 篇同时获 Honorable Mention；共 10 篇。',
 'ICML':'保留全部 6 篇 Outstanding Paper（该会议主奖名称），补充 4 篇官方 Oral；共 10 篇。',
 'ICLR':'保留全部 3 篇 Outstanding Paper（该会议主奖名称），补充 7 篇官方 Oral；其中 SAM 2 同时获 Honorable Mention。共 10 篇。',
 'EMNLP':'保留主奖 Best Paper、全部 7 篇 Outstanding，以及 Best Special Theme、Best Resource 各 1 篇；共 10 篇。',
 'CHI':'官方共 50 篇 Best Paper，按主题多样性精选其中 10 篇；这是获奖子集，不是完整获奖名单或官方排名。',
 'WWW':'目前核验 1 篇主奖 Best Paper；主办方旧站与展示标签尚未可靠取得，未用普通录用论文冒充 Oral/Spotlight。获奖证据来自作者所在 EPFL 官方新闻。'
}
for name,conf in confs.items():
    conf['selectionNote']=notes[name]
    assert len(conf['items'])<=10
    assert len({x['title'] for x in conf['items']})==len(conf['items'])
    for x in conf['items']:
        assert x['title'] and x['url'].startswith('https://') and x['source'].startswith('https://') and x['topic']
    if name=='WWW':
        conf['sources'][0]['label']='EPFL 官方获奖报道（作者机构）'
    for x in conf['items']:
        if x.get('awardSource') and not any(s['url']==x['awardSource'] for s in conf['sources']):
            conf['sources'].append({'label':'官方奖项补充证据','url':x['awardSource']})

policy='每会最多 10 篇：优先保留已核验的 Best Paper / Outstanding Paper 主奖；主奖超过 10 篇时明确标注官方总数与精选子集。保留准确的学生奖、专项奖、Honorable Mention 名称，不将其冒充主奖。名额不足时从官方 Oral / Spotlight 记录中按主题多样性补充；没有确切展示证据则保留少于 10 篇。topic 为依据论文标题/摘要作出的编辑归纳，非官方领域分类，不保证覆盖所有方向，也不以领域去重为由删除已核验的主奖。Oral/Spotlight 表示官方展示形式，不等同于获奖或质量排名。'
out={'asOf':'2026-10-28','year':2025,'policy':policy,'conferences':list(confs.values())}
(ROOT/'research/curated-papers.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print({x['acronym']:len(x['items']) for x in out['conferences']})
print('Total:',sum(len(x['items']) for x in out['conferences']))
