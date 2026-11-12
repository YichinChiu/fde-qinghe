"""Qinghe customer layer: profiling, adaptation and reconciliation.

The harness handles IO. Everything here is customer-specific judgement:
what counts as missing, how codes are normalised, which rows are suspicious.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import re
import unicodedata

CONTRACT_VERSION = 'w04-0.1.0'

MEMBER = 'crm_member_export.csv'
ORDER = 'crm_order_export.csv'
CARD = 'crm_card_export.csv'
SHOP = 'crm_shop.csv'
DND_LIST = '小林工作账_勿扰名单.csv'
CALLBACK_LIST = '小林工作账_回访名单.csv'

MISSING = {'', 'NULL', '-', '无'}
SAMPLE_LIMIT = 20

# CRM data dictionary v2.3 as published by IT (2023-05-26). Used when the supplied
# dictionary text has no field tables (e.g. the public practice dictionary), and as
# the baseline the parsed dictionary is merged onto.
DICTIONARY_V23 = {
    MEMBER: {
        'hy_id': {'type': '文本', 'note': 'QH 加 8 位数字，唯一'},
        'nm': {'type': '文本', 'note': ''},
        'mobile': {'type': '文本', 'note': '11 位'},
        'birth': {'type': '日期', 'note': '可为空'},
        'join_dt': {'type': '日期', 'note': '会员注册的日期'},
        'lv': {'type': '代码', 'note': '1 普通，2 银卡，3 金卡'},
        'stat': {'type': '代码', 'note': '1 正常，2 冻结，3 注销'},
        'src_ch': {'type': '文本', 'note': '门店、小程序、商城'},
        'reg_shop': {'type': '文本', 'note': '门店编码，4 位数字，见门店表'},
        'tag': {'type': '文本', 'note': '多个标签用逗号分隔，取值见附录标签表'},
    },
    ORDER: {
        'ord_no': {'type': '文本', 'note': '唯一'},
        'hy_id': {'type': '文本', 'note': '见会员表'},
        'shop_cd': {'type': '文本', 'note': '门店编码，见门店表'},
        'ord_tm': {'type': '日期时间', 'note': ''},
        'ord_stat': {'type': '文本', 'note': '已支付、已完成、部分退款、全额退款、已取消'},
        'amt_total': {'type': '整数', 'note': '单位：分'},
        'amt_pay': {'type': '整数', 'note': '单位：分'},
        'amt_rfd': {'type': '整数', 'note': '单位：分'},
        'qty': {'type': '整数', 'note': ''},
        'ch': {'type': '文本', 'note': '门店、小程序、商城'},
    },
    CARD: {
        'card_no': {'type': '文本', 'note': '唯一'},
        'hy_id': {'type': '文本', 'note': '见会员表'},
        'card_kind': {'type': '文本', 'note': '悦享卡（年）、家庭季卡、异业联名卡、体验卡'},
        'st_dt': {'type': '日期', 'note': ''},
        'ed_dt': {'type': '日期', 'note': ''},
        'stop_dt': {'type': '日期', 'note': '可为空'},
        'pay_amt': {'type': '整数', 'note': '单位：分'},
    },
    SHOP: {
        'shop_cd': {'type': '文本', 'note': '4 位数字，唯一'},
        'shop_nm': {'type': '文本', 'note': ''},
        'area': {'type': '文本', 'note': '华东、华南、华北'},
        'open_dt': {'type': '日期', 'note': ''},
        'shop_stat': {'type': '文本', 'note': '营业、闭店'},
    },
}
TAGS_V23 = ['高价值', '价格敏感', '宠物', '生鲜偏好', '母婴-0到3岁', '母婴-3到6岁', '周末家庭',
            '学生', '企业团购', '流失预警', '积分达人', '门店偏好']

# Free-text in the tag field that restricts contact. Used only for profiling counts here.
CONTACT_RESTRICTION = re.compile(r'勿扰|勿打|勿发|不要打|不要发|别打|别发|不再联系|拒绝(电话|短信|联系)|免打扰|投诉')
TAG_SEPARATORS = re.compile(r'[,，;；/]|\s+')


# ---------------------------------------------------------------- value helpers

def is_missing(value):
    return value is None or value.strip() in MISSING


def normalize_code(value):
    """Full-width digits/letters and stray (ideographic) spaces → canonical upper-case code."""
    return unicodedata.normalize('NFKC', value).strip().upper()


DATE_FORMATS = ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d')
DATETIME_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S')


def parse_date(value):
    text = value.strip()
    for fmt in DATE_FORMATS + DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def value_kind(value):
    text = value.strip()
    if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2} \d{1,2}:\d{2}:\d{2}', text):
        return 'datetime'
    if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', text):
        return 'date'
    if re.fullmatch(r'-?\d+', text):
        return 'integer'
    if re.fullmatch(r'-?\d+\.\d+', text):
        return 'decimal'
    return 'string'


def to_decimal(value):
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None
    return number if number.is_finite() else None


def rows_of(tables, name):
    table = tables.get(name)
    return table['rows'] if table else []


def sample(rows):
    return sorted(rows)[:SAMPLE_LIMIT]


# ---------------------------------------------------------------- dictionary

def parse_dictionary(text):
    """Read field tables and the tag appendix from the dictionary markdown.

    Falls back to v2.3 for any table the text does not describe.
    """
    spec = {name: dict(fields) for name, fields in DICTIONARY_V23.items()}
    tags = list(TAGS_V23)
    current = None
    parsed_tags = []
    in_tag_table = False
    for line in text.splitlines():
        heading = re.match(r'#+\s*(.+)', line)
        if heading:
            title = heading.group(1)
            table = re.search(r'(crm_[a-z_]+)', title)
            current = f'{table.group(1)}.csv' if table else None
            in_tag_table = '标签' in title and current is None
            if current:
                spec[current] = {}
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')] if line.strip().startswith('|') else None
        if not cells or set(''.join(cells)) <= set('- :'):
            continue
        if current and len(cells) >= 4:
            field = cells[0].strip('`')
            if field and field != '字段':
                spec[current][field] = {'type': cells[2], 'note': cells[3]}
        elif in_tag_table and cells[0] not in ('标签', ''):
            parsed_tags.append(cells[0])
    if parsed_tags:
        tags = parsed_tags
    for name in list(spec):
        if not spec[name]:
            spec[name] = dict(DICTIONARY_V23.get(name, {}))
    return spec, tags


def enumerated_values(entry):
    """Allowed values declared in a dictionary note: code pairs or 、-separated lists."""
    note = entry['note']
    if entry['type'] == '代码':
        pairs = re.findall(r'(\d+)\s*([^\s，,；;0-9]+)', note)
        return {'codes': {code: label for code, label in pairs}} if pairs else None
    if '、' in note and '，' not in note and '见' not in note:
        return {'values': [v.strip() for v in note.split('、') if v.strip()]}
    return None


# ---------------------------------------------------------------- field statistics

def field_statistics(filename, table):
    stats = []
    for field in table['fields']:
        values = [row['raw'].get(field, '') for row in table['rows']]
        present = [v for v in values if not is_missing(v)]
        kinds = Counter(value_kind(v) for v in present)
        inferred = kinds.most_common(1)[0][0] if kinds else 'string'
        if inferred == 'integer' and kinds.get('decimal'):
            inferred = 'decimal'
        if len(kinds) > 1 and inferred in ('date', 'datetime') or (inferred == 'integer' and kinds.get('date')):
            inferred = 'date(mixed formats)'
        stat = {'source_file': filename, 'field': field, 'inferred_type': inferred,
                'total_count': len(values), 'missing_count': len(values) - len(present)}
        counts = Counter(values)
        if 0 < len(counts) <= 30:
            stat['distribution'] = [{'value': v, 'count': n} for v, n in sorted(counts.items())]
        else:
            stat['range'] = value_range(present, inferred)
        stats.append(stat)
    return stats


def value_range(present, inferred):
    if not present:
        return {'min': None, 'max': None}
    if inferred in ('integer', 'decimal'):
        numbers = [n for n in (to_decimal(v) for v in present) if n is not None]
        if numbers:
            return {'min': str(min(numbers)), 'max': str(max(numbers))}
    if inferred.startswith('date'):
        parsed = [d for d in (parse_date(v) for v in present) if d is not None]
        if parsed:
            fmt = '%Y-%m-%d %H:%M:%S' if inferred == 'datetime' else '%Y-%m-%d'
            return {'min': min(parsed).strftime(fmt), 'max': max(parsed).strftime(fmt)}
    return {'min': min(present), 'max': max(present)}


# ---------------------------------------------------------------- anomaly detectors
# Each detector returns (anomalies, differences). Rows are 1-based record numbers
# from the harness (header excluded), so every finding can be traced back to the CSV.

def anomaly(pattern, filename, rows, query=None):
    evidence = {'source_file': filename, 'sample_rows': sample(rows)}
    if query:
        evidence['query'] = query
    return {'pattern': pattern, 'evidence': evidence}


def difference(filename, field, claim, actual, impact):
    return {'source_file': filename, 'field': field, 'dictionary_claim': claim, 'actual': actual, 'impact': impact}


def detect_duplicates(tables, spec):
    out, diffs = [], []
    for filename, table in tables.items():
        seen = {}
        exact = []
        for row in table['rows']:
            key = tuple(sorted(row['raw'].items()))
            if key in seen:
                exact.append(row['source_row'])
            else:
                seen[key] = row['source_row']
        if exact:
            boundary = sum(1 for r in exact if (r - 1) % 1000 < 5)
            hint = f'，其中 {boundary} 条紧跟每 1000 条分页边界（疑似分页导出重叠）' if len(exact) >= 10 and boundary >= len(exact) / 2 else ''
            out.append(anomaly(f'完全重复行：{len(exact)} 条与前文记录逐字段相同{hint}', filename, exact))
        unique_fields = [f for f, e in spec.get(filename, {}).items() if '唯一' in e['note'] and f in table['fields']]
        for field in unique_fields:
            first = {}
            conflicting = []
            for row in table['rows']:
                value = row['raw'][field]
                if is_missing(value):
                    continue
                if value in first and first[value]['raw'] != row['raw']:
                    conflicting.append(row['source_row'])
                first.setdefault(value, row)
            if conflicting:
                out.append(anomaly(f'主键重复但内容不同：{field} 有 {len(conflicting)} 条重复编号对应不同记录', filename, conflicting))
            dup_total = len(exact) + len(conflicting)
            if dup_total and field == table['fields'][0]:
                diffs.append(difference(filename, field, '唯一', f'{dup_total} 条记录编号重复（完全相同 {len(exact)} 条，内容不同 {len(conflicting)} 条）',
                                        '按主键去重前会重复计入订单数和金额；完全相同的按分页重叠去重，内容不同的隔离待核'))
    return out, diffs


def detect_code_formats(tables, spec):
    """Store codes: whitespace / full-width / lower-case noise vs. genuinely new letter-prefixed codes."""
    out, diffs = [], []
    targets = [(SHOP, 'shop_cd'), (MEMBER, 'reg_shop'), (ORDER, 'shop_cd')]
    for filename, field in targets:
        rows = rows_of(tables, filename)
        if not rows or field not in tables[filename]['fields']:
            continue
        noisy, letters = [], []
        for row in rows:
            raw = row['raw'][field]
            if is_missing(raw):
                continue
            norm = normalize_code(raw)
            if norm != raw:
                noisy.append(row['source_row'])
            if re.fullmatch(r'[A-Z]\d{3}', norm):
                letters.append(row['source_row'])
        if noisy:
            out.append(anomaly(f'门店编码格式不一：{field} 有 {len(noisy)} 条含首尾空格、全角数字或小写字母，规范化后才能关联门店表', filename, noisy))
        if letters:
            out.append(anomaly(f'门店编码出现字母开头：{field} 有 {len(letters)} 条形如 A446 的编码，不是字典写的 4 位数字', filename, letters))
        claim = spec.get(filename, {}).get(field, {}).get('note', '')
        if letters and '4 位数字' in (claim or spec.get(SHOP, {}).get('shop_cd', {}).get('note', '')):
            extra = ''
            if filename == SHOP:
                opened = sorted(parse_date(r['raw']['open_dt']) for r in rows
                                if re.fullmatch(r'[A-Z]\d{3}', normalize_code(r['raw'][field])) and parse_date(r['raw']['open_dt']))
                if opened:
                    extra = f'，这些门店开业日期在 {opened[0]:%Y-%m-%d} 至 {opened[-1]:%Y-%m-%d}'
            diffs.append(difference(filename, field, '4 位数字门店编码', f'{len(letters)} 条为“字母+3 位数字”编码{extra}；另有 {len(noisy)} 条只是空格/全角/大小写写法不同',
                                    '按 4 位数字校验会把新编码门店的订单和会员误判为无效；写法差异在映射时规范化，字母编码保留并请客户确认编码规则'))
    return out, diffs


def detect_references(tables):
    out, diffs = [], []
    members = {r['raw']['hy_id'] for r in rows_of(tables, MEMBER)}
    shops = {normalize_code(r['raw']['shop_cd']) for r in rows_of(tables, SHOP)}
    if MEMBER in tables:
        for filename in (ORDER, CARD):
            rows = rows_of(tables, filename)
            orphans = [r['source_row'] for r in rows if r['raw']['hy_id'] not in members]
            if orphans:
                ids = {rows[i - 1]['raw']['hy_id'] for i in orphans}
                in_range = ''
                numbers = sorted(int(m[2:]) for m in members if re.fullmatch(r'QH\d{8}', m))
                if numbers:
                    inside = sum(1 for m in ids if re.fullmatch(r'QH\d{8}', m) and numbers[0] <= int(m[2:]) <= numbers[-1])
                    gaps = numbers[-1] - numbers[0] + 1 - len(numbers)
                    if inside:
                        in_range = f'；其中 {inside} 个会员号落在会员表编号区间内（会员表区间内缺号 {gaps} 个），疑似会员导出缺页'
                out.append(anomaly(f'孤儿{"订单" if filename == ORDER else "会员卡"}：{len(orphans)} 条记录的会员号在会员表中找不到关联（涉及 {len(ids)} 个会员号{in_range}）',
                                   filename, orphans))
                diffs.append(difference(filename, 'hy_id', '见会员表（应能关联到会员）', f'{len(orphans)} 条记录关联不到会员表，涉及 {len(ids)} 个会员号',
                                        '这些会员的属性、标签、注册信息暂缺；不能算作“无会员”，隔离并写入覆盖说明，向 IT 要补导'))
    if SHOP in tables:
        for filename, field in ((ORDER, 'shop_cd'), (MEMBER, 'reg_shop')):
            rows = rows_of(tables, filename)
            orphans = [r['source_row'] for r in rows if not is_missing(r['raw'][field]) and normalize_code(r['raw'][field]) not in shops]
            if orphans:
                out.append(anomaly(f'门店关联失败：{field} 有 {len(orphans)} 条规范化后仍找不到门店表', filename, orphans))
    return out, diffs


def detect_dates(tables, spec):
    out, diffs = [], []
    for filename, table in tables.items():
        for field, entry in spec.get(filename, {}).items():
            if field not in table['fields'] or '日期' not in entry['type']:
                continue
            non_iso, invalid = defaultdict(list), []
            expected = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}' if entry['type'] == '日期时间' else r'\d{4}-\d{2}-\d{2}'
            for row in table['rows']:
                value = row['raw'][field]
                if is_missing(value):
                    continue
                if parse_date(value) is None:
                    invalid.append(row['source_row'])
                elif not re.fullmatch(expected, value.strip()):
                    style = 'YYYY/MM/DD' if '/' in value else 'YYYYMMDD' if re.fullmatch(r'\d{8}', value.strip()) else '其他'
                    non_iso[style].append(row['source_row'])
            if invalid:
                out.append(anomaly(f'无效日期：{field} 有 {len(invalid)} 条无法解析为真实日期（如 2 月 30 日）', filename, invalid))
            if non_iso:
                rows = [r for group in non_iso.values() for r in group]
                styles = '、'.join(f'{k} {len(v)} 条' for k, v in non_iso.items())
                out.append(anomaly(f'日期格式混用：{field} 有 {len(rows)} 条不是 ISO 写法（{styles}）', filename, rows))
                diffs.append(difference(filename, field, f'{entry["type"]}（未注明格式，其余记录为 ISO）', f'{len(rows)} 条使用 {styles}',
                                        '按单一格式解析会丢失或误判这些记录的日期；适配时多格式显式解析，统一为 ISO'))
    # order number embeds the order date: cross-check against ord_tm
    rows = rows_of(tables, ORDER)
    mismatched = []
    for row in rows:
        number, stamp = row['raw'].get('ord_no', ''), row['raw'].get('ord_tm', '')
        embedded = re.match(r'O(\d{8})', number)
        if embedded and stamp[:10].replace('-', '') != embedded.group(1):
            mismatched.append(row['source_row'])
    if mismatched:
        out.append(anomaly(f'订单号内嵌日期与 ord_tm 不一致：{len(mismatched)} 条', ORDER, mismatched))
    return out, diffs


def detect_enumerations(tables, spec):
    out, diffs = [], []
    for filename, table in tables.items():
        for field, entry in spec.get(filename, {}).items():
            if field not in table['fields']:
                continue
            allowed = enumerated_values(entry)
            if not allowed:
                continue
            counts = Counter(r['raw'][field] for r in table['rows'] if not is_missing(r['raw'][field]))
            if not counts:
                continue
            if 'codes' in allowed:
                codes, labels = allowed['codes'], set(allowed['codes'].values())
                as_labels = {v: n for v, n in counts.items() if v in labels}
                unknown = {v: n for v, n in counts.items() if v not in codes and v not in labels}
                if as_labels and not any(v in codes for v in counts):
                    diffs.append(difference(filename, field, f'代码：{entry["note"]}', f'实际存中文名称而非代码：{format_counts(as_labels)}',
                                            '映射时按名称取值，不能按 1/2/3 代码翻译，否则全部落空'))
                if unknown:
                    rows = [r['source_row'] for r in table['rows'] if r['raw'][field] in unknown]
                    out.append(anomaly(f'字典外代码：{field} 出现 {format_counts(unknown)}，字典只定义 {"、".join(codes)}', filename, rows))
                    diffs.append(difference(filename, field, f'代码：{entry["note"]}', f'另有字典未定义的取值 {format_counts(unknown)}',
                                            '含义不明的状态不能并入“正常”或丢弃；保留原值，影响活跃会员数等口径，需向 IT 确认含义'))
            else:
                values = allowed['values']
                unknown = {v: n for v, n in counts.items() if v not in values}
                if unknown:
                    rows = [r['source_row'] for r in table['rows'] if r['raw'][field] in unknown]
                    out.append(anomaly(f'字典外取值：{field} 出现 {format_counts(unknown)}', filename, rows))
                    diffs.append(difference(filename, field, '、'.join(values), f'另有字典未列的取值 {format_counts(unknown)}',
                                            enumeration_impact(filename, field, unknown, values)))
    return out, diffs


def enumeration_impact(filename, field, unknown, values):
    if field == 'card_kind':
        return '同一卡种存在新旧两种名称，需合并映射后再按卡种统计；字典外卡种（如员工卡）是否计入付费会员需客户确认'
    if field == 'src_ch':
        return '“系统导入”不是会员真实注册渠道，按渠道统计新会员会失真；需向 IT 确认迁移批次的原始渠道'
    if field == 'area':
        return '按大区汇总时字典外大区不能丢弃；需按实际大区更新字典'
    return '字典外取值不能直接丢弃，按原值保留并请客户确认含义'


def format_counts(counts):
    return '、'.join(f'{v} {n} 条' for v, n in sorted(counts.items(), key=lambda kv: -kv[1]))


def detect_amounts(tables, spec):
    out, diffs = [], []
    for filename, table in tables.items():
        for field, entry in spec.get(filename, {}).items():
            if field not in table['fields'] or not re.search(r'单位[:：]\s*分', entry['note']):
                continue
            decimals = [r['source_row'] for r in table['rows'] if '.' in r['raw'][field]]
            if decimals:
                example = table['rows'][decimals[0] - 1]['raw'][field]
                out.append(anomaly(f'金额带小数：{field} 有 {len(decimals)} 条带两位小数（如 {example}），与字典“整数分”不符', filename, decimals))
                diffs.append(difference(filename, field, f'{entry["type"]}，{entry["note"]}', f'{len(decimals)}/{len(table["rows"])} 条为带两位小数的元，如 {example}',
                                        '若按“分”读入，所有金额缩小 100 倍；映射时按元×100 转为整数分'))
    rows = rows_of(tables, ORDER)
    over_refund, status_mismatch, cancelled_paid = [], [], []
    for row in rows:
        raw = row['raw']
        total, paid, refund = (to_decimal(raw.get(k, '')) for k in ('amt_total', 'amt_pay', 'amt_rfd'))
        if None in (total, paid, refund):
            continue
        status = raw.get('ord_stat')
        if refund > paid:
            over_refund.append(row['source_row'])
        if status == '全额退款' and refund != paid or status in ('已完成', '已支付') and refund != 0:
            status_mismatch.append(row['source_row'])
        if status == '已取消' and (paid != 0 or refund != 0):
            cancelled_paid.append(row['source_row'])
    if over_refund:
        out.append(anomaly(f'退款金额大于实付：{len(over_refund)} 条订单 amt_rfd > amt_pay（净消费为负）', ORDER, over_refund))
    if status_mismatch:
        out.append(anomaly(f'订单状态与退款金额矛盾：{len(status_mismatch)} 条', ORDER, status_mismatch))
    if cancelled_paid:
        out.append(anomaly(f'已取消订单仍有实付或退款：{len(cancelled_paid)} 条', ORDER, cancelled_paid))
    big = [r['source_row'] for r in rows if (to_decimal(r['raw'].get('qty', '')) or 0) > 50]
    if big:
        out.append(anomaly(f'件数异常大：{len(big)} 条订单 qty > 50，疑似团购或录入错误', ORDER, big))
    if CARD in tables:
        free = [r['source_row'] for r in rows_of(tables, CARD) if (to_decimal(r['raw'].get('pay_amt', '')) or 1) == 0]
        if free:
            out.append(anomaly(f'购卡实付为 0：{len(free)} 张卡', CARD, free))
    return out, diffs


def detect_tags(tables, tag_list):
    rows = rows_of(tables, MEMBER)
    if not rows or 'tag' not in tables[MEMBER]['fields']:
        return [], []
    out, diffs = [], []
    known = set(tag_list)
    other_separators, notes, unknown_tokens, restricted = [], [], Counter(), []
    placeholder = defaultdict(list)
    for row in rows:
        text = row['raw']['tag']
        if is_missing(text):
            if text.strip():
                placeholder[text.strip()].append(row['source_row'])
            continue
        if re.search(r'[，;；/]|\s', text):
            other_separators.append(row['source_row'])
        tokens = [t.strip() for t in TAG_SEPARATORS.split(text) if t.strip()]
        if any(t not in known for t in tokens):
            notes.append(row['source_row'])
            unknown_tokens.update(t for t in tokens if t not in known)
        if CONTACT_RESTRICTION.search(text):
            restricted.append(row['source_row'])
    if placeholder:
        out.append(anomaly(f'空值写法不一：tag 用 {format_counts({k: len(v) for k, v in placeholder.items()})} 表示无标签', MEMBER,
                           [r for v in placeholder.values() for r in v]))
    if other_separators:
        out.append(anomaly(f'标签分隔符混用：{len(other_separators)} 条使用中文逗号、分号、斜杠或空格分隔', MEMBER, other_separators))
        diffs.append(difference(MEMBER, 'tag', '多个标签用逗号分隔', f'{len(other_separators)} 条还用了“，”“;”“；”“/”或空格分隔',
                                '只按英文逗号拆分会把多个标签粘成一个未知值；拆分时连字符不能作分隔符（母婴-0到3岁 是合法标签）'))
    if notes:
        top = '、'.join(t for t, _ in unknown_tokens.most_common(8))
        out.append(anomaly(f'标签字段混入备注：{len(notes)} 条含附录标签表以外的内容（{len(unknown_tokens)} 种，常见：{top}）', MEMBER, notes))
        diffs.append(difference(MEMBER, 'tag', f'取值见附录标签表（{len(known)} 个）',
                                f'{len(notes)} 条含表外内容 {len(unknown_tokens)} 种，常见：{top}；其中既有疑似新标签，也有带句号或“类别-内容”写法的手写备注',
                                '不能当无效值删除；确认过的新标签进标签表，备注整条保留原文和来源，触达限制类备注必须识别出来'))
    if restricted:
        out.append(anomaly(f'标签字段含触达限制备注：{len(restricted)} 条（如 勿打电话、勿发短信），字典未定义此类内容', MEMBER, restricted))
    return out, diffs


def detect_member_quality(tables):
    rows = rows_of(tables, MEMBER)
    if not rows:
        return [], []
    out, diffs = [], []
    fields = tables[MEMBER]['fields']
    if 'nm' in fields:
        generic = [r['source_row'] for r in rows if r['raw']['nm'].strip() == '顾客']
        if generic:
            out.append(anomaly(f'姓名为占位词“顾客”：{len(generic)} 条', MEMBER, generic))
    if 'mobile' in fields:
        masked = [r['source_row'] for r in rows if '*' in r['raw']['mobile']]
        if masked:
            shared = Counter(r['raw']['mobile'] for r in rows)
            dup = sum(n for n in shared.values() if n > 1)
            out.append(anomaly(f'手机号已脱敏：{len(masked)} 条中间四位为 ****，脱敏后 {dup} 条与他人重号，无法用手机号识别同一人', MEMBER, masked))
            diffs.append(difference(MEMBER, 'mobile', '11 位手机号', f'{len(masked)} 条为 3+****+4 脱敏格式（按公司规定）',
                                    '不能用手机号做身份合并或触达；身份合并只能依赖会员号'))
    if {'create_tm', 'src_ch'} <= set(fields):
        burst = Counter(r['raw']['create_tm'][:10] for r in rows)
        day, n = burst.most_common(1)[0]
        imported = [r['source_row'] for r in rows if r['raw']['src_ch'] == '系统导入']
        if imported:
            later = sum(1 for r in rows if r['raw']['src_ch'] == '系统导入' and r['raw']['create_tm'][:10] != r['raw'].get('join_dt', '')[:10])
            out.append(anomaly(f'系统迁移批次：{len(imported)} 条注册渠道为“系统导入”，create_tm 集中在 {day} 前后（当日 {n} 条），reg_dev 为空；create_tm 晚于 join_dt 的有 {later} 条',
                               MEMBER, imported))
        extra = [f for f in fields if f not in DICTIONARY_V23[MEMBER]]
        if extra:
            diffs.append(difference(MEMBER, '、'.join(extra), '字典未定义该字段', f'导出含字典外字段 {"、".join(extra)}；create_tm 是建档时间，迁移会员的 create_tm 是迁移日期',
                                    '注册日期必须用 join_dt，不能用 create_tm，否则迁移会员会被算成 2025 年 3 月的新会员'))
    return out, diffs


def detect_shops(tables):
    shops = rows_of(tables, SHOP)
    if not shops:
        return [], []
    out = []
    names = defaultdict(list)
    for r in shops:
        names[r['raw']['shop_nm']].append(r['source_row'])
    repeated = [row for rows in names.values() if len(rows) > 1 for row in rows]
    if repeated:
        out.append(anomaly(f'门店名称重复：{sum(1 for v in names.values() if len(v) > 1)} 个店名对应多个门店编码，共 {len(repeated)} 条', SHOP, repeated))
    closed = {normalize_code(r['raw']['shop_cd']) for r in shops if r['raw'].get('shop_stat') == '闭店'}
    if closed:
        orders = [r['source_row'] for r in rows_of(tables, ORDER) if normalize_code(r['raw']['shop_cd']) in closed]
        if orders:
            out.append(anomaly(f'闭店门店仍有订单：{len(orders)} 条订单发生在 {len(closed)} 家闭店门店，门店表没有闭店日期，无法判断订单是否在闭店之后',
                               ORDER, orders))
    return out, []


def detect_workbook(tables):
    """Xiaolin's spreadsheets are cross-checked only; they may be absent (public sample)."""
    dnd = rows_of(tables, DND_LIST)
    members = {r['raw']['hy_id']: r for r in rows_of(tables, MEMBER)}
    if not dnd or not members:
        return [], []
    unmatched, unflagged = [], []
    for r in dnd:
        member = members.get(r['raw'].get('会员号'))
        if member is None:
            unmatched.append(r['source_row'])
        elif not CONTACT_RESTRICTION.search(member['raw'].get('tag', '')):
            unflagged.append(r['source_row'])
    out = []
    if unflagged:
        out.append(anomaly(f'勿扰名单与 CRM 不一致：工作账 {len(unflagged)} 人在 CRM 标签/备注里没有触达限制记录', DND_LIST, unflagged))
    if unmatched:
        out.append(anomaly(f'勿扰名单会员号在 CRM 会员表中找不到：{len(unmatched)} 人', DND_LIST, unmatched))
    return out, []


def detect_missing_placeholders(tables):
    out = []
    for filename, table in tables.items():
        for field in table['fields']:
            styles = Counter(r['raw'][field].strip() for r in table['rows'] if is_missing(r['raw'][field]))
            if len(styles) > 1 and field != 'tag':
                rows = [r['source_row'] for r in table['rows'] if is_missing(r['raw'][field]) and r['raw'][field].strip()]
                if rows:
                    out.append(anomaly(f'空值写法不一：{field} 用 {format_counts({(k or "空串"): v for k, v in styles.items()})} 表示缺失', filename, rows))
    return out


# ---------------------------------------------------------------- profile entry

def profile(tables, dictionary, context):
    spec, tag_list = parse_dictionary(dictionary or '')
    fields = []
    for filename, table in tables.items():
        fields.extend(field_statistics(filename, table))

    anomalies, differences = [], []
    for detector in (detect_duplicates, detect_code_formats, detect_dates, detect_enumerations, detect_amounts):
        a, d = detector(tables, spec)
        anomalies += a
        differences += d
    for a, d in (detect_references(tables), detect_tags(tables, tag_list), detect_member_quality(tables),
                 detect_shops(tables), detect_workbook(tables)):
        anomalies += a
        differences += d
    anomalies += detect_missing_placeholders(tables)

    if not differences:
        differences.append(difference(next(iter(tables), 'n/a'), '*', '字典描述的字段、类型与取值',
                                      '本次输入未发现与字典不一致之处', '无需修订映射；仍需结合访谈确认口径'))
    if not anomalies:
        first = next(iter(tables), 'n/a')
        anomalies.append({'pattern': '未发现异常模式', 'evidence': {'query': f'逐字段统计见 fields；输入 {first}'}})
    return {'contract_version': CONTRACT_VERSION, 'data_version': context['data_version'],
            'fields': fields, 'anomalies': anomalies, 'dictionary_differences': differences}


# ================================================================ adapter
# Every business decision below is read from cleaning_rules.yaml; the code only knows
# how to interpret each rule type. Record order follows the source files so that two
# runs write byte-identical CSVs.

RECORD_FILES = {'shop': SHOP, 'member': MEMBER, 'order': ORDER, 'card': CARD}
RECORD_TABLES = {'shop': 'stores', 'member': 'members', 'order': 'orders', 'card': 'cards'}
RECORD_KEYS = {'shop': 'shop_cd', 'member': 'hy_id', 'order': 'ord_no', 'card': 'card_no'}
OUTPUT_TABLES = ['members', 'orders', 'stores', 'cards', 'member_tags', 'member_notes', 'quarantine']


class Quarantine(Exception):
    """Raised while mapping a record; carries the reason code from the rules file."""


class Rules:
    def __init__(self, rules, context):
        self.by_id = {r['rule_id']: r for r in rules['abnormal_records']}
        tag_cfg = rules['tag_cleaning']
        tags_path = Path(context['rules_dir']) / tag_cfg['legal_tags_source']
        self.legal_tags = [t.strip() for t in tags_path.read_text(encoding='utf-8-sig').splitlines() if t.strip()]
        delimiters = sorted(tag_cfg['delimiters'], key=len, reverse=True)
        parts = [r'\s+' if d.isspace() else re.escape(d) for d in delimiters]
        self.splitter = re.compile('(' + '|'.join(parts) + ')')
        self.missing = defaultdict(set)
        for entry in rules['invalid_values']:
            if entry['action'] != 'to_null':
                raise ValueError('INVALID_VALUE_ACTION_UNSUPPORTED:' + entry['action'])
            for field in entry['source_fields']:
                self.missing[field].update(str(v) for v in entry['values'])
        self.date_formats = self.param('dates', 'formats').split('|')
        self.account_status = self.mapping('account_status')
        self.tier = self.mapping('tier')
        self.order_status = self.mapping('order_status')
        self.card_alias = self.mapping('card_alias')
        self.card_types = self.param('card_types', 'allowed').split('|')
        self.channels = self.param('channels', 'allowed').split('|')
        self.note_start = re.compile(self.param('note_new_keyword', 'pattern'))
        self.categories = []
        for rule_id in sorted(k for k in self.by_id if k.startswith('note_category_')):
            name, pattern = self.param(rule_id, 'pattern').split('=', 1)
            self.categories.append((name, re.compile(pattern)))
        if self.by_id['money_yuan']['condition'] != 'decimal_yuan_to_cents':
            raise ValueError('MONEY_RULE_UNSUPPORTED')
        if self.by_id['store_code']['condition'] != 'nfkc_trim_upper':
            raise ValueError('STORE_CODE_RULE_UNSUPPORTED')

    def param(self, rule_id, kind):
        condition = self.by_id[rule_id]['condition']
        prefix = kind + ':'
        if not condition.startswith(prefix):
            raise ValueError(f'RULE_CONDITION_UNSUPPORTED:{rule_id}')
        return condition[len(prefix):]

    def mapping(self, rule_id):
        pairs = [item.split('=', 1) for item in self.param(rule_id, 'map').split('|')]
        return {k: v for k, v in pairs}

    def code(self, rule_id):
        return self.by_id[rule_id]['reason_code']

    def active(self, rule_id, action):
        return rule_id in self.by_id and self.by_id[rule_id]['action'] == action

    def is_missing(self, field, value):
        return value is None or value.strip() in self.missing.get(field, MISSING)

    def date(self, value):
        text = value.strip()
        for fmt in self.date_formats:
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        raise Quarantine(self.code('invalid_date'))

    def cents(self, value):
        number = to_decimal(value)
        if number is None:
            raise Quarantine(self.code('invalid_money'))
        scaled = number * 100
        if scaled != scaled.to_integral_value():
            raise Quarantine(self.code('invalid_money'))
        return int(scaled)

    def store(self, value):
        return normalize_code(value)

    def category(self, note):
        for name, pattern in self.categories:
            if pattern.search(note):
                return name
        return '其他'


def split_tag_field(text, cfg):
    """Return (tags, notes) from one tag-field value; every non-tag character stays in a note.

    A note starts at a fragment that matches the "关键词-" rule, after a note that ended
    with a full stop, or right after a legal tag; otherwise the fragment continues the
    running note and keeps its original separator.
    """
    pieces = cfg.splitter.split(text)
    tags, notes = [], []
    separator, after_tag = '', True
    for index, piece in enumerate(pieces):
        if index % 2 == 1:
            separator = piece
            continue
        token = piece.strip()
        if not token:
            continue
        if token in cfg.legal_tags:
            if token not in tags:
                tags.append(token)
            separator, after_tag = '', True
            continue
        starts_new = after_tag or not notes or notes[-1].endswith('。') or cfg.note_start.match(token) is not None
        if starts_new:
            notes.append(token)
        else:
            notes[-1] = notes[-1] + separator + token
        separator, after_tag = '', False
    return tags, notes


def adapt(tables, rules, context):
    cfg = Rules(rules, context)
    result = {name: [] for name in OUTPUT_TABLES}
    counts = {kind: {'read': len(rows_of(tables, f)), 'accepted': 0, 'quarantined': 0, 'deduplicated': 0}
              for kind, f in RECORD_FILES.items()}
    samples, sampled_reasons = [], set()
    stores, members = set(), set()

    def isolate(kind, row, code):
        counts[kind]['quarantined'] += 1
        result['quarantine'].append({'record_type': kind, 'source_file': row['source_file'], 'source_row': row['source_row'],
                                     'reason_code': code, 'raw_json': json.dumps(row['raw'], ensure_ascii=False, sort_keys=True)})
        if code not in sampled_reasons:
            sampled_reasons.add(code)
            samples.append({'source_file': row['source_file'], 'source_row': row['source_row'], 'status': 'quarantined',
                            'destination': f'quarantine.csv 记录 {len(result["quarantine"])}', 'reason': code})

    for kind in ('shop', 'member', 'order', 'card'):
        filename = RECORD_FILES[kind]
        rows = rows_of(tables, filename)
        key_field = RECORD_KEYS[kind]
        contents = defaultdict(set)
        for row in rows:
            contents[row['raw'].get(key_field, '').strip()].add(tuple(sorted(row['raw'].items())))
        seen = set()
        for row in rows:
            raw = row['raw']
            identity = tuple(sorted(raw.items()))
            if identity in seen and cfg.active('exact_duplicate', 'deduplicate'):
                counts[kind]['deduplicated'] += 1
                continue
            seen.add(identity)
            try:
                if len(contents[raw.get(key_field, '').strip()]) > 1:
                    raise Quarantine(cfg.code('duplicate_key'))
                mapped = MAPPERS[kind](raw, cfg, stores, members)
            except Quarantine as exc:
                isolate(kind, row, str(exc))
                continue
            result[RECORD_TABLES[kind]].append(mapped)
            counts[kind]['accepted'] += 1
            if kind == 'shop':
                stores.add(mapped['store_id'])
            elif kind == 'member':
                members.add(mapped['member_id'])
                emit_tags_and_notes(raw, row, cfg, result)
            elif kind == 'order' and not any(s['status'] == 'accepted' for s in samples):
                samples.insert(0, {'source_file': filename, 'source_row': row['source_row'], 'status': 'accepted',
                                   'destination': f'orders.csv 记录 {len(result["orders"])}',
                                   'reason': '金额按元转分、状态映射、日期规范化，会员与门店均能关联'})

    coverage = {'source': coverage_source(tables),
                'time_range': coverage_range(context, result['orders']),
                'quarantined': {kind: counts[kind]['quarantined'] for kind in RECORD_FILES}}
    return {'tables': result, 'record_counts': counts, 'field_mapping': FIELD_MAPPING,
            'samples': samples, 'coverage_notes': coverage}


def map_shop(raw, cfg, stores, members):
    return {'store_id': cfg.store(raw['shop_cd']), 'region': raw['area'].strip(), 'store_name': raw['shop_nm'].strip()}


def map_member(raw, cfg, stores, members):
    status = raw.get('stat', '').strip()
    if status not in cfg.account_status:
        raise Quarantine(cfg.code('account_status_unknown'))
    tier = raw.get('lv', '').strip()
    created = raw.get('create_tm', '').strip()
    return {'member_id': raw['hy_id'].strip(),
            'registered_at': cfg.date(raw['join_dt']),
            'home_store_id': '' if cfg.is_missing('reg_shop', raw.get('reg_shop', '')) else cfg.store(raw['reg_shop']),
            'tier': cfg.tier.get(tier, tier),
            'account_status': cfg.account_status[status],
            'registered_channel': raw.get('src_ch', '').strip(),
            'created_at': cfg.date(created) if created else cfg.date(raw['join_dt'])}


def map_order(raw, cfg, stores, members):
    if raw['hy_id'].strip() not in members:
        raise Quarantine(cfg.code('orphan_member'))
    store = cfg.store(raw['shop_cd'])
    if store not in stores:
        raise Quarantine(cfg.code('orphan_store'))
    ordered_at = cfg.date(raw['ord_tm'])
    status = raw['ord_stat'].strip()
    if status not in cfg.order_status:
        raise Quarantine(cfg.code('order_status_unknown'))
    channel = raw['ch'].strip()
    if channel not in cfg.channels:
        raise Quarantine(cfg.code('channels'))
    gross, paid, refund = cfg.cents(raw['amt_total']), cfg.cents(raw['amt_pay']), cfg.cents(raw['amt_rfd'])
    if refund > paid:
        raise Quarantine(cfg.code('refund_exceeds_paid'))
    quantity = to_decimal(raw['qty'])
    if quantity is None or quantity != quantity.to_integral_value():
        raise Quarantine(cfg.code('invalid_money'))
    return {'order_id': raw['ord_no'].strip(), 'member_id': raw['hy_id'].strip(), 'store_id': store,
            'ordered_at': ordered_at, 'status': cfg.order_status[status], 'gross_cents': gross, 'paid_cents': paid,
            'refund_cents': refund, 'quantity': int(quantity), 'channel': channel}


def map_card(raw, cfg, stores, members):
    if raw['hy_id'].strip() not in members:
        raise Quarantine(cfg.code('orphan_member'))
    kind = raw['card_kind'].strip()
    kind = cfg.card_alias.get(kind, kind)
    if kind not in cfg.card_types:
        raise Quarantine(cfg.code('card_types'))
    ended = '' if cfg.is_missing('stop_dt', raw.get('stop_dt', '')) else cfg.date(raw['stop_dt'])
    return {'card_id': raw['card_no'].strip(), 'member_id': raw['hy_id'].strip(), 'card_type': kind,
            'valid_from': cfg.date(raw['st_dt']), 'valid_until': cfg.date(raw['ed_dt']), 'ended_at': ended,
            'card_paid_cents': cfg.cents(raw['pay_amt'])}


MAPPERS = {'shop': map_shop, 'member': map_member, 'order': map_order, 'card': map_card}


def emit_tags_and_notes(raw, row, cfg, result):
    text = raw.get('tag', '')
    if cfg.is_missing('tag', text):
        return
    member_id = raw['hy_id'].strip()
    tags, notes = split_tag_field(text, cfg)
    for tag in tags:
        result['member_tags'].append({'member_id': member_id, 'tag': tag})
    unique = []
    for note in notes:
        if note in unique:   # identical text twice in one field: keep the text, attach it to the previous note
            unique[-1] = unique[-1] + note
        else:
            unique.append(note)
    for note in unique:
        result['member_notes'].append({'member_id': member_id, 'source_file': row['source_file'], 'source_row': row['source_row'],
                                       'source_field': 'tag', 'raw_text': text, 'note_text': note,
                                       'category': cfg.category(note)})


def coverage_source(tables):
    parts = ['新 CRM 导出：会员、订单、会员卡、门店四个文件。',
             '不含门店老收银系统中的部分会员消费（老周 MSG-05387、MSG-05395，涉及门店与时间段待核），CRM 中“未购买”不等于没有消费。',
             '已注销会员的资料按公司规定清理，订单保留但无法关联会员，按 UNLINKED_ACCOUNT 隔离（老周 MSG-05387）。',
             '手机号已中间四位脱敏；姓名、手机号、生日不进入查询库。']
    if DND_LIST in tables or CALLBACK_LIST in tables:
        parts.append('小林工作账（回访名单、勿扰名单）只用于对照、未导入查询库；勿扰名单中有会员在 CRM 无触达限制，触达名单须另用工作账过滤。')
    return ''.join(parts)


def coverage_range(context, orders):
    manifest = Path(context.get('source', '')) / 'manifest.json'
    if manifest.is_file():
        try:
            coverage = json.loads(manifest.read_text(encoding='utf-8')).get('coverage')
            if isinstance(coverage, list) and len(coverage) == 2:
                return {'start': coverage[0], 'end_exclusive': coverage[1]}
        except (ValueError, OSError):
            pass
    dates = sorted(o['ordered_at'] for o in orders)
    if not dates:
        today = datetime.now().date().isoformat()
        return {'start': today, 'end_exclusive': next_day(today)}
    return {'start': dates[0], 'end_exclusive': next_day(dates[-1])}


def next_day(iso):
    return (datetime.strptime(iso, '%Y-%m-%d') + timedelta(days=1)).date().isoformat()


FIELD_MAPPING = [
    {'source_file': SHOP, 'source_fields': ['shop_cd'], 'target': 'stores.store_id', 'transformation': 'NFKC 规范化、去首尾空白、转大写；字母开头编码保留'},
    {'source_file': SHOP, 'source_fields': ['area'], 'target': 'stores.region', 'transformation': '原值保留（含字典外的西南、华中）'},
    {'source_file': SHOP, 'source_fields': ['shop_nm'], 'target': 'stores.store_name', 'transformation': '原值保留；同名多编码不合并'},
    {'source_file': MEMBER, 'source_fields': ['hy_id'], 'target': 'members.member_id', 'transformation': '原会员号'},
    {'source_file': MEMBER, 'source_fields': ['join_dt'], 'target': 'members.registered_at', 'transformation': 'YYYY-MM-DD、YYYY/MM/DD、YYYYMMDD 解析为 ISO 日期；不用 create_tm'},
    {'source_file': MEMBER, 'source_fields': ['reg_shop'], 'target': 'members.home_store_id', 'transformation': '同门店编码规范化'},
    {'source_file': MEMBER, 'source_fields': ['lv'], 'target': 'members.tier', 'transformation': '中文名称原样；兼容代码 1/2/3'},
    {'source_file': MEMBER, 'source_fields': ['stat'], 'target': 'members.account_status', 'transformation': '1 活跃、2 冻结、3 注销、0 未激活；其他隔离'},
    {'source_file': MEMBER, 'source_fields': ['src_ch'], 'target': 'members.registered_channel', 'transformation': '原值保留（含系统导入）'},
    {'source_file': MEMBER, 'source_fields': ['create_tm'], 'target': 'members.created_at', 'transformation': '取日期部分，表示新 CRM 建档日期'},
    {'source_file': MEMBER, 'source_fields': ['tag'], 'target': 'member_tags.tag', 'transformation': '多分隔符拆分，仅 16 个正式标签进入'},
    {'source_file': MEMBER, 'source_fields': ['tag'], 'target': 'member_notes.note_text', 'transformation': '非标签片段按“关键词-”和句号组成整条备注，raw_text 保留完整原值，按规则判定类别'},
    {'source_file': ORDER, 'source_fields': ['ord_no'], 'target': 'orders.order_id', 'transformation': '原订单号；完全重复行去重'},
    {'source_file': ORDER, 'source_fields': ['hy_id'], 'target': 'orders.member_id', 'transformation': '须关联到已接受会员，否则隔离 UNLINKED_ACCOUNT'},
    {'source_file': ORDER, 'source_fields': ['shop_cd'], 'target': 'orders.store_id', 'transformation': '门店编码规范化后关联门店表'},
    {'source_file': ORDER, 'source_fields': ['ord_tm'], 'target': 'orders.ordered_at', 'transformation': '取本地日期；无法解析隔离 INVALID_DATE'},
    {'source_file': ORDER, 'source_fields': ['ord_stat'], 'target': 'orders.status', 'transformation': '已完成、已支付、部分退款、全额退款转 paid；已取消转 cancelled'},
    {'source_file': ORDER, 'source_fields': ['amt_total'], 'target': 'orders.gross_cents', 'transformation': 'Decimal 元乘 100'},
    {'source_file': ORDER, 'source_fields': ['amt_pay'], 'target': 'orders.paid_cents', 'transformation': 'Decimal 元乘 100'},
    {'source_file': ORDER, 'source_fields': ['amt_rfd'], 'target': 'orders.refund_cents', 'transformation': 'Decimal 元乘 100；大于实付隔离 REFUND_EXCEEDS_PAID'},
    {'source_file': ORDER, 'source_fields': ['qty'], 'target': 'orders.quantity', 'transformation': '转整数'},
    {'source_file': ORDER, 'source_fields': ['ch'], 'target': 'orders.channel', 'transformation': '门店、小程序、商城原样'},
    {'source_file': CARD, 'source_fields': ['card_no'], 'target': 'cards.card_id', 'transformation': '原卡号'},
    {'source_file': CARD, 'source_fields': ['card_kind'], 'target': 'cards.card_type', 'transformation': '悦享卡（年）统一为悦享年卡；清单外卡种隔离'},
    {'source_file': CARD, 'source_fields': ['st_dt', 'ed_dt'], 'target': 'cards.valid_from / valid_until', 'transformation': 'ISO 日期'},
    {'source_file': CARD, 'source_fields': ['stop_dt'], 'target': 'cards.ended_at', 'transformation': '空串、NULL、-、无 视为未提前终止（空值）'},
    {'source_file': CARD, 'source_fields': ['pay_amt'], 'target': 'cards.card_paid_cents', 'transformation': 'Decimal 元乘 100'},
]


# ================================================================ reconciliation

def reconcile(payload):
    meta, manifest = payload['metadata'], payload['manifest']
    rows, balanced_all = [], True
    for kind, filename in RECORD_FILES.items():
        values = dict(meta['record_counts'][kind])
        read = len(payload['source'][filename]['rows']) if filename in payload['source'] else 0
        in_db = payload['first']['counts'].get('raw_' + RECORD_TABLES[kind], 0)
        cleaned = len(payload['cleaned'][RECORD_TABLES[kind] + '.csv']['rows'])
        balanced = (read == values['read'] == values['accepted'] + values['quarantined'] + values['deduplicated']
                    and in_db == values['accepted'] == cleaned)
        balanced_all = balanced_all and balanced
        rows.append({'record_type': kind, **values,
                     'reconciliation': {'balanced': balanced,
                                        'evidence': f'源文件 {read} = 接受 {values["accepted"]} + 隔离 {values["quarantined"]} + 去重 {values["deduplicated"]}；清洗 CSV {cleaned}；库内 {in_db}'}})
    orders = payload['cleaned']['orders.csv']['rows']
    paid_total = sum(int(r['raw']['paid_cents']) for r in orders)
    accepted_ids = {r['raw']['order_id'] for r in orders}
    source_paid, counted = 0, set()
    for r in payload['source'].get(ORDER, {'rows': []})['rows']:
        order_id = r['raw']['ord_no'].strip()
        if order_id in accepted_ids and order_id not in counted:
            counted.add(order_id)
            source_paid += int(Decimal(r['raw']['amt_pay']) * 100)
    quarantine = payload['cleaned']['quarantine.csv']['rows']
    quarantine_ok = all(json.loads(q['raw']['raw_json'])
                        == payload['source'][q['raw']['source_file']]['rows'][int(q['raw']['source_row']) - 1]['raw']
                        for q in quarantine)
    before, after = payload['first']['counts'], payload['second']['counts']
    repeat = before == after and payload['first'].get('table_sha256') == payload['second'].get('table_sha256')
    money_ok = paid_total == payload['first']['paid_cents'] == payload['second']['paid_cents'] == source_paid
    passed = (balanced_all and repeat and money_ok and quarantine_ok
              and len(orders) == payload['first']['order_count'] == payload['second']['order_count'])
    details = (f'清洗后订单 {len(orders)} 条，实付合计 {paid_total} 分；原始文件中同一批订单按元换算 {source_paid} 分；'
               f'两次导入实付 {payload["first"]["paid_cents"]} / {payload["second"]["paid_cents"]} 分，订单 {payload["first"]["order_count"]} / {payload["second"]["order_count"]} 条；'
               f'隔离 {len(quarantine)} 条，raw_json 与原始记录逐条一致：{quarantine_ok}；各类读入＝接受＋隔离＋去重：{balanced_all}；两次导入表计数与哈希一致：{repeat}。')
    return {'contract_version': CONTRACT_VERSION, 'data_version': manifest['id'], 'field_mapping': meta['field_mapping'],
            'record_counts': rows, 'samples': meta['samples'],
            'repeat_import': {'first_run_id': payload['first_run_id'], 'second_run_id': payload['second_run_id'],
                              'before': before, 'after': after, 'row_counts_equal': before == after},
            'test_result': {'passed': passed, 'details': details}}
