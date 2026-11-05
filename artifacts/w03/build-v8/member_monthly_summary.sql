WITH monthly_orders AS (
    SELECT
        DATE_TRUNC('month', ordered_at)::DATE AS month_start,
        (DATE_TRUNC('month', ordered_at) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AS month_end,
        member_id,
        COUNT(*) AS valid_order_count,
        SUM(paid_cents - refund_cents) AS net_sales_cents,
        BOOL_OR(ordered_at < (DATE_TRUNC('month', ordered_at) + INTERVAL '1 month' - INTERVAL '1 day')::DATE) AS has_prior_purchase
    FROM {{ ref('orders') }}
    WHERE status = 'paid' AND paid_cents > refund_cents
    GROUP BY 1, 2, 3
),
qualified_members AS (
    SELECT DISTINCT
        mo.month_start,
        mo.member_id
    FROM monthly_orders mo
    JOIN {{ ref('cards') }} c ON mo.member_id = c.member_id
    WHERE c.card_type IN ('悦享年卡', '家庭季卡')
      AND c.valid_until > mo.month_end
      AND (c.ended_at IS NULL OR c.ended_at > mo.month_end)
      AND (
          c.valid_from < mo.month_end
          OR (c.valid_from = mo.month_end AND mo.has_prior_purchase)
      )
)
SELECT
    mo.member_id || '_' || CAST(mo.month_start AS VARCHAR) AS member_month_id,
    mo.member_id,
    mo.month_start,
    mo.valid_order_count,
    mo.net_sales_cents,
    CASE WHEN qm.member_id IS NOT NULL THEN 1 ELSE 0 END AS is_paid_member
FROM monthly_orders mo
LEFT JOIN qualified_members qm
  ON mo.month_start = qm.month_start
 AND mo.member_id = qm.member_id