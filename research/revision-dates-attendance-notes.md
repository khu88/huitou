# 日期与历史参会政策核验（2026-10-28）

主数据为 `revision-dates-attendance.json`。本轮只新增研究证据文件，未更改既有会议源数据或界面代码。数据交由主 Agent 合并。

## WWW 的重要纠正

- 2027 年主会是 5 月 12–14 日，整体活动是 5 月 10–14 日；前两日为 Workshops / Tutorials / Web4All。
- Research Long Paper 与 Short Paper 是两个 OpenReview 子入口。Industry 使用同一组 Long / Short 入口并勾选 Industry Paper，并非独立投稿系统。
- Short 摘要 invitation 的 `duedate` 是 `2026-11-10T13:00:00Z`；对应官网原值为 11 月 9 日 AoE。实际配置比官网晚 61 分钟。
- Demo invitation 的 `duedate` 是 `2026-11-15T21:00:00Z`；早于官网写明的 11 月 16 日 AoE。必须同时显示冲突及原日期，不能让用户误以为两处一致。
- Long 的 invitation 未公开读取成功，Short 的 Full_Submission invitation 尚未读取到。入口文字虽然显示不同时间，但未据此覆盖官网 deadline。
- `expdate` 是 invitation 失效时间，本轮均未当作正式投稿截止。原始提取见 `www-openreview-deadline-evidence.json`。
- 2026 是不同届次：主会 7 月 1–3 日，整体 6 月 29 日至 7 月 3 日，且官方已从 Dubai 线下计划改为全线上；不能与 2027 Dublin 混用。

## 历史政策口径

覆盖现有 12 场详细会议的 2023、2024、2025 年，共 36 条。30 条有足够官方政策或无届次证据，6 条明确标记未知。未知项是 AAAI 2023、NeurIPS 2023/2024、ICLR 2024/2025、WWW 2025。

`conditional` 不是“可以线上”的同义词。它可能表示需获批的远程报告、必须按现场费率注册、或允许代理现场报告。界面必须显示摘要说明。参会费率、远程观众票和直播均不能单独证明作者可远程报告。当前无年份的通用 FAQ 不用于倒推历史政策。

CVPR 与 ICCV 的官方作者注册页明确允许无法到场时虚拟参会，但仍须支付现场作者费率。KDD 2024/2025 和 NeurIPS 2025 允许安排现场代理，因此不能写成“至少一名作者本人必须到场”。

## 其余 deadline 抽查边界

另存 `other-openreview-deadline-audit.json`：AAAI 2027、EMNLP ARR May 2026、NeurIPS 2026、KDD 2027 Cycle 1 的公开入口文字与既有日期的 UTC 换算一致；过期 invitation 访问受限，不能称为已核验系统硬截止。CVPR 2027 摘要的实际 invitation 与既有日期一致。ICLR 2027 入口无公开日期，保留官网值。

ACL 2027 投稿入口尚未核实；ICML/ICCV 2027 DDL 保持未知；CHI PCS 及 ICSE HotCRP 本轮未完成系统级读取。因此没有宣称 12 场所有截止都经过提交系统核验。

## 已执行验证

Python 已检查 JSON 可解析、12 场会议唯一性、每场三年齐全、已知政策均有 HTTPS 官方来源、所有日期可按 ISO 解析，以及 WWW 两项 invitation 日期与预期一致。这里的验证证明数据结构与已录入证据的一致性，不证明来源在未来不会更新。
