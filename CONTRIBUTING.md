# 贡献指南

当前维护目标是网页版。公开源码见 GitHub khu88/huitou；代码许可证尚未确定，贡献流程会继续完善。不要提交真实账号数据库、凭证、未公开研究内容或本机运行日志。

## 补充或修正会议数据

1. 先确认会议届次、Track 与日期原始时区。优先查投稿系统，再查官方 CFP；两者冲突时保存原文出处和核验日期，不静默覆盖差异。
2. 在 `research/expanded-details/<学科>.json` 中按固定会议 ID 修改对应记录，保留来源链接、范围、核验日期和无法确认的字段。不要仅按缩写匹配：同缩写的会议可能属于不同系列。`data/conferences.json` 由构建脚本生成。
3. 运行 `python3 scripts/build_data.py`、`python3 scripts/validate_data.py` 和 `python3 scripts/audit_coverage.py`，查看相关会议的详情页及字段覆盖报告。扩展记录的 `detail: null` 不会擦除旧的已核验详情。

维护约定：

- CCF 等级依据当前目录与勘误，不自动赋予 Workshop、Short 或 Findings 相同等级；N 为本站分类。
- 摘要、全文、承诺提交等节点分别记录。准确时间戳必须带时区；官网仅公布日期时使用 `abstractDeadlineDate` / `fullDeadlineDate`，不要默认补为 23:59 或 AoE。这类节点展示日期但不生成倒计时、提醒或 ICS。页面关闭时间和 `expdate` 不是正式截止。
- `primary` 固定为主会 Full / Research Track；多轮投稿可以选择下一轮，已截止也不能用 Short、Demo 或 Industry 替代主会。获邀后提交的稿件标记 `submissionStage: invitation-only`；滚动投稿标记 `deadlineMode: rolling`，不能虚构一个年度截止。
- 核验状态与字段覆盖分开：`partial` 表示已读官方资料但仍有缺口；`unavailable` 表示尚未取得足以建立届次详情的来源，不等于会议停办。保留 `missingFields`，不要把查到首页或有日期称为全字段完成。
- 录用率需要整数分子、分母和相同的 Track 口径；缺少整数时留空，不从百分比反推。
- 模板沿用旧届时保留年份与回退说明。
- 每会精选论文不超过 10 篇；先保留已核验的主要获奖论文，再以官方 Oral/Spotlight 补充。奖项和展示类型分开标注，主题标签属于编辑归纳。官方获奖超过 10 篇时明确说明选集范围。
- 作者必须到场、至少一名作者到场、代理报告、附条件远程和线上观众票不能混为一谈；无法确认时标未知。
- 不通过修改断言掩盖数据错误。CCF 换版或历史统计窗口变更时，应同步说明新旧口径及来源。

## 修改代码

保持构建简单，优先复用现有浏览器与 Python 标准库能力。增加第三方依赖或资源时记录用途、来源和许可证。

```sh
python3 scripts/build_data.py
python3 scripts/validate_data.py
python3 scripts/audit_coverage.py
python3 scripts/build_standalone.py
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
```

界面变化还需检查窄屏、明暗主题、特大字号、键盘操作和减少动画。提醒变化需区分保存、授权、触发与送达；不要让静态页面显示不存在的云账号或后台推送能力。

提交说明应描述具体问题、变化及实际完成的验证。未执行的浏览器、手机或声音检查如实列出，不以逻辑测试代替设备验收。

## 素材与公开范围

参考 [素材说明](docs/assets.md)。用户提供的图片不因放入仓库就自动获得开放再分发许可；代码与第三方资料也不共享默认许可证。公开发布前确认授权，或替换为许可明确的素材。

`research/expanded-details/` 保存经人工核对的事实与公开来源，是默认离线构建输入；`research/data-quality-report.json` 保存逐会缺口。原始网页/PDF 缓存在 `research/evidence/`，已排除于 Git，不随应用分发，也不是构建必需文件。目录/评级快照的既有来源说明另见 `research/rankings-README.md`。`.local/`、数据库、日志、依赖、`dist/` 与本地任务记录不应提交。

管理功能的实现只保存在本地私有扩展中，不属于公开源码。`research/qa/` 的所有截图及验证记录也不提交，即使使用的是测试账号。不要强制添加已忽略文件或把它们复制到其他目录以绕过检查。公开版本应在完全不含私有扩展的目录中仍能启动、运行账号/会议/微信和公共木鱼功能。

提交前运行 `python3 scripts/audit_publication.py`；暂存后再运行 `python3 scripts/audit_publication.py --staged` 检查实际提交内容。检查不能证明不存在所有秘密，发布者仍需审阅本次文件清单。
