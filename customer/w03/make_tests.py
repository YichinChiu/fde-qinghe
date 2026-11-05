"""由 test_specs.json 与独立审核程序 audit.py 生成 tests.json。

期望只来自 audit.py 对 CSV 的逐记录计算，不读取指标库或任何测试运行结果。
用法：python customer/w03/make_tests.py <数据目录> <specs.json> <输出 tests.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit  # noqa: E402

DEF = {
    "order_count": "01_订单日报说明“按下单日期统计全部订单…包含取消单”：窗口内全部订单行计数",
    "paid_order_count": "01“状态为 paid 的订单数，包括后来全部退款的订单”",
    "valid_order_count": "01／02“paid 且实付大于累计退款”：status=paid 且 paid_cents-refund_cents>0",
    "cancelled_order_count": "01“状态为 cancelled 的订单数”",
    "refund_order_count": "01“paid 状态且退款金额大于零”",
    "partial_refund_order_count": "01“paid 且退款大于零、小于实付”",
    "full_refund_order_count": "01“paid 且实付大于零、退款等于实付”",
    "payment_cents": "01“paid 订单实付金额合计，尚未扣退款”",
    "refund_cents": "01“paid 订单退款金额合计，按原订单下单日期归属”",
    "net_sales_cents": "01“paid 订单实付减退款后合计；取消单不计”",
    "gross_cents": "01“paid 订单折扣前原价金额合计”",
    "discount_cents": "01“paid 订单原价减实付…退款不冲减”：sum(gross_cents-paid_cents)",
    "buyer_count": "01“有有效订单的不同 CRM 会员账户数”：有效订单 member_id 去重",
    "refund_buyer_count": "01“发生退款的 paid 订单关联的不同 CRM 会员账户数”",
    "selling_store_count": "01“至少有一笔有效订单的不同订单归属门店数”：有效订单 store_id 去重",
    "valid_order_items": "01“有效订单中的原始购买件数合计”：有效订单 quantity 求和",
    "avg_order_value": "02 净销售额÷有效订单数，分母零为 null",
    "avg_buyer_value": "02 净销售额÷购买会员数，分母零为 null",
    "purchase_frequency": "02 有效订单数÷购买会员数，分母零为 null",
    "refund_amount_rate": "02 退款金额÷实付金额（原始比率）",
    "cancel_rate": "02 取消订单数÷创建订单数",
    "refund_order_rate": "02 退款订单数÷支付订单数",
    "discount_rate": "02 优惠金额÷支付订单原价金额",
    "items_per_order": "02 有效订单商品件数÷有效订单数",
    "new_member_count": "03_会员运营周报“按注册日期统计新注册 CRM 账户数”：registered_at 落在窗口内的 members 行",
    "first_buyer_count": "03“先用全覆盖历史确定首次，再按窗口筛选”：全期有效订单按 (ordered_at, order_id) 排序，序号 1 落在窗口内的账户数",
    "first_order_sales_cents": "03 序号 1 的有效订单 paid_cents-refund_cents 合计",
    "first_order_count": "03 序号 1 的有效订单落在窗口内的单数",
    "repeat_order_count": "03“第二笔及以后的有效订单，按订单日期落入窗口计数”",
    "monthly_buyer_count": "03 同一自然月至少一笔有效订单的账户数",
    "monthly_repeat_buyer_count": "03 同一自然月至少两笔有效订单的账户数",
    "monthly_repeat_rate": "03 月内复购会员数÷月内购买会员数",
    "monthly_paid_buyer_count": "04_本期统计确认邮件：月底最后一天具备付费资格且当月至少一笔有效订单的账户数",
    "monthly_paid_order_count": "04 月末有资格账户当月全部有效订单数（按账户，不按卡重复）",
    "monthly_paid_sales_cents": "04 月末有资格账户当月有效订单净销售额",
    "monthly_paid_repeat_buyer_count": "04 月末有资格且当月至少两笔有效订单的账户数",
    "monthly_paid_repeat_rate": "04 付费会员复购人数÷付费会员购买人数",
    "monthly_paid_avg_order_value": "04 付费会员净销售额÷付费会员有效订单数",
}
ELIGIBILITY = ("月末资格依据 docs/w03/business_model.md 2.2：卡种仅悦享年卡、家庭季卡（运营口头答复待书面确认）；"
               "valid_until、ended_at 落在月底当天不算有效（本期暂定口径，陈姐 MSG-03579/03581）；"
               "valid_from 早于月底有效，等于月底时仅当账户当月月底之前有有效购买才纳入（小林 MSG-03554/03556，FDE 按原话字面解读）；"
               "账户任一张卡有效即有资格，多卡不重复。")


def norm(v):
    if isinstance(v, float) and v.is_integer() is False:
        return v
    return v


def main(data_dir, specs_path, out_path):
    specs = json.load(open(specs_path, encoding="utf-8"))
    tests = []
    for s in specs:
        status = s.get("status", "ok")
        case = {"id": s["id"], "question": s["question"]}
        if status != "ok":
            case["expected"] = {"status": status}
            case["expected_source"] = f"非成功期望：{s['catches']}。只比较状态。"
            tests.append(case)
            continue
        intent = s["intent"]
        res = audit.compute(intent, data_dir)
        rows = []
        for r in res["rows"]:
            rows.append([x for x in r])
        exp = {"status": "ok", "intent": intent, "columns": res["columns"], "rows": rows,
               "units": res["units"], "data_version": res["data_version"]}
        parts = [DEF[m] for m in intent["metrics"]]
        src = (f"独立审核程序 customer/w03/audit.py 对数据版本 {res['data_version']}（{data_dir}）逐记录计算；"
               f"窗口 [{intent['start']}, {intent['end']})，分组 {intent['group_by'] or '无'}，筛选 {intent['filters'] or '无'}。"
               f"定义：{'；'.join(parts)}。")
        if any(m.startswith("monthly_paid") for m in intent["metrics"]):
            src += ELIGIBILITY
        src += f" 本用例检查：{s['catches']}。"
        case["expected"] = exp
        case["expected_source"] = src
        tests.append(case)
    Path(out_path).write_text(json.dumps(tests, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(tests), "ok": sum(1 for t in tests if t["expected"]["status"] == "ok")}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
