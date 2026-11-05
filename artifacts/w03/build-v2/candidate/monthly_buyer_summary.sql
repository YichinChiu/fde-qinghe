select
  member_id || '_' || strftime(date_trunc('month', ordered_at), '%Y-%m-%d') as member_month_id,
  member_id,
  date_trunc('month', ordered_at)::date as month_start,
  count(*) as valid_order_cnt
from {{ ref('orders') }}
where status = 'paid' and (paid_cents - refund_cents) > 0
group by 1, 2, 3