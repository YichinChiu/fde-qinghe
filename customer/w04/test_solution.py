"""Qinghe adapter tests. Inputs are hand-built records; expectations are written out
independently of the implementation, against the real rules file and tag list."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RULES_PATH = ROOT / 'artifacts' / 'w04' / 'cleaning_rules.yaml'

spec = importlib.util.spec_from_file_location('qinghe_solution', HERE / 'solution.py')
solution = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solution)

RULES = yaml.safe_load(RULES_PATH.read_text(encoding='utf-8'))
CONTEXT = {'rules_dir': str(RULES_PATH.parent), 'source': str(HERE), 'data_version': 'unit-test'}


def table(filename, fields, records):
    return {'fields': fields, 'rows': [{'source_file': filename, 'source_row': i, 'raw': dict(r)}
                                        for i, r in enumerate(records, 1)]}


SHOP_FIELDS = ['shop_cd', 'shop_nm', 'area', 'open_dt', 'shop_stat']
MEMBER_FIELDS = ['hy_id', 'nm', 'mobile', 'birth', 'join_dt', 'create_tm', 'lv', 'stat', 'src_ch', 'reg_shop', 'reg_dev', 'tag']
ORDER_FIELDS = ['ord_no', 'hy_id', 'shop_cd', 'ord_tm', 'ord_stat', 'amt_total', 'amt_pay', 'amt_rfd', 'qty', 'ch']
CARD_FIELDS = ['card_no', 'hy_id', 'card_kind', 'st_dt', 'ed_dt', 'stop_dt', 'pay_amt']


def member(hy_id, tag='', **over):
    base = {'hy_id': hy_id, 'nm': '测试', 'mobile': '139****0000', 'birth': 'NULL', 'join_dt': '2023-06-01',
            'create_tm': '2023-06-01 10:00:00', 'lv': '普通', 'stat': '1', 'src_ch': '门店', 'reg_shop': '1001',
            'reg_dev': 'abc', 'tag': tag}
    base.update(over)
    return base


def order(ord_no, hy_id='QH10000001', **over):
    base = {'ord_no': ord_no, 'hy_id': hy_id, 'shop_cd': '1001', 'ord_tm': '2026-08-03 10:00:00', 'ord_stat': '已完成',
            'amt_total': '99.90', 'amt_pay': '79.90', 'amt_rfd': '0.00', 'qty': '2', 'ch': '门店'}
    base.update(over)
    return base


def sample_tables():
    return {
        solution.SHOP: table(solution.SHOP, SHOP_FIELDS, [
            {'shop_cd': '1001', 'shop_nm': '测试店', 'area': '华东', 'open_dt': '2020-01-01', 'shop_stat': '营业'},
            {'shop_cd': ' a446 ', 'shop_nm': '新店', 'area': '西南', 'open_dt': '2025-02-01', 'shop_stat': '营业'}]),
        solution.MEMBER: table(solution.MEMBER, MEMBER_FIELDS, [
            member('QH10000001', '母婴-0到3岁,老客户-以前经常来，卡务-11月办卡，门店留有登记'),
            member('QH10000002', 'NULL', join_dt='20230603', stat='0', reg_shop='１００１'),
            member('QH10000003', '价格敏感/生鲜偏好;勿发短信-投诉过', join_dt='2023/06/02', reg_shop='A446')]),
        solution.ORDER: table(solution.ORDER, ORDER_FIELDS, [
            order('O1'),
            order('O1'),                                                   # exact duplicate (page overlap)
            order('O2', hy_id='QH10099999'),                              # member cleaned after deregistration
            order('O3', ord_stat='部分退款', amt_pay='26.78', amt_rfd='34.81'),
            order('O4', ord_tm='2026-02-30 09:00:00'),                     # impossible calendar date
            order('O5', shop_cd=' a446 ', ord_stat='已取消', amt_pay='0.00'),
            order('O6', ord_stat='全额退款', amt_rfd='79.90')]),
        solution.CARD: table(solution.CARD, CARD_FIELDS, [
            {'card_no': 'C1', 'hy_id': 'QH10000001', 'card_kind': '悦享卡（年）', 'st_dt': '2023-01-01', 'ed_dt': '2024-01-01', 'stop_dt': '无', 'pay_amt': '199.00'},
            {'card_no': 'C2', 'hy_id': 'QH10000002', 'card_kind': '员工卡', 'st_dt': '2024-01-01', 'ed_dt': '2025-01-01', 'stop_dt': '2024-06-30', 'pay_amt': '0.00'},
            {'card_no': 'C3', 'hy_id': 'QH10000003', 'card_kind': '神秘卡', 'st_dt': '2024-01-01', 'ed_dt': '2025-01-01', 'stop_dt': '', 'pay_amt': '9.90'}]),
    }


class TagAndNoteTests(unittest.TestCase):
    def setUp(self):
        self.cfg = solution.Rules(RULES, CONTEXT)

    def test_hyphenated_and_new_tags_are_legal(self):
        tags, notes = solution.split_tag_field('母婴-0到3岁,夜间购物，银发族', self.cfg)
        self.assertEqual(tags, ['母婴-0到3岁', '夜间购物', '银发族'])
        self.assertEqual(notes, [])

    def test_card_note_keeps_internal_comma(self):
        tags, notes = solution.split_tag_field('老客户-以前经常来，卡务-11月办卡，门店留有登记', self.cfg)
        self.assertEqual(tags, [])
        self.assertEqual(notes, ['老客户-以前经常来', '卡务-11月办卡，门店留有登记'])

    def test_full_stop_closes_a_note(self):
        _, notes = solution.split_tag_field('等本人回复。,联系状态-优先留微信消息', self.cfg)
        self.assertEqual(notes, ['等本人回复。', '联系状态-优先留微信消息'])

    def test_unconfirmed_word_kept_as_note_not_dropped(self):
        tags, notes = solution.split_tag_field('母婴-0到3岁,待核新品,勿打电话-先留言', self.cfg)
        self.assertEqual(tags, ['母婴-0到3岁'])
        self.assertEqual(notes, ['待核新品', '勿打电话-先留言'])

    def test_contact_restrictions_recognised_anywhere(self):
        for text in ['勿打电话-本人要求', '勿发短信-营销通知先停', '本人要求勿打电话。']:
            self.assertEqual(self.cfg.category(text), '触达限制', text)
        for text in ['联系状态-下班后再问', '电话-上次没接', '微信-等本人回复']:
            self.assertEqual(self.cfg.category(text), '联系状态', text)


class ValueTests(unittest.TestCase):
    def setUp(self):
        self.cfg = solution.Rules(RULES, CONTEXT)

    def test_yuan_to_cents(self):
        self.assertEqual(self.cfg.cents('61.01'), 6101)
        self.assertEqual(self.cfg.cents('0.00'), 0)
        self.assertEqual(self.cfg.cents('199'), 19900)
        with self.assertRaises(solution.Quarantine):
            self.cfg.cents('0.001')
        with self.assertRaises(solution.Quarantine):
            self.cfg.cents('NaN')

    def test_three_date_styles_and_invalid_date(self):
        self.assertEqual(self.cfg.date('2023-06-01'), '2023-06-01')
        self.assertEqual(self.cfg.date('2023/06/01'), '2023-06-01')
        self.assertEqual(self.cfg.date('20230601'), '2023-06-01')
        self.assertEqual(self.cfg.date('2026-08-03 10:33:20'), '2026-08-03')
        with self.assertRaises(solution.Quarantine):
            self.cfg.date('2026-02-30')

    def test_store_code_normalisation(self):
        self.assertEqual(self.cfg.store(' 3050 '), '3050')
        self.assertEqual(self.cfg.store('　3050　'), '3050')
        self.assertEqual(self.cfg.store('１１２４'), '1124')
        self.assertEqual(self.cfg.store('j946'), 'J946')


class AdaptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = solution.adapt(sample_tables(), RULES, CONTEXT)

    def test_counts_balance(self):
        counts = self.result['record_counts']
        self.assertEqual(counts['order'], {'read': 7, 'accepted': 3, 'quarantined': 3, 'deduplicated': 1})
        self.assertEqual(counts['card'], {'read': 3, 'accepted': 2, 'quarantined': 1, 'deduplicated': 0})
        for kind, c in counts.items():
            self.assertEqual(c['read'], c['accepted'] + c['quarantined'] + c['deduplicated'], kind)

    def test_quarantine_reasons_and_raw_kept(self):
        reasons = {(q['record_type'], q['source_row']): q['reason_code'] for q in self.result['tables']['quarantine']}
        self.assertEqual(reasons, {('order', 3): 'UNLINKED_ACCOUNT', ('order', 4): 'REFUND_EXCEEDS_PAID',
                                   ('order', 5): 'INVALID_DATE', ('card', 3): 'UNSUPPORTED_CARD_TYPE'})
        refund = next(q for q in self.result['tables']['quarantine'] if q['reason_code'] == 'REFUND_EXCEEDS_PAID')
        self.assertEqual(json.loads(refund['raw_json'])['amt_rfd'], '34.81')

    def test_members_mapping(self):
        members = {m['member_id']: m for m in self.result['tables']['members']}
        self.assertEqual(members['QH10000002']['registered_at'], '2023-06-03')
        self.assertEqual(members['QH10000002']['account_status'], '未激活')
        self.assertEqual(members['QH10000002']['home_store_id'], '1001')
        self.assertEqual(members['QH10000003']['registered_at'], '2023-06-02')
        self.assertEqual(members['QH10000003']['home_store_id'], 'A446')

    def test_orders_money_and_status(self):
        orders = {o['order_id']: o for o in self.result['tables']['orders']}
        self.assertEqual(set(orders), {'O1', 'O5', 'O6'})
        self.assertEqual((orders['O1']['gross_cents'], orders['O1']['paid_cents'], orders['O1']['status']), (9990, 7990, 'paid'))
        self.assertEqual((orders['O5']['status'], orders['O5']['store_id']), ('cancelled', 'A446'))
        self.assertEqual((orders['O6']['status'], orders['O6']['refund_cents']), ('paid', 7990))

    def test_cards_alias_employee_and_empty_stop(self):
        cards = {c['card_id']: c for c in self.result['tables']['cards']}
        self.assertEqual(cards['C1']['card_type'], '悦享年卡')
        self.assertEqual(cards['C1']['ended_at'], '')
        self.assertEqual((cards['C2']['card_type'], cards['C2']['ended_at'], cards['C2']['card_paid_cents']), ('员工卡', '2024-06-30', 0))

    def test_tags_and_notes_tables(self):
        tags = {(t['member_id'], t['tag']) for t in self.result['tables']['member_tags']}
        self.assertEqual(tags, {('QH10000001', '母婴-0到3岁'), ('QH10000003', '价格敏感'), ('QH10000003', '生鲜偏好')})
        notes = [(n['member_id'], n['note_text'], n['category']) for n in self.result['tables']['member_notes']]
        self.assertEqual(notes, [('QH10000001', '老客户-以前经常来', '客户关系'),
                                 ('QH10000001', '卡务-11月办卡，门店留有登记', '卡务'),
                                 ('QH10000003', '勿发短信-投诉过', '触达限制')])
        first = self.result['tables']['member_notes'][0]
        self.assertEqual((first['source_field'], first['source_row']), ('tag', 1))
        self.assertEqual(first['raw_text'], '母婴-0到3岁,老客户-以前经常来，卡务-11月办卡，门店留有登记')

    def test_repeat_run_identical(self):
        again = solution.adapt(copy.deepcopy(sample_tables()), RULES, CONTEXT)
        self.assertEqual(json.dumps(again, ensure_ascii=False, sort_keys=True),
                         json.dumps(self.result, ensure_ascii=False, sort_keys=True))

    def test_missing_workbook_is_fine_and_samples_cover_both(self):
        statuses = {s['status'] for s in self.result['samples']}
        self.assertTrue({'accepted', 'quarantined'} <= statuses)
        self.assertNotIn('工作账', self.result['coverage_notes']['source'])


if __name__ == '__main__':
    unittest.main()
