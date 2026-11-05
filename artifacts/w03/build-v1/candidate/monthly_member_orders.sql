SELECT
  member_id || '_' || STRFTIME(DATE_TRUNC('month', ordered_at)::DATE, '%Y-%m-%d') AS member_month_id,
  member_id,
  DATE_TRUNC('month', ordered_at)::DATE AS month_start,
  COUNT(order_id) AS valid_order_count
FROM {{ ref('orders') }}
WHERE status = 'paid' AND (paid_cents - refund_cents > 0)
GROUP BY member_id, DATE_TRUNC('month', ordered_at)::DATE