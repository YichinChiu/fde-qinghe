with valid_orders as (
  select
    order_id,
    member_id,
    store_id,
    ordered_at,
    (paid_cents - refund_cents) as net_sales_cents,
    row_number() over (partition by member_id order by ordered_at, order_id) as order_seq
  from {{ ref('orders') }}
  where status = 'paid' and (paid_cents - refund_cents) > 0
)
select
  order_id,
  member_id,
  store_id,
  ordered_at,
  net_sales_cents,
  order_seq
from valid_orders