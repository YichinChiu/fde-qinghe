"""青禾 W03 独立审核程序：直接逐记录读取 CSV，按客户材料定义计算期望。

不导入指标库、不读取生成的 metrics.yml / SQL、不调用大模型。
定义依据（文件均在 materials/w03/）：
- 01_订单日报说明.md：订单数、金额、退款、购买会员数、成交门店数、商品件数
- 02_财务邮件.md：有效订单＝paid 且实付大于累计退款；比率与零分母未定义
- 03_会员运营周报.md：注册会员数、观测期首购／首单／后续订单、月内购买与复购
- 04_本期统计确认邮件.md：月末付费会员六项（月底最后一天判资格，按账户不按卡）
- docs/w03/business_model.md：卡种范围（悦享年卡、家庭季卡）、valid_from 月底当天口径、
  valid_until／ended_at 月底当天不算有效（本期暂定口径）

用法：python customer/w03/audit.py <数据目录> <intent.json>   → 打印 {columns, rows, units}
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

PAID_CARD_TYPES = {"悦享年卡", "家庭季卡"}  # 业务模型 2.2：本期总部运营月报卡种范围

UNITS = {
    "order_count": "count", "paid_order_count": "count", "valid_order_count": "count",
    "cancelled_order_count": "count", "refund_order_count": "count",
    "partial_refund_order_count": "count", "full_refund_order_count": "count",
    "payment_cents": "cents", "refund_cents": "cents", "net_sales_cents": "cents",
    "gross_cents": "cents", "discount_cents": "cents", "buyer_count": "count",
    "refund_buyer_count": "count", "selling_store_count": "count", "valid_order_items": "count",
    "avg_order_value": "cents_per_order", "avg_buyer_value": "cents_per_member",
    "purchase_frequency": "orders_per_member", "refund_amount_rate": "ratio", "cancel_rate": "ratio",
    "refund_order_rate": "ratio", "discount_rate": "ratio", "items_per_order": "items_per_order",
    "new_member_count": "count", "first_buyer_count": "count", "first_order_sales_cents": "cents",
    "first_order_count": "count", "repeat_order_count": "count", "monthly_buyer_count": "count",
    "monthly_repeat_buyer_count": "count", "monthly_repeat_rate": "ratio",
    "monthly_paid_buyer_count": "count", "monthly_paid_order_count": "count",
    "monthly_paid_sales_cents": "cents", "monthly_paid_repeat_buyer_count": "count",
    "monthly_paid_repeat_rate": "ratio", "monthly_paid_avg_order_value": "cents_per_order",
}
RATIOS = {
    "avg_order_value": ("net_sales_cents", "valid_order_count"),
    "avg_buyer_value": ("net_sales_cents", "buyer_count"),
    "purchase_frequency": ("valid_order_count", "buyer_count"),
    "refund_amount_rate": ("refund_cents", "payment_cents"),
    "cancel_rate": ("cancelled_order_count", "order_count"),
    "refund_order_rate": ("refund_order_count", "paid_order_count"),
    "discount_rate": ("discount_cents", "gross_cents"),
    "items_per_order": ("valid_order_items", "valid_order_count"),
    "monthly_repeat_rate": ("monthly_repeat_buyer_count", "monthly_buyer_count"),
    "monthly_paid_repeat_rate": ("monthly_paid_repeat_buyer_count", "monthly_paid_buyer_count"),
    "monthly_paid_avg_order_value": ("monthly_paid_sales_cents", "monthly_paid_order_count"),
}
ORDER_METRICS = {
    "order_count", "paid_order_count", "valid_order_count", "cancelled_order_count",
    "refund_order_count", "partial_refund_order_count", "full_refund_order_count",
    "payment_cents", "refund_cents", "net_sales_cents", "gross_cents", "discount_cents",
    "buyer_count", "refund_buyer_count", "selling_store_count", "valid_order_items",
}
FIRST_METRICS = {"first_buyer_count", "first_order_sales_cents", "first_order_count", "repeat_order_count"}
MONTHLY = {"monthly_buyer_count", "monthly_repeat_buyer_count"}
MONTHLY_PAID = {"monthly_paid_buyer_count", "monthly_paid_order_count", "monthly_paid_sales_cents",
                "monthly_paid_repeat_buyer_count"}


def d(s):
    return date.fromisoformat(s) if s else None


def load(data_dir):
    p = Path(data_dir)
    rd = lambda n: list(csv.DictReader(open(p / n, encoding="utf-8", newline="")))
    members = {r["member_id"]: r for r in rd("members.csv")}
    stores = {r["store_id"]: r for r in rd("stores.csv")}
    orders = []
    for r in rd("orders.csv"):
        r = dict(r)
        r["ordered_at"] = d(r["ordered_at"])
        for k in ("gross_cents", "paid_cents", "refund_cents", "quantity"):
            r[k] = int(r[k])
        orders.append(r)
    cards = []
    for r in rd("cards.csv"):
        r = dict(r)
        for k in ("valid_from", "valid_until", "ended_at"):
            r[k] = d(r[k])
        cards.append(r)
    manifest = json.load(open(p / "manifest.json", encoding="utf-8"))
    return members, stores, orders, cards, manifest


def is_paid(o):
    return o["status"] == "paid"


def is_valid(o):  # 02_财务邮件：paid 状态且实付大于累计退款
    return is_paid(o) and o["paid_cents"] - o["refund_cents"] > 0


def month_start(x):
    return x.replace(day=1)


def next_month(x):
    return (x.replace(day=28) + timedelta(days=4)).replace(day=1)


def dim_value(dim, order=None, member=None, stores=None, members=None, t=None):
    """维度取值。order 为订单行（成交门店角色），member 为账户行（归属门店角色）。"""
    if dim == "metric_time__month":
        return month_start(t).isoformat()
    if dim == "metric_time__day":
        return t.isoformat()
    if dim == "store":
        return order["store_id"]
    if dim == "store__region":
        return stores[order["store_id"]]["region"]
    if dim == "store__store_name":
        return stores[order["store_id"]]["store_name"]
    if dim == "order__channel":
        return order["channel"]
    if dim == "order__status":
        return order["status"]
    m = member if member is not None else members[order["member_id"]]
    if dim == "member":
        return m["member_id"]
    if dim == "member__tier":
        return m["tier"]
    if dim == "home_store":
        return m["home_store_id"]
    if dim == "home_store__region":
        return stores[m["home_store_id"]]["region"]
    if dim == "home_store__store_name":
        return stores[m["home_store_id"]]["store_name"]
    if dim == "metric_time__month":
        return month_start(t).isoformat()
    if dim == "metric_time__day":
        return t.isoformat()
    raise ValueError("UNSUPPORTED_DIMENSION:" + dim)


def passes(filters, **kw):
    for f in filters:
        v = dim_value(f["field"], **kw)
        if f["op"] == "eq" and v != f["value"]:
            return False
        if f["op"] == "in" and v not in f["value"]:
            return False
    return True


def ranked_valid_orders(orders):
    """03_会员运营周报：在全测试覆盖期内为每个账户按日期、订单号排序有效订单。"""
    by_member = defaultdict(list)
    for o in orders:
        if is_valid(o):
            by_member[o["member_id"]].append(o)
    seq = {}
    for lst in by_member.values():
        lst.sort(key=lambda o: (o["ordered_at"], o["order_id"]))
        for i, o in enumerate(lst, 1):
            seq[o["order_id"]] = i
    return seq


def eligible_at(member_id, me, cards_by_member, valid_orders_in_month):
    """月末资格：业务模型 2.2。账户任一张范围内卡在月底当天有效即有资格。
    - 卡种：悦享年卡、家庭季卡（运营口头答复，待书面确认）
    - valid_until、ended_at 落在月底当天不算有效（本期暂定口径，门店实际做法）
    - valid_from 早于月底：有效；等于月底：月末才生效，仅当该账户当月此前（月底之前）有有效购买才纳入（小林 MSG-03554/03556）
    """
    for c in cards_by_member.get(member_id, []):
        if c["card_type"] not in PAID_CARD_TYPES:
            continue
        if c["valid_until"] is None or c["valid_until"] <= me:
            continue
        if c["ended_at"] is not None and c["ended_at"] <= me:
            continue
        if c["valid_from"] < me:
            return True
        if c["valid_from"] == me and any(o["ordered_at"] < me for o in valid_orders_in_month):
            return True
    return False


def compute(intent, data_dir):
    members, stores, orders, cards, manifest = load(data_dir)
    start, end = d(intent["start"]), d(intent["end"])
    gb, filters, metrics = intent["group_by"], intent["filters"], intent["metrics"]
    base = set()
    for m in metrics:
        base |= set(RATIOS.get(m, (m,)))
    agg = defaultdict(lambda: defaultdict(int))
    distinct = defaultdict(lambda: defaultdict(set))
    groups = set()

    def key_for(**kw):
        return tuple(dim_value(g, stores=stores, members=members, **kw) for g in gb)

    if base & ORDER_METRICS:
        for o in orders:
            if not (start <= o["ordered_at"] < end):
                continue
            if not passes(filters, order=o, stores=stores, members=members, t=o["ordered_at"]):
                continue
            k = key_for(order=o, t=o["ordered_at"])
            groups.add(k)
            a = agg[k]
            p, r, g = o["paid_cents"], o["refund_cents"], o["gross_cents"]
            a["order_count"] += 1
            if o["status"] == "cancelled":
                a["cancelled_order_count"] += 1
            if is_paid(o):
                a["paid_order_count"] += 1
                a["payment_cents"] += p
                a["refund_cents"] += r
                a["net_sales_cents"] += p - r
                a["gross_cents"] += g
                a["discount_cents"] += g - p
                if r > 0:
                    a["refund_order_count"] += 1
                    distinct[k]["refund_buyer_count"].add(o["member_id"])
                    if r < p:
                        a["partial_refund_order_count"] += 1
                if p > 0 and r == p:
                    a["full_refund_order_count"] += 1
            if is_valid(o):
                a["valid_order_count"] += 1
                a["valid_order_items"] += o["quantity"]
                distinct[k]["buyer_count"].add(o["member_id"])
                distinct[k]["selling_store_count"].add(o["store_id"])

    if "new_member_count" in base:
        for mb in members.values():
            t = d(mb["registered_at"])
            if not (start <= t < end):
                continue
            if not passes(filters, member=mb, stores=stores, members=members, t=t):
                continue
            k = key_for(member=mb, t=t)
            groups.add(k)
            agg[k]["new_member_count"] += 1

    if base & FIRST_METRICS:
        seq = ranked_valid_orders(orders)
        for o in orders:
            if o["order_id"] not in seq or not (start <= o["ordered_at"] < end):
                continue
            if not passes(filters, order=o, stores=stores, members=members, t=o["ordered_at"]):
                continue
            k = key_for(order=o, t=o["ordered_at"])
            groups.add(k)
            if seq[o["order_id"]] == 1:
                agg[k]["first_order_count"] += 1
                agg[k]["first_order_sales_cents"] += o["paid_cents"] - o["refund_cents"]
                distinct[k]["first_buyer_count"].add(o["member_id"])
            else:
                agg[k]["repeat_order_count"] += 1

    if base & (MONTHLY | MONTHLY_PAID):
        if filters or any(g not in ("metric_time__month",) for g in gb):
            raise ValueError("MONTHLY_FULL_MONTH_ALL_STORE_ONLY")
        cards_by_member = defaultdict(list)
        for c in cards:
            cards_by_member[c["member_id"]].append(c)
        ms = start
        while ms < end:
            me_next = next_month(ms)
            me = me_next - timedelta(days=1)
            per_member = defaultdict(list)
            for o in orders:
                if ms <= o["ordered_at"] < me_next and is_valid(o):
                    per_member[o["member_id"]].append(o)
            k = key_for(t=ms)
            groups.add(k)
            a = agg[k]
            for mid, lst in per_member.items():
                a["monthly_buyer_count"] += 1
                if len(lst) >= 2:
                    a["monthly_repeat_buyer_count"] += 1
                if base & MONTHLY_PAID and eligible_at(mid, me, cards_by_member, lst):
                    a["monthly_paid_buyer_count"] += 1
                    a["monthly_paid_order_count"] += len(lst)
                    a["monthly_paid_sales_cents"] += sum(o["paid_cents"] - o["refund_cents"] for o in lst)
                    if len(lst) >= 2:
                        a["monthly_paid_repeat_buyer_count"] += 1
            ms = me_next

    def value(k, m):
        if m in RATIOS:
            n, den = (value(k, x) for x in RATIOS[m])
            return None if not den else n / den
        if m in distinct[k] or m in ("buyer_count", "refund_buyer_count", "selling_store_count", "first_buyer_count"):
            return len(distinct[k][m])
        return agg[k][m]

    if not gb:
        groups = {()}
    rows = [list(k) + [value(k, m) for m in metrics] for k in sorted(groups)]
    return {"columns": list(gb) + list(metrics), "rows": rows, "units": {m: UNITS[m] for m in metrics},
            "data_version": manifest["id"]}


if __name__ == "__main__":
    print(json.dumps(compute(json.load(open(sys.argv[2], encoding="utf-8")), sys.argv[1]), ensure_ascii=False))
