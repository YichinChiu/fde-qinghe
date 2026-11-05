"""青禾 W03 判定程序：纯比较期望与实际结果，不调用大模型，不另行查数。

比较顺序（docs/w03/test-guide.md 第 5 节）：状态 → 版本 → 意图 → 单位 → 列 → 行 → 值。
- 整数期望精确比较（13000 与 13000.0 相等，13001 不等）；浮点期望用 rel_tol=1e-9、abs_tol=1e-9。
- null 只等于 null；布尔值、数字字符串、非有限浮点一律拒绝。
- 指标、分组按名字作集合比较（不允许重复）；筛选按 (field, op, value) 排序比较，不删除多出的筛选。
- 行按 group_by 各列的值组成键对齐，检查缺组、多组、重复组；无分组时两边都必须恰好一行。
- 时间分组键只做格式规范化：“YYYY-MM-DD 00:00:00”视为“YYYY-MM-DD”，不把不同日期归一。
调试信息只写标准错误；标准输出只有一个 JSON 对象。
"""
import json
import math
import re
import sys

STATUSES = {"ok", "clarify", "unsupported", "error"}
VERSION_FIELDS = ("data_version", "data_sha256", "catalog_sha256")
REL_TOL = 1e-9
ABS_TOL = 1e-9
_MIDNIGHT = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]00:00:00(\.0+)?$")


def _diff(out, path, expected, actual, **extra):
    item = {"path": path, "expected": expected, "actual": actual}
    item.update(extra)
    out.append(item)


def _is_number(x):
    return type(x) in (int, float) and (type(x) is int or math.isfinite(x))


def equal_value(want, got):
    if want is None:
        return got is None, "null"
    if not _is_number(got) or not _is_number(want):
        return False, "type"
    if type(want) is int:
        if type(got) is float and not got.is_integer():
            return False, "exact"
        return int(got) == want if type(got) is float else got == want, "exact"
    return math.isclose(want, got, rel_tol=REL_TOL, abs_tol=ABS_TOL), f"isclose(rel={REL_TOL},abs={ABS_TOL})"


def _norm_key(v):
    if isinstance(v, str):
        m = _MIDNIGHT.match(v)
        if m:
            return m.group(1)
    if isinstance(v, bool) or v is None:
        return ("__special__", repr(v))
    return v


def _name_set(out, path, want, got):
    if not isinstance(got, list):
        _diff(out, path, want, got, rule="must be list")
        return
    if len(set(map(str, got))) != len(got):
        _diff(out, path, want, got, rule="duplicate names")
    if sorted(map(str, want)) != sorted(map(str, got)):
        _diff(out, path, want, got, rule="set mismatch")


def _filters_key(fs):
    res = []
    for f in fs:
        v = f.get("value")
        v = tuple(sorted(v)) if isinstance(v, list) else v
        res.append((str(f.get("field")), str(f.get("op")), json.dumps(v, ensure_ascii=False, sort_keys=True)))
    return sorted(res)


def compare_intent(out, want, got):
    if not isinstance(got, dict):
        _diff(out, "intent", want, got, rule="missing intent")
        return
    _name_set(out, "intent.metrics", want["metrics"], got.get("metrics"))
    for k in ("start", "end"):
        if got.get(k) != want[k]:
            _diff(out, f"intent.{k}", want[k], got.get(k))
    _name_set(out, "intent.group_by", want["group_by"], got.get("group_by"))
    gf = got.get("filters")
    if not isinstance(gf, list) or any(not isinstance(f, dict) for f in gf):
        _diff(out, "intent.filters", want["filters"], gf, rule="must be list of objects")
    elif _filters_key(want["filters"]) != _filters_key(gf):
        _diff(out, "intent.filters", want["filters"], gf)


def compare(expected, actual):
    out = []
    if not isinstance(expected, dict) or expected.get("status") not in STATUSES:
        return {"passed": False, "differences": [{"path": "expected.status", "rule": "unsupported expected status",
                                                    "expected": None, "actual": None}]}
    if not isinstance(actual, dict):
        return {"passed": False, "differences": [{"path": "actual", "rule": "not an object",
                                                    "expected": "object", "actual": actual}]}
    # 1. 状态
    if actual.get("status") != expected["status"]:
        _diff(out, "status", expected["status"], actual.get("status"))
        return {"passed": False, "differences": out}
    # 2. 版本（只比较期望中明确锁定的字段）
    for f in VERSION_FIELDS:
        if f in expected and actual.get(f) != expected[f]:
            _diff(out, f, expected[f], actual.get(f), rule="version mismatch or missing")
    if expected["status"] != "ok":
        return {"passed": not out, "differences": out}
    for f in ("intent", "columns", "rows", "units"):
        if f not in expected:
            _diff(out, f"expected.{f}", "present", None, rule="ok expectation incomplete")
    if out:
        return {"passed": False, "differences": out}
    # 3. 意图
    compare_intent(out, expected["intent"], actual.get("intent"))
    # 4. 单位
    gu, wu = actual.get("units"), expected["units"]
    if not isinstance(gu, dict):
        _diff(out, "units", wu, gu, rule="must be object")
    else:
        for m in sorted(set(wu) | set(gu)):
            if m not in gu:
                _diff(out, f"units.{m}", wu[m], None, rule="missing unit")
            elif m not in wu:
                _diff(out, f"units.{m}", None, gu[m], rule="unexpected unit")
            elif gu[m] != wu[m]:
                _diff(out, f"units.{m}", wu[m], gu[m], rule="unit mismatch")
    # 5. 列
    wc, gc, gr = expected["columns"], actual.get("columns"), actual.get("rows")
    col_ok = isinstance(gc, list) and len(set(gc)) == len(gc) and set(gc) == set(wc)
    if not col_ok:
        _diff(out, "columns", wc, gc, rule="column set mismatch or duplicate")
    if not isinstance(gr, list) or any(not isinstance(r, list) for r in gr):
        _diff(out, "rows", "list of lists", gr, rule="rows must be list of lists")
        return {"passed": False, "differences": out}
    if not col_ok:
        return {"passed": False, "differences": out}
    for i, r in enumerate(gr):
        if len(r) != len(gc):
            _diff(out, f"rows[{i}]", len(gc), len(r), rule="row length != column count")
    for i, r in enumerate(expected["rows"]):
        if len(r) != len(wc):
            _diff(out, f"expected.rows[{i}]", len(wc), len(r), rule="expected row length")
    if out and any(d["path"].startswith(("rows[", "expected.rows")) for d in out):
        return {"passed": False, "differences": out}
    # 6. 行：按分组键对齐
    keys = list(expected["intent"]["group_by"])
    metrics = [c for c in wc if c not in keys]

    def index(rows, cols, side):
        idx = {}
        for r in rows:
            rec = dict(zip(cols, r))
            k = tuple(_norm_key(rec.get(g)) for g in keys)
            if k in idx:
                _diff(out, "rows", None, None, rule=f"duplicate group in {side}", group=dict(zip(keys, k)))
                continue
            idx[k] = rec
        return idx

    wi, gi = index(expected["rows"], wc, "expected"), index(gr, gc, "actual")
    if not keys:
        if len(expected["rows"]) != 1 or len(gr) != 1:
            _diff(out, "rows", len(expected["rows"]), len(gr), rule="ungrouped result must have exactly one row")
    for k in sorted(set(wi) - set(gi), key=str):
        _diff(out, "rows", "present", "missing", rule="missing group", group=dict(zip(keys, k)))
    for k in sorted(set(gi) - set(wi), key=str):
        _diff(out, "rows", "absent", "present", rule="unexpected group", group=dict(zip(keys, k)))
    # 7. 值
    for k in sorted(set(wi) & set(gi), key=str):
        for m in metrics:
            ok, rule = equal_value(wi[k][m], gi[k].get(m))
            if not ok:
                _diff(out, "rows", wi[k][m], gi[k].get(m), rule=rule, group=dict(zip(keys, k)), metric=m)
    return {"passed": not out, "differences": out}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        result = compare(data["expected"], data["actual"])
    except Exception as exc:  # 输入格式错误也必须输出合法 JSON 并判为不通过
        print(f"judge input error: {exc!r}", file=sys.stderr)
        result = {"passed": False, "differences": [{"path": "input", "rule": "invalid judge input",
                                                     "expected": None, "actual": str(exc)}]}
    print(json.dumps(result, ensure_ascii=False, default=str))
