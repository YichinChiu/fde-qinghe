"""判定程序自检：从已核对的真实结果制作单点改动的合成注入，逐份交给 judge.py 判定。

用法：python customer/w03/judge_selftest.py <测试报告 metric_test_report.json> <tests.json> <输出目录>
每份注入写成 {"expected": 用例期望, "actual": 改动后的结果}，并通过子进程以标准输入调用 judge.py，
与任务书第 9 步的手工命令等价。注入结果均为合成数据，不是模型真实犯错。
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_judge(payload):
    p = subprocess.run([sys.executable, str(HERE / "judge.py")], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(p.stdout)


def main(report_path, tests_path, out_dir):
    report = json.load(open(report_path, encoding="utf-8"))
    tests = {t["id"]: t for t in json.load(open(tests_path, encoding="utf-8"))}
    actual = {c["id"]: c["actual"] for c in report["cases"]}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def base(cid):
        assert report_path and cid in actual, cid
        exp = tests[cid]["expected"]
        act = copy.deepcopy(actual[cid])
        assert run_judge({"expected": exp, "actual": act})["passed"], f"baseline {cid} must pass"
        return exp, act

    cases = []

    def add(name, cid, desc, mutate, want_pass=False):
        exp, act = base(cid)
        before = json.dumps(act, ensure_ascii=False, sort_keys=True)
        exp2 = mutate(exp, act) or exp
        changed = before != json.dumps(act, ensure_ascii=False, sort_keys=True)
        payload = {"expected": exp2, "actual": act}
        (out / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        res = run_judge(payload)
        cases.append({"name": name, "source_case": cid, "change": desc, "actual_modified": changed,
                      "expected_passed": want_pass, "judge_passed": res["passed"],
                      "ok": res["passed"] == want_pass, "differences": res["differences"]})

    # 9 类必做注入
    add("01-wrong-metric", "aug-net-sales", "intent.metrics: net_sales_cents → payment_cents",
        lambda e, a: a["intent"].__setitem__("metrics", ["payment_cents"]))
    add("02-wrong-date", "aug-net-sales", "intent.end: 2026-09-01 → 2026-08-31，数字不变",
        lambda e, a: a["intent"].__setitem__("end", "2026-08-31"))
    add("03-extra-filter", "aug-net-sales", "intent.filters 多加 order__channel=门店",
        lambda e, a: a["intent"]["filters"].append({"field": "order__channel", "op": "eq", "value": "门店"}))
    add("04a-wrong-group", "aug-valid-orders-by-channel", "intent.group_by: order__channel → store",
        lambda e, a: a["intent"].__setitem__("group_by", ["store"]))
    add("04b-missing-group", "aug-valid-orders-by-channel", "rows 删除一组",
        lambda e, a: a["rows"].pop())
    add("05-cents-vs-yuan", "aug-net-sales", "units.net_sales_cents: cents → yuan，数字不变",
        lambda e, a: a["units"].__setitem__("net_sales_cents", "yuan"))
    def pct(e, a):
        i = a["columns"].index("cancel_rate")
        a["rows"][0][i] = a["rows"][0][i] * 100
    add("06-ratio-as-percent", "aug-orders-cancel", "cancel_rate 乘 100", pct)
    def null_to_zero(e, a):
        i = a["columns"].index("avg_order_value")
        assert a["rows"][0][i] is None
        a["rows"][0][i] = 0
    add("07-null-to-zero", "mar-2025-zero-denominator", "avg_order_value: null → 0", null_to_zero)
    def tamper(e, a):
        a["rows"][0][a["columns"].index("net_sales_cents")] += 1
    add("08-tampered-value", "aug-net-sales", "net_sales_cents +1 分", tamper)
    add("09a-error-with-rows", "aug-net-sales", "status: ok → error，保留正确行",
        lambda e, a: a.__setitem__("status", "error"))
    v1 = json.load(open(Path(report_path).parent.parent / "test-small-v1" / "metric_test_report.json", encoding="utf-8"))
    failed = next(c["actual"] for c in v1["cases"] if c["id"] == "aug-net-sales-by-home-store")
    assert failed["status"] == "error"

    def fake_ok(e, a):
        a.clear()
        a.update(copy.deepcopy(failed))
        a["status"] = "ok"
        a["columns"] = ["home_store__region", "net_sales_cents"]
        a["rows"] = [[r[0], r[1]] for r in e["rows"]]
        a["units"] = dict(e["units"])
    add("09b-failed-result-disguised-ok", "aug-net-sales-by-home-region",
        "取第 1 轮真实失败结果（NATIVE_QUERY_FAILED，意图 group_by=home_store），状态改为 ok 并留着期望行", fake_ok)

    # test-guide 第 6 节补充项
    def dup_group(e, a):
        a["rows"].append(list(a["rows"][0]))
    add("10-duplicate-group", "aug-valid-orders-by-channel", "rows 重复追加同一组", dup_group)
    def lock_version(e, a):
        e = copy.deepcopy(e)
        a["data_version"] = "qinghe-w03-20260923-large"
        return e
    add("11-wrong-data-version", "aug-net-sales", "data_version 替换为另一版本（期望已锁 data_version）", lock_version)
    add("12-role-swap", "aug-net-sales-by-home-region", "group_by: home_store__region → store__region（角色混淆）",
        lambda e, a: a["intent"].__setitem__("group_by", ["store__region"]))
    def to_bool(e, a):
        a["rows"][0][a["columns"].index("selling_store_count")] = True
    add("13-bool-as-number", "aug-selling-stores", "selling_store_count 改为 true", to_bool)
    def to_str(e, a):
        a["rows"][0][a["columns"].index("net_sales_cents")] = str(a["rows"][0][a["columns"].index("net_sales_cents")])
    add("14-numeric-string", "aug-net-sales", "net_sales_cents 改为数字字符串", to_str)
    def ratio_drift(e, a):
        i = a["columns"].index("cancel_rate")
        a["rows"][0][i] = a["rows"][0][i] + 1e-6
    add("15-ratio-outside-tolerance", "aug-orders-cancel", "cancel_rate +1e-6（超出容差）", ratio_drift)
    def extra_unit(e, a):
        a["units"]["payment_cents"] = "cents"
    add("16-extra-unit", "aug-net-sales", "units 多出一项", extra_unit)

    # 正向检查
    add("P1-original", "aug-valid-orders-by-channel", "原始正确结果，不改", lambda e, a: None, want_pass=True)
    add("P2-row-order", "aug-valid-orders-by-channel", "只颠倒行顺序", lambda e, a: a["rows"].reverse(), want_pass=True)
    def col_order(e, a):
        a["columns"] = list(reversed(a["columns"]))
        a["rows"] = [list(reversed(r)) for r in a["rows"]]
    add("P3-column-order", "aug-valid-orders-by-channel", "列顺序整体颠倒（按列名映射）", col_order, want_pass=True)
    def int_float(e, a):
        i = a["columns"].index("net_sales_cents")
        a["rows"][0][i] = float(a["rows"][0][i])
    add("P4-int-as-float", "aug-net-sales", "100300 → 100300.0", int_float, want_pass=True)
    def ratio_within(e, a):
        i = a["columns"].index("cancel_rate")
        a["rows"][0][i] = a["rows"][0][i] + 1e-12
    add("P5-ratio-within-tolerance", "aug-orders-cancel", "cancel_rate +1e-12（容差内）", ratio_within, want_pass=True)

    # 纯比较输入的数值分支（非真实结果）
    big = {"expected": {"status": "ok", "intent": {"metrics": ["payment_cents"], "start": "2026-08-01", "end": "2026-09-01", "group_by": [], "filters": []},
                        "columns": ["payment_cents"], "rows": [[1000000000]], "units": {"payment_cents": "cents"}},
           "actual": {"status": "ok", "intent": {"metrics": ["payment_cents"], "start": "2026-08-01", "end": "2026-09-01", "group_by": [], "filters": []},
                      "columns": ["payment_cents"], "rows": [[1000000001]], "units": {"payment_cents": "cents"}}}
    (out / "S1-large-integer-off-by-one.json").write_text(json.dumps(big, ensure_ascii=False, indent=1), encoding="utf-8")
    r = run_judge(big)
    cases.append({"name": "S1-large-integer-off-by-one", "source_case": "合成比较输入", "change": "1000000000 对 1000000001",
                  "actual_modified": True, "expected_passed": False, "judge_passed": r["passed"], "ok": r["passed"] is False,
                  "differences": r["differences"]})

    summary = {"report": str(report_path), "total": len(cases), "all_ok": all(c["ok"] for c in cases), "cases": cases}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in cases:
        print(f"{c['name']:<34} want_pass={c['expected_passed']!s:<5} judge_pass={c['judge_passed']!s:<5} {'OK' if c['ok'] else 'FAIL'}")
    print("ALL_OK" if summary["all_ok"] else "SOME_FAILED")


if __name__ == "__main__":
    main(*sys.argv[1:4])
