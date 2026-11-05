SELECT
  order_id,
  member_id,
  store_id,
  ordered_at,
  (paid_cents - refund_cents) AS net_cents,
  ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY ordered_at, order_id) AS order_seq
FROM {{ ref('orders') }}
WHERE status = 'paid' AND (paid_cents - refund_cents > 0)