# CCF 全学科会议目录核验记录

核验日期：2026-10-28（Asia/Singapore）。

## 版本和证据

- 当前采用第七版（2026）正式目录。CCF 发布页载明 2026-03-31 正式发布，2026-04-09 修正一处勘误：<https://www.ccf.org.cn/Academic_Evaluation/By_category/>。
- CCF 发布页可通过搜索索引读取，直接网页抓取遇到访问验证。未绕过验证，也未把旧版分类页当成第七版。
- 实际解析对象是 CCF 署名的 72 页正式 PDF，来自浙江工商大学图书馆公开转载页：<https://lib.zjgsu.edu.cn/2026/0414/c1056a221631/page.htm>。
- PDF URL：<https://lib.zjgsu.edu.cn/_upload/article/files/f5/b1/f4f7201343b88c0f10564f590ebe/854a3c68-36a6-4698-a359-5184d5e30a0c.pdf>。
- 与独立公开 GitHub 镜像 `LovenSar/CCF_RANK` 的同名正式版 PDF 比对，字节完全相同。两个文件大小均 346777 字节；SHA-256 均为 `271b630b576bf8a4f802e767f5694caded93680e22b3a19bef7902591c45c1d3`。
- PDF 元数据创建及修改时间均为 2026-04-09 11:13:27 +08:00，与发布页勘误日期一致。

## 产物

- `ccf-catalog.json`：应用可用结构化目录，全部从 PDF 表格提取；不含期刊或自定义 N 会议。
- `extract_ccf_catalog.py`：可复现提取脚本，不联网；依赖已有 bundled Python 的 pdfplumber，不安装软件。
- `ccf-2026-official-catalog.pdf`：大学镜像取得的原始文件。
- `ccf-2026-mirror.pdf`：独立 GitHub 镜像文件，用于哈希比对。
- `ccf-2026-extracted.txt`：pypdf 独立文字提取，辅助核验。
- `catalog-extraction.log`：提取数量、分组数量、全部会议名称输出。
- `qa/ccf-57.png`、`qa/ccf-58.png`：人工智能 A/B 会议页的渲染核验图。

## 完整性与计数

共 **386 个会议条目**：A **58**，B **132**，C **196**；覆盖官方全部 **10 个学科**。

| 学科 | A | B | C | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 计算机体系结构/并行与分布计算/存储系统 | 11 | 26 | 30 | 67 |
| 计算机网络 | 4 | 10 | 20 | 34 |
| 网络与信息安全 | 6 | 11 | 29 | 46 |
| 软件工程/系统软件/程序设计语言 | 10 | 20 | 27 | 57 |
| 数据库/数据挖掘/内容检索 | 5 | 13 | 13 | 31 |
| 计算机科学理论 | 5 | 10 | 10 | 25 |
| 计算机图形学与多媒体 | 4 | 14 | 17 | 35 |
| 人工智能 | 7 | 14 | 22 | 43 |
| 人机交互与普适计算 | 4 | 7 | 15 | 26 |
| 交叉/综合/新兴 | 2 | 7 | 13 | 22 |

实际执行：全部会议组逐行解析；每个学科/分级分组的原表序号连续性检查通过；输出记录 id 唯一性检查通过；记录数量与各分组加总一致。第 57/58 页人工智能 A/B 表通过渲染图像复核，确认 ICLR=A、IJCAI=B，不能沿用旧版分级。

## 字段使用注意

- `officialUrl` 全部为 `null`，因为目录中的网址多数为 DBLP，并不等于会议官方主页。原表网址放在 `catalogUrl`，不得直接称为“投稿链接”。
- 每条保留 `ccfSource`、`ccfCategorySource`、`sourcePdf` 和一基页码 `sourcePage`。分类页仅辅助导航，最终分级证据是第七版 PDF。
- 会议目录收录不表示该会议仍然举办、下一届已经公布、尚可投稿，或某个 Track 具备同等 CCF 认定；具体年份/Track 需另核查。
- CCF 官方说明分级适用于 Full paper / Regular paper，Short、Demo、Technical Brief、Summary、Findings 及伴随 Workshop 不计入目录考虑范围。不可将会议级别无条件继承到所有 Track。
- `sourceName` 保留原 PDF 全称；`name` 只修复少数排版连词/空格，未自行修订疑似源文件错误（例如 Euro-Par 全称末尾带 Springer）。英文名称以 PDF 为基准。
- `acronym` 保留原目录简称，仅去除换行造成的断词，并将历史简称注释移入 `aliases`。IEEE World Haptics Conference 的简称在原表为空，保留空值，应用用 `displayName` 或 `name` 兜底；不得凭空补简称。
- FSE / SEC 存在不同学科的同名缩写，id 添加学科后缀以防误合并：`fse-software` / `fse-security`，`sec-architecture` / `sec-security`。
- 常用检索别名可在应用层显式添加：例如 `SIGKDD` 对应通称 KDD，`ACM MM` 对应通称 ACM Multimedia。不要将不同会议因缩写相近而合并。
- 自定义 N 类必须与 CCF 官方 A/B/C 区分。ICLR 已为 A，不能再用作 N 示例。

## 限制

本阶段仅完成会议目录和分级数据，没有提供逐年的截止日期、会议地址、模板、录用率或 Best Paper；这些字段须由其他核验工作补全。未声称 386 个会议的官网或投稿链接均已核验。

PDF 版权属于中国计算机学会；本应用提取的是名称、分级、类别、参考地址等事实数据，不改变目录权属。
