# AI / NLP / ML 首批资料核验

核验日期：2026-10-28。数据文件：`ai-details.json`。本次为公共只读检索及本地结构化整理；未执行远程写入、安装或消息发送。

## 覆盖和年份

- 6 个会议：AAAI、ACL、EMNLP、NeurIPS、ICLR、ICML；12 个当前届次 Track。
- 当前最新可核验届次：AAAI/ACL/ICLR 2027；EMNLP/NeurIPS 2026。ICML 已明确 2027 举办地区为 South America，但尚未核实城市、会期、CFP 与截止日期。
- ICML 2026 日期/两个 Track 保留在 `previousEdition`，不能作为 2027 的截止日期。
- 录用率窗口统一为此前三个完整自然年 2023–2025。Awards 统一为 2025：必须在 UI 标年份，不能将 2027 会议的 2025 awards 称为上一届。
- 21 篇获奖论文，均有官方获奖页及论文/会议详情链接。不包含 Test of Time 或 Honorable Mention。数量不足十篇时不凑数。

## 统计口径

| Conference | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| ACL | 1074 / 4864 | 940 / 4407 | 1699 / 8360 |
| EMNLP | 1047 / 4909 | 1271 / 6105 | 1811 / 8174 |
| NeurIPS | 3218 / 12343 | 4037 / 15671 | 5290 / 21575 |
| ICLR | 1574 / 4938 | 2260 / 7262 | 3704 / 11603 |
| ICML | 未核验 | 27.5%，原始数量未核验 | 3260 / 12107 |
| AAAI | 未核验 | 未核验 | 未核验 |

每条数据的来源和说明保留在 JSON `sources` / `note` 中。ACL 和 EMNLP 的 PDF 前言有关页文本保存在 `ai-stat-extracts.json`，用于复查。

- ACL 2024 以官方论文集前言的 940 为准；一些汇总站点显示 943，未混用。
- ACL 2025 以 Program Chairs 段落的 1699 为准；General Chair 段落近似写为 1700。
- EMNLP 2024 分母排除部分撤稿和 desk reject，2025 明确包含；跨年比较要保留口径提示。
- NeurIPS 2023/2024 用官方 Fact Sheet 的主赛道统计，排除 Datasets & Benchmarks。
- ICLR 2023/2024 用官方 Fact Sheet 的 4938/7262；其他日期抓取的 OpenReview 汇总可能不同。
- ICML 2025 的原始整数来源为 RIKEN AIP 官方新闻；会议官方 Fact Sheet 独立确认 3260 篇及约 27%。
- 百分比由整数重新计算，保留两位小数；原始数缺失时不反推。ICML 2024 单独保留官方公布的 27.5%。

## 日期、入口和模板

- 所有已核验投稿时间使用 UTC-12 (AoE) 的显式 ISO 时间戳。日期型 AoE 截止按 23:59 分钟显示；用户正式投稿时应核对官方投稿系统。
- ACL 2027 是 ARR review → commitment 两阶段；commitment 日期尚未公布。CFP 当前 ARR 链接误指向 2026 年，因此不将该旧入口标为 2027 投稿链接。
- EMNLP 2026 commitment 官方链接为通用 `https://openreview.net/group?id=EMNLP`，没有自行拼造年份路径。
- AAAI Main / AISI 与 AI Alignment 截止日期不同；AISI 有独立投稿入口。Alignment 专用入口未单独核验，暂使用 CFP 导航。
- NeurIPS 2026 Sydney 主会为 12/6–12；Atlanta / Paris 卫星会为 12/9–13，未合并成同一会期。
- AAAI 2027 Author Kit 已被官方 CFP 链接；工具访问 kit 返回 403，压缩包内容未检查。
- ACL / EMNLP 使用官方持续更新的通用 ACL 模板，不伪造模板年度。
- ICML 2027 最新模板未核验，明确提供 2026 旧版 fallback，正式提交需再次核对。

## 最小验证

已执行：JSON 可解析；所有非空 deadline ISO 时间戳可解析；每会 awards <=10；原始数量合法且全部计算百分比正确。

未执行：逐个链接的浏览器交互验收、压缩包内容验收、未收录年份的全量统计核验。未知字段保持 null。
