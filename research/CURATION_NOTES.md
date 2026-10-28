# 2025 精选论文数据核验

数据：`research/curated-papers.json`。核验日期：2026-10-28。

## 选择口径

- 每个会议最多 10 篇，保留现有已核验的 Best / Outstanding 主奖；不足时依据会议官方 Oral 名单补充互补主题。没有使用未经证实的展示类型。
- 主奖、学生奖、资源/主题/社会影响奖、Honorable Mention 均沿用准确奖名；Honorable Mention 不冒充主奖。
- CHI 官方 public program 中 `award=BEST_PAPER` 共 50 项，选取其中 10 个不同主题并明确是子集。主题标签为编辑归纳，非官方分类，不宣称覆盖全部研究领域。
- ACL 保留主类别的全部 4 篇 Best Paper，另收录 6 篇专项获奖论文。其它专项奖及 Outstanding 并非全部收录。
- 其余 ICLR/ICML 的 Outstanding 是该会议官方主奖名称，未改称 Best Paper。

## 当前覆盖

| 会议 | 篇数 | 数据状态 |
| --- | ---: | --- |
| NeurIPS | 10 | 4 Best + 6 Oral |
| ICML | 10 | 6 Outstanding + 4 Oral |
| ICLR | 10 | 3 Outstanding + 7 Oral，其中 SAM 2 为 Honorable Mention |
| CVPR | 10 | Best + Best Student + 8 Oral，其中 Molmo 为 Honorable Mention |
| ICCV | 10 | Marr Prize + Best Student + 8 Oral，其中 2 篇为 Honorable Mention |
| ACL | 10 | 4 主类别 Best + 6 专项 Best |
| EMNLP | 10 | Best + 7 Outstanding + Best Special Theme + Best Resource |
| CHI | 10 | 官方 50 篇 Best 中的主题精选 |
| SIGKDD | 4 | 保留核验奖项，补充展示类型待核验 |
| AAAI | 3 | 保留核验 Outstanding，补充展示类型待核验 |
| WWW | 1 | Best，证据为作者所在 EPFL 官方新闻；主站旧页面访问失败 |
| ICSE | 0 | 具体获奖论文尚未完成逐篇核验 |

合计 88 篇。不把不足 10 篇的会议写成已补全。

## 验证和证据

- `curation-evidence/manifest.json` 保存本次取得的官方 Oral/program/ACL Anthology 原始响应地址、HTTP 200、字节数与 SHA-256。大体积原始 HTML/JS 已压缩为与任务有关的书目与奖项事实，未保留无关客户端脚本。
- `*-orals.json` 是官方 2025 Oral 页面中的标题及逐篇链接索引；生成脚本要求所选标题匹配唯一官方记录。
- `*-selected-anthology-links.json` 为入选论文在 ACL Anthology 中的标题、URL；生成脚本同时检查标题前缀和具体年份/论文号。
- `chi-best-papers.json` 是官方 SIGCHI public program 中 50 篇 `BEST_PAPER` 的标题、内容 ID、奖项字段及 DOI。采集来源是公开的 `https://files.sigchi.org/conference/program/CHI/2025`。
- `existing-awards-2025.json` 固定了修改前 28 篇已核验奖项，避免重新生成时读取已合并数据造成重复。
- `link-check.json` 实际请求了 60 个已选官方 Oral 详情/ACL Anthology 链接：60 个 HTTP 200，60 个页面正文规范化后可匹配对应论文标题。未在这一检查中重新请求 DOI/OpenReview/OJS 链接；它们的获奖/题目信息依据保留的官方奖项及官方 program 记录。不能把这一结果解读为 88 个链接全部通过在线检查。
- 脚本断言：每会不超过 10 篇、同会标题唯一、所有条目有标题/HTTPS 论文链接/HTTPS 来源/主题标签。原 28 篇未删除。

重建：`python3 research/build_curated_papers.py`（在项目根目录执行；只更新 `research/curated-papers.json`）。

## 待补与避免的错误

AAAI、SIGKDD、WWW 仍需官方 Oral/Spotlight 的逐篇证据；ICSE 需要从官方 Research Track 核对 Distinguished Paper，不能混入同场举办的 MSR、SEAMS 或 Workshop 奖项。研究中发现一份第三方列表把 Stable-Sketch 误列为 WWW 2025：University of Edinburgh 官方报道及 ACM FY24 年报明确是 WWW 2024，故未纳入本年度。
