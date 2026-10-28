"""Bounded, deterministic WeChat commands over the local conference snapshot.

No network, database, model calls or side effects occur here. The caller must
authenticate the sender, execute against fresh account state in a transaction,
validate and persist ``patch``, then send ``text``. Queries never invent missing
conference facts. Mutation grammar is deliberately explicit.
"""

import hashlib
import math
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC = timezone.utc
MAX_TEXT = 3000
LEADS = {0: '截止时', 5: '提前5分钟', 60: '提前1小时', 180: '提前3小时',
         1440: '提前1天', 4320: '提前3天', 10080: '提前7天'}
HELP = '''会投助手 · 本地会议目录
查会议：ACL、查会议 ICLR、人工智能 A类会议、会议 第2页
看详情：WWW 截止、ACL 投稿、CVPR 模板、ICLR 录用率、ACL 参会、CVPR 论文
多 Track：WWW 第1轨 截止；论文分页：CVPR 论文 第2页
看近期：未来30天、未来7天、这个月截止、我的收藏截止
收藏：收藏 AAAI、取消收藏 AAAI、我的收藏
设置提醒：提醒 CVPR 全文 提前7天；提醒 ACL 第1轨 全文 提前1天
提醒提前量：7天、3天、1天、3小时、1小时、5分钟、截止时
管理提醒：我的提醒、暂停提醒 提醒ID、恢复提醒 提醒ID、删除提醒 提醒ID、暂停全部提醒
主动消息仅用于你启用的 DDL 提醒；不发送资讯或营销。
结果来自本地已核验快照，并非实时抓取；未补齐的数据会明确标注。'''


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return value.astimezone(UTC) if value.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _now(value):
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError('now must have an explicit timezone')
        return value.astimezone(UTC)
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value, UTC)
    parsed = _parse_date(value)
    if parsed is None:
        raise ValueError('now must be an aware datetime, ISO timestamp or Unix seconds')
    return parsed


def _conferences(catalog):
    return catalog.get('conferences', []) if isinstance(catalog, dict) else catalog


def reminder_due(reminder):
    """Return the UTC trigger time, or None for an invalid reminder snapshot."""
    if not isinstance(reminder, dict):
        return None
    deadline = _parse_date(reminder.get('deadline'))
    lead = reminder.get('leadMinutes')
    if deadline is None or type(lead) is not int or lead not in LEADS:
        return None
    try:
        return deadline - timedelta(minutes=lead)
    except OverflowError:
        return None


def reminder_problem(reminder, catalog):
    """Match the website's fail-closed current-deadline reconciliation."""
    if (reminder_due(reminder) is None or not reminder.get('id')
            or reminder.get('kind') not in ('abstract', 'full')
            or type(reminder.get('enabled')) is not bool):
        return '提醒格式无效'
    conference = next((c for c in _conferences(catalog)
                       if c['id'] == reminder.get('conferenceId')), None)
    track = next((t for t in (conference or {}).get('detail', {}).get('tracks', [])
                  if t.get('name') == reminder.get('trackName')), None)
    current = _parse_date((track or {}).get(reminder['kind'] + 'Deadline'))
    if current is None:
        return '当前节点日期待核验'
    if current != _parse_date(reminder['deadline']):
        return '日期已变化，请重新设置'
    return None


def _reply(lines, patch=None):
    if isinstance(lines, str):
        lines = lines.splitlines()
    chunks, length = [], 0
    for line in lines:
        line = str(line)
        if length + len(line) + 1 > MAX_TEXT - 65:
            chunks.append('内容较多，本条已节选。请指定第N轨、论文第N页或缩小查询范围。')
            break
        chunks.append(line)
        length += len(line) + 1
    return {'text': '\n'.join(chunks), 'patch': patch or {}}


def _urls(values):
    if not isinstance(values, (list, tuple)):
        values = [values]
    output = []
    for value in values:
        url = value.get('url') if isinstance(value, dict) else value
        if isinstance(url, str) and url.startswith(('https://', 'http://')) and url not in output:
            output.append(url)
    return output


def _source(values, prefix='来源'):
    urls = _urls(values)
    return [prefix + '：' + url for url in urls[:2]]


def _stamp(value, tz):
    parsed = _parse_date(value)
    if parsed is None:
        return '待核验 / 未公布'
    return parsed.astimezone(tz).strftime('%Y-%m-%d %H:%M %Z (UTC%z)')


def _countdown(value, now):
    parsed = _parse_date(value)
    if parsed is None:
        return ''
    seconds = (parsed - now).total_seconds()
    if seconds <= 0:
        return '已截止'
    minutes = math.ceil(seconds / 60)
    days, remainder = divmod(minutes, 1440)
    hours, minutes = divmod(remainder, 60)
    return '剩余' + (f'{days}天' if days else '') + (f'{hours}小时' if hours else '') + f'{minutes}分钟'


def _header(c):
    detail = c.get('detail', {})
    rank = 'N · 未分级' if c.get('rank') == 'N' else 'CCF ' + c.get('rank', '未知')
    return f"{c['acronym']} {detail.get('year', '')} · {rank} · {c.get('area', '领域待补')}".replace('  ', ' ')


def _footer(catalog, conference=None):
    detail = (conference or {}).get('detail', {})
    return '数据核验：' + str(detail.get('verifiedDate') or catalog.get('asOf') or '未知') + '；以官方最新投稿要求为准。'


@lru_cache(maxsize=2048)
def _alias_pattern(alias):
    return re.compile(r'(?<![A-Za-z0-9])' + re.escape(alias) + r'(?![A-Za-z0-9])', re.I)


def _mentions(text, conferences):
    """Match complete ASCII aliases even when next to Chinese characters."""
    found = []
    for c in conferences:
        aliases = [c.get('id', ''), c.get('acronym', ''), c.get('displayName', ''), *c.get('aliases', [])]
        if any(alias and _alias_pattern(alias).search(text) for alias in set(aliases)):
            found.append(c)
    # Long multiword aliases can contain an otherwise valid short acronym.
    exact = [c for c in found if text.casefold() in
             [str(c.get(k, '')).casefold() for k in ('id', 'acronym', 'displayName')]
             + [a.casefold() for a in c.get('aliases', [])]]
    return exact or found


def _track_number(text):
    match = re.search(r'第\s*(\d{1,3})\s*(?:轨|个?\s*[Tt]rack)', text)
    return int(match.group(1)) if match else None


def _page_number(text):
    match = re.search(r'第\s*(\d{1,4})\s*页', text)
    return max(1, int(match.group(1))) if match else 1


def _tracks(c, text):
    all_tracks = c.get('detail', {}).get('tracks', [])
    number = _track_number(text)
    if number is not None:
        return [(number, all_tracks[number - 1])] if 1 <= number <= len(all_tracks) else []
    return list(enumerate(all_tracks, 1))


def invitation_notice(track):
    """Read stage restrictions from the current catalog, including old reminders."""
    return ('仅限获邀稿件；此阶段不接受普通新稿。'
            if (track or {}).get('submissionStage') == 'invitation-only' else '')


def _deadline_lines(c, text, now, tz, compact=False):
    selected = _tracks(c, text)
    if not selected:
        return ['该 Track 不存在或截止信息尚未核验。']
    lines = []
    for index, track in selected:
        lines.append(f"第{index}轨 · {track['name']}")
        if invitation_notice(track):
            lines.append(invitation_notice(track))
        for kind, title in [('abstract', '摘要'), ('full', '全文')]:
            value = track.get(kind + 'Deadline')
            calendar_date = track.get(kind + 'DeadlineDate')
            if not value and calendar_date:
                lines.append(f'{title}：{calendar_date} · 仅确认日期，时刻或时区待核验；不计算倒计时。')
            elif not value and kind == 'full' and track.get('deadlineMode') == 'rolling':
                lines.append('全文：滚动投稿，无单一年度截止；请查看官方周期。')
            else:
                lines.append(f'{title}：{_stamp(value, tz)}' + (f' · {_countdown(value, now)}' if value else ''))
            if value and not compact:
                lines.append('原始时间：' + value + ' · ' + str(track.get(kind + 'Timezone', track.get('timezone', ''))))
        if track.get('deadlineConflict'):
            lines.append('注意：投稿系统与官网日期存在冲突。')
        if track.get('note') and (not compact or track.get('deadlineConflict')):
            lines.append(track['note'])
        if track.get('deadlineSourceLabel'):
            lines.append('采用依据：' + track['deadlineSourceLabel'])
        source = track.get('submissionUrl') or track.get('cfpUrl') or track.get('submissionInfoUrl')
        lines.extend(_source(source or track.get('sources', []), '投稿 / 核验入口'))
    return lines


def _detail(c, text, catalog, now, tz):
    detail = c.get('detail', {})
    lines = [_header(c)]
    if not detail:
        lines.extend(['该会议已收录目录；Track、截止、录用率等详情尚未核验。', c.get('name', '')])
        lines.extend(_source(c.get('officialUrl') or c.get('ccfSource') or c.get('catalogUrl')))
        return _reply(lines + [_footer(catalog, c)])
    lower = text.lower()
    if any(word in lower for word in ('论文', 'best paper', 'spotlight', 'oral')):
        collection = detail.get('curatedPapers') or detail.get('bestPapers') or {}
        items = collection.get('items', [])[:10]
        # Preserve official award labels and keep verified main awards first.
        items = sorted(items, key=lambda p: 0 if p.get('presentationType') == 'best' or
                       p in detail.get('bestPapers', {}).get('items', []) else 1)
        page = _page_number(text)
        selected = items[(page - 1) * 5:page * 5]
        year = collection.get('year') or detail.get('bestPapers', {}).get('year') or catalog.get('bestPaperYear', '未知')
        lines.append(f'精选论文 · {year} · 共{len(items)}篇（最多10篇），第{page}页')
        if collection.get('selectionNote'):
            lines.append(collection['selectionNote'])
        if not selected:
            lines.append('此页没有已核验论文。' if items else '论文尚未核验，不以普通论文冒充获奖 / Oral / Spotlight。')
        for index, paper in enumerate(selected, (page - 1) * 5 + 1):
            lines.append(f"{index}. [{paper.get('award') or paper.get('presentationType', '标签待核验')}] {paper['title']}")
            if paper.get('topic'):
                lines.append('主题（编辑归纳）：' + paper['topic'])
            if paper.get('linkType') in ('award-list', 'program-entry'):
                lines.append(('链接至官方获奖名单' if paper['linkType'] == 'award-list' else '链接至官方议程') + '；独立论文地址尚未核验。')
            lines.extend(_urls(paper.get('url')))
        lines.extend(_source(collection.get('sources') or collection.get('source') or
                             [p.get('source') for p in selected], '标签来源'))
        if len(items) > page * 5:
            lines.append(f"继续：{c['acronym']} 论文 第{page + 1}页")
    elif any(word in lower for word in ('录用', 'acceptance')):
        rows = detail.get('acceptance', [])
        years = catalog.get('acceptanceWindow') or sorted({r['year'] for r in rows})[-3:]
        lines.append('录用统计年份：' + '、'.join(map(str, years)) + '；各年统计口径可能不同。')
        for year in years[-3:]:
            row = next((r for r in rows if r.get('year') == year), {})
            accepted, submitted = row.get('accepted'), row.get('submitted')
            valid = type(accepted) is int and type(submitted) is int and submitted > 0 and 0 <= accepted <= submitted
            lines.append(f'{year}：' + (f'{accepted}/{submitted} = {accepted / submitted * 100:.2f}%' if valid else '未取得可核验的成对数量'))
            if row.get('scope'):
                lines.append('口径：' + row['scope'])
            if row.get('note'):
                lines.append(row['note'])
            lines.extend(_source(row.get('sources', [])))
    elif any(word in lower for word in ('参会', '线下', '线上', '到场', 'attendance')):
        rows = detail.get('attendance', [])
        years = catalog.get('acceptanceWindow') or sorted({r['year'] for r in rows})[-3:]
        statuses = {'required': '须现场', 'in-person-required': '须现场', 'remote-allowed': '允许远程',
                    'conditional': '有条件 / 特殊安排', 'unknown': '未确认', 'not-held': '该年未举办'}
        lines.append('作者参会政策（历史届次，不推断当届要求）')
        for year in years[-3:]:
            row = next((r for r in rows if r.get('year') == year), {})
            lines.append(f"{year}：{statuses.get(row.get('status'), '未确认')} · {row.get('scope', '范围待核验')}")
            lines.append(row.get('summary') or '尚无足够依据判断作者是否必须现场参会。')
            lines.extend(_source(row.get('sources', [])))
    elif any(word in lower for word in ('模板', '模版', 'template', '投稿', 'track')) or _track_number(text):
        if any(word in lower for word in ('截止', 'ddl', 'deadline')):
            lines.extend(_deadline_lines(c, text, now, tz))
        else:
            selected = _tracks(c, text)
            if not selected:
                lines.append('该 Track 不存在或尚未核验。')
            for index, track in selected:
                lines.append(f"第{index}轨 · {track['name']}")
                lines.append('投稿入口：' + (track.get('submissionUrl') or '尚未核验 / 未开放'))
                lines.extend(_source(track.get('submissionInfoUrl') or track.get('cfpUrl'), '投稿说明'))
                template = track.get('template') or detail.get('template') or {}
                status = {'current': '当届', 'previous': '前一年备用', 'fallback': '旧版备用',
                          'rolling': '持续更新通用模板'}.get(template.get('status'), template.get('status', '待核验'))
                lines.append(f"模板：{template.get('year') or '无固定年份'} · {status}")
                lines.extend(_urls(template.get('url')))
                if template.get('note'):
                    lines.append(template['note'])
                if track.get('note'):
                    lines.append(track['note'])
                lines.extend(_source(track.get('sources', [])))
    elif any(word in lower for word in ('截止', 'ddl', 'deadline', '还有多久', '什么时候交')):
        lines.extend(_deadline_lines(c, text, now, tz))
    else:
        event = detail.get('event', {})
        lines.extend([c.get('name', ''), f"举办：{event.get('start') or '日期待公布'} → {event.get('end') or '待公布'}",
                      '地点：' + (event.get('location') or '待公布')])
        if event.get('note'):
            lines.append(event['note'])
        lines.extend(_source(event.get('source') or event.get('sourceUrl'), '会期来源'))
        lines.extend(_deadline_lines(c, text, now, tz, compact=True))
        lines.append(f"继续查询：{c['acronym']} 投稿 / 模板 / 录用率 / 参会 / 论文")
    lines.append(_footer(catalog, c))
    return _reply(lines)


def _search(text, catalog, conferences):
    query = re.sub(r'第\s*\d+\s*页', '', text).strip()
    query = re.sub(r'^(?:请|帮我|麻烦)?\s*(?:搜索|查询|查找|查会议|查一下|查|看看)?\s*', '', query)
    grade = re.search(r'(?<![a-zA-Z0-9])(?:CCF\s*)?([ABCN])\s*(?:类|区|会|级)?(?![a-zA-Z0-9])', query, re.I)
    if grade:
        conferences = [c for c in conferences if c.get('rank') == grade.group(1).upper()]
        query = query[:grade.start()] + query[grade.end():]
    query = re.sub(r'会议|目录|分区|学科|领域|有哪些|有什么|全部|所有|列出|请问|的|？|\?', '', query).strip()
    if query:
        conferences = [c for c in conferences if query.casefold() in ' '.join(str(c.get(k, ''))
                       for k in ('name', 'acronym', 'id', 'area', 'areaId')).casefold()
                       or any(query.casefold() in alias.casefold() for alias in c.get('aliases', []))]
    page = _page_number(text)
    lines = [f'匹配 {len(conferences)} 场会议 · 第{page}页（每页20场）']
    for c in conferences[(page - 1) * 20:page * 20]:
        lines.append(f"{c['acronym']} · {c['rank']} · {c.get('area', '')}" + (' · 有详细数据' if c.get('detail') else ' · 详情待补'))
    if len(conferences) > page * 20:
        next_query = re.sub(r'第\s*\d+\s*页', '', text).strip() or '会议'
        lines.append(f'下一页：{next_query} 第{page + 1}页')
    if not conferences:
        lines.append('未找到。可发送完整简称、会议英文名、学科名或“A类会议”。')
    lines.append(_footer(catalog))
    return _reply(lines)


def _reminder_list(state, catalog, text, now, tz):
    rows = state.get('reminders', [])
    page = _page_number(text)
    by_id = {c['id']: c for c in _conferences(catalog)}
    lines = [f'我的提醒 · {len(rows)}条 · 第{page}页（每页8条）']
    if not rows:
        lines.append('暂无提醒。示例：提醒 CVPR 全文 提前7天')
    for row in rows[(page - 1) * 8:page * 8]:
        c = by_id.get(row.get('conferenceId'), {})
        track = next((t for t in (c.get('detail') or {}).get('tracks', [])
                      if t.get('name') == row.get('trackName')), None)
        due = reminder_due(row)
        status = reminder_problem(row, catalog) or ('已暂停' if not row.get('enabled') else
                 '触发时间已过' if due <= now else '已启用，等待触发')
        lines.append(f"{c.get('acronym', row.get('conferenceId'))} · {row.get('trackName')} · {'摘要' if row.get('kind') == 'abstract' else '全文'} · {LEADS.get(row.get('leadMinutes'), '提前量无效')}")
        if invitation_notice(track):
            lines.append(invitation_notice(track))
        lines.append(f"ID：{row.get('id')} · {status}")
        lines.append('触发：' + (_stamp(due.isoformat(), tz) if due else '无效'))
    if len(rows) > page * 8:
        lines.append(f'继续：我的提醒 第{page + 1}页')
    return _reply(lines)


def _set_reminder(text, c, state, catalog, now, tz):
    # Never silently choose a kind, lead time or track among multiple choices.
    kinds = [kind for word, kind in [('摘要', 'abstract'), ('全文', 'full')] if word in text]
    lead_match = re.search(r'提前\s*(\d+)\s*(天|小时|分钟)', text)
    lead = (int(lead_match.group(1)) * {'天': 1440, '小时': 60, '分钟': 1}[lead_match.group(2)]) if lead_match else (0 if '截止时' in text else None)
    if len(kinds) != 1 or lead not in LEADS:
        return _reply('请明确摘要或全文及提前量。例如：提醒 CVPR 全文 提前7天。支持7天、3天、1天、3小时、1小时、5分钟、截止时。')
    tracks = _tracks(c, text)
    if len(tracks) != 1:
        lines = [f"{c['acronym']} 有多个 Track，请指定“第N轨”；不会自动替你选择。" if tracks else '没有可设置的已核验 Track。']
        lines += [f"第{i}轨 · {t['name']}" + (' · 仅限获邀' if invitation_notice(t) else '') for i, t in tracks]
        return _reply(lines)
    _, track = tracks[0]
    kind = kinds[0]
    deadline = track.get(kind + 'Deadline')
    due = reminder_due({'deadline': deadline, 'leadMinutes': lead})
    if due is None:
        return _reply('该节点日期尚未核验，暂不能设置提醒。')
    if due <= now:
        return _reply('该提前量对应的提醒时间已过。请选择更接近截止的提前量，或查询其他会议。')
    existing = deepcopy(state.get('reminders', []))
    same = lambda r: (r.get('conferenceId'), r.get('trackName'), r.get('kind'), r.get('leadMinutes')) == (c['id'], track['name'], kind, lead)
    old = next((r for r in existing if same(r)), None)
    identifier = (old or {}).get('id') or 'wx-' + hashlib.sha256(f"{c['id']}|{track['name']}|{kind}|{lead}".encode()).hexdigest()[:24]
    rows = [r for r in existing if not same(r)]
    if len(rows) >= 200:
        return _reply('提醒已达到200条上限，请删除不再需要的提醒。')
    row = {'id': identifier, 'conferenceId': c['id'], 'trackName': track['name'], 'kind': kind,
           'deadline': deadline, 'leadMinutes': lead, 'enabled': True}
    rows.append(row)
    favorites = list(dict.fromkeys([*state.get('favorites', []), c['id']]))
    if len(favorites) > 1000:
        return _reply('收藏已达到1000条上限，暂不能为新会议添加提醒。请先取消不再需要的收藏。')
    lines = [f"已保存 {c['acronym']} · {track['name']} · {'摘要' if kind == 'abstract' else '全文'} · {LEADS[lead]}",
             '触发：' + _stamp(due.isoformat(), tz), 'ID：' + identifier,
             '已同时收藏会议。微信推送还需扫码绑定并开启“只推送 DDL 提醒”，本机服务需保持运行。']
    if invitation_notice(track):
        lines.insert(1, invitation_notice(track))
    if track.get('deadlineConflict'):
        lines.append('注意：当前日期与官网存在冲突。请先查询该会议“截止”核对已记录说明。')
    return _reply(lines, {'favorites': favorites, 'reminders': rows})


def _upcoming(text, catalog, state, now, tz):
    conferences = _conferences(catalog)
    if '收藏' in text:
        conferences = [c for c in conferences if c['id'] in state.get('favorites', [])]
    day_match = re.search(r'(?:未来|近|接下来)\s*(\d+)\s*天', text)
    days = int(day_match.group(1)) if day_match else 30
    if not 1 <= days <= 366:
        return _reply('查询范围请设为1至366天。')
    if any(word in text for word in ('本月', '这个月')):
        local = now.astimezone(tz)
        end = local.replace(year=local.year + (local.month == 12), month=local.month % 12 + 1, day=1,
                            hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    else:
        end = now + timedelta(days=days)
    nodes = []
    for c in conferences:
        for index, track in enumerate(c.get('detail', {}).get('tracks', []), 1):
            if track.get('submissionStage') == 'invitation-only' or track.get('deadlineMode') == 'rolling':
                continue
            for kind, label in [('abstract', '摘要'), ('full', '全文')]:
                value = track.get(kind + 'Deadline')
                parsed = _parse_date(value)
                if parsed and now < parsed < end:
                    nodes.append((parsed, c, index, track, label, value))
    nodes.sort(key=lambda n: (n[0], n[1]['id'], n[2], n[4]))
    page = _page_number(text)
    lines = [f"即将截止 · {len(nodes)}个已核验节点 · 至{_stamp(end.isoformat(), tz)} · 第{page}页"]
    for _, c, index, track, label, value in nodes[(page - 1) * 10:page * 10]:
        lines.append(f"{c['acronym']} · {c['rank']} · 第{index}轨 {track['name']} · {label}")
        lines.append(f'{_stamp(value, tz)} · {_countdown(value, now)}' + (' · 官方时间有冲突，请查截止详情' if track.get('deadlineConflict') else ''))
    if not nodes:
        lines.append('此范围没有已核验的未来节点；不代表所有会议都没有截止安排。')
    if len(nodes) > page * 10:
        query = re.sub(r'第\s*\d+\s*页', '', text).strip()
        lines.append(f'继续：{query} 第{page + 1}页')
    lines += ['只列有精确时刻的节点；仅日期、滚动和获邀阶段不计入本查询，见会议详情。', _footer(catalog)]
    return _reply(lines)


def execute(text, catalog, state, now=None):
    """Parse one message; return reply plus an atomic account-state patch.

    ``now`` may be an aware datetime, ISO timestamp or Unix seconds. ``catalog``
    is the full conferences.json document. ``state`` is the authenticated
    account's normal state. No input object is modified.
    """
    if not isinstance(text, str) or not text.strip():
        return _reply('请发送文字，例如“ACL 截止”或“帮助”。')
    if len(text) > 2000:
        return _reply('消息过长，请将查询缩短到2000字以内。')
    text = text.strip().strip('。！!？?').strip()
    now = _now(now)
    try:
        tz = ZoneInfo(state.get('settings', {}).get('timezone', 'Asia/Singapore'))
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        tz = UTC
    conferences = _conferences(catalog)
    if text.lower() in ('帮助', '菜单', '功能', 'help', '/help', '开始', '你好', '会投', '会投助手'):
        return _reply(HELP)
    if re.fullmatch(r'我的提醒(?:\s*第\s*\d+\s*页)?', text):
        return _reminder_list(state, catalog, text, now, tz)
    if text in ('暂停全部提醒', '暂停所有提醒'):
        rows = deepcopy(state.get('reminders', []))
        for row in rows:
            row['enabled'] = False
        return _reply(f'已暂停全部{len(rows)}条提醒。可用“恢复提醒 ID”逐条恢复。', {'reminders': rows})
    action = re.fullmatch(r'(暂停|恢复|删除)提醒\s+([A-Za-z0-9][A-Za-z0-9_.:-]{0,159})', text)
    if action:
        verb, identifier = action.groups()
        rows = deepcopy(state.get('reminders', []))
        row = next((r for r in rows if r.get('id') == identifier), None)
        if row is None:
            return _reply('当前账号没有这条提醒。请发送“我的提醒”查看 ID。')
        if verb == '删除':
            rows.remove(row)
        elif verb == '恢复':
            problem = reminder_problem(row, catalog)
            if problem or reminder_due(row) <= now:
                return _reply((problem or '提醒时间已过') + '，请重新设置提醒。')
            row['enabled'] = True
        else:
            row['enabled'] = False
        return _reply(f'已{verb}提醒 {identifier}。', {'reminders': rows})
    favorite = re.fullmatch(r'(收藏|取消收藏)\s*(.+)', text)
    if favorite:
        verb, target = favorite.groups()
        matches = _mentions(target, conferences)
        # A mutation target must itself be a known alias, not a phrase that
        # merely mentions one (e.g. 收藏 ACL 吗 / 不要收藏 ACL).
        exact = [c for c in matches if target.casefold() in
                 [str(c.get(k, '')).casefold() for k in ('id', 'acronym', 'displayName')]
                 + [a.casefold() for a in c.get('aliases', [])]]
        if len(exact) != 1:
            return _reply('请明确一场会议，例如“收藏 AAAI”或“取消收藏 AAAI”。')
        c = exact[0]
        favorites = list(dict.fromkeys(state.get('favorites', [])))
        if verb == '收藏':
            if c['id'] not in favorites:
                if len(favorites) >= 1000:
                    return _reply('收藏已达到1000条上限，请先取消不再需要的收藏。')
                favorites.append(c['id'])
            return _reply(f"已收藏 {c['acronym']}。收藏不会自动创建提醒，可发送“提醒 {c['acronym']} 全文 提前7天”。", {'favorites': favorites})
        favorites = [v for v in favorites if v != c['id']]
        rows = deepcopy(state.get('reminders', []))
        for row in rows:
            if row.get('conferenceId') == c['id']:
                row['enabled'] = False
        return _reply(f"已取消收藏 {c['acronym']}，并暂停其全部提醒。", {'favorites': favorites, 'reminders': rows})
    if re.fullmatch(r'我的收藏(?:\s*第\s*\d+\s*页)?', text):
        selected = [c for c in conferences if c['id'] in state.get('favorites', [])]
        return _search('会议 第' + str(_page_number(text)) + '页', catalog, selected)
    if re.search(r'(?:未来|接下来|近)\s*\d+\s*天|本月|这个月|收藏.*(?:截止|ddl)|(?:近期|最近).*截止', text, re.I):
        return _upcoming(text, catalog, state, now, tz)
    matches = _mentions(text, conferences)
    if len(matches) > 1:
        return _reply('匹配到多场会议，请每次指定一场：' + '、'.join(c['acronym'] for c in matches))
    if text.startswith('提醒 '):
        command = re.fullmatch(r'提醒\s+(.+?)\s+(?:第\s*\d{1,3}\s*(?:轨|个?\s*[Tt]rack)\s+)?(?:摘要|全文)\s+(?:提前\s*\d+\s*(?:天|小时|分钟)|截止时)', text)
        aliases = ([str(matches[0].get(k, '')).casefold() for k in ('id', 'acronym', 'displayName')]
                   + [a.casefold() for a in matches[0].get('aliases', [])]) if len(matches) == 1 else []
        if command is None or command.group(1).casefold() not in aliases:
            return _reply('请使用明确格式。例如：提醒 CVPR 全文 提前7天；多Track：提醒 ACL 第1轨 全文 提前1天。')
        return _set_reminder(text, matches[0], state, catalog, now, tz)
    if any(word in text for word in ('提醒', '收藏', '删除', '暂停', '恢复')):
        return _reply('未执行修改。请使用明确指令，例如“收藏 AAAI”“提醒 CVPR 全文 提前7天”或“我的提醒”。发送“帮助”查看完整格式。')
    if matches:
        return _detail(matches[0], text, catalog, now, tz)
    return _search(text, catalog, conferences)
