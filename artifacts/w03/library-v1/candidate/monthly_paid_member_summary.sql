with months as (
  select distinct
    date_trunc('month', ordered_at)::date as month_start,
    (date_trunc('month', ordered_at) + interval '1 month' - interval '1 day')::date as month_end
  from {{ ref('orders') }}
),
monthly_orders as (
  select
    member_id,
    date_trunc('month', ordered_at)::date as month_start,
    count(*) as valid_order_cnt,
    sum(paid_cents - refund_cents) as net_sales_cents,
    min(ordered_at) as min_ordered_at
  from {{ ref('orders') }}
  where status = 'paid' and (paid_cents - refund_cents) > 0
  group by 1, 2
),
eligible_members as (
  select distinct
    m.month_start,
    c.member_id
  from months m
  join {{ ref('cards') }} c
    on c.card_type in ('悦享年卡', '家庭季卡')
    and c.valid_until > m.month_end
    and (c.ended_at is null or c.ended_at > m.month_end)
    and (
      c.valid_from < m.month_end
      or (
        c.valid_from = m.month_end
        and exists (
          select 1 from monthly_orders mo
          where mo.member_id = c.member_id
            and mo.month_start = m.month_start
            and mo.min_ordered_at < m.month_end
        )
      )
    )
)
select
  em.member_id || '_' || strftime(em.month_start, '%Y-%m-%d') as paid_member_month_id,
  em.member_id,
  em.month_start,
  coalesce(mo.valid_order_cnt, 0) as valid_order_cnt,
  coalesce(mo.net_sales_cents, 0) as net_sales_cents
from eligible_members em
left join monthly_orders mo
  on em.member_id = mo.member_id
  and em.month_start = mo.month_start