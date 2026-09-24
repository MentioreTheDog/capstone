"""SQL-запрос сборки признаков на уровне заказа.

v2 — исправлено вычисление опоздания относительно обещанной даты.

Причина правки (найдена на этапе EDA): order_estimated_delivery_date хранится
как календарная дата с временем 00:00:00, а order_delivered_customer_date —
с реальным временем вручения. Прямая дробная разница через JULIANDAY
засчитывала доставку в 15:00 в обещанный день как "опоздание на 0.6 дня",
из-за чего доля опоздавших завышалась с 6.7% до 8.0%, а сигнал по самому
важному признаку размывался. Теперь обе даты приводятся к DATE().
"""

FEATURE_SQL = """
WITH item_agg AS (
    SELECT order_id,
           COUNT(*)                   AS n_items,
           COUNT(DISTINCT seller_id)  AS n_sellers,
           SUM(price)                 AS total_price,
           SUM(freight_value)         AS total_freight,
           MAX(price)                 AS max_item_price
    FROM order_items GROUP BY order_id
),
pay_agg AS (
    SELECT order_id,
           SUM(payment_value)        AS payment_value,
           MAX(payment_installments) AS installments,
           COUNT(*)                  AS n_payment_rows
    FROM order_payments GROUP BY order_id
),
pay_main AS (
    SELECT order_id, payment_type FROM (
        SELECT order_id, payment_type,
               ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY payment_value DESC) rn
        FROM order_payments
    ) WHERE rn = 1
),
main_item AS (
    SELECT order_id, product_id, seller_id FROM (
        SELECT order_id, product_id, seller_id,
               ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY price DESC) rn
        FROM order_items
    ) WHERE rn = 1
),
rev AS (
    SELECT order_id, MIN(review_score) AS review_score
    FROM order_reviews GROUP BY order_id
),
base AS (
    SELECT o.order_id, o.customer_id,
           o.order_purchase_timestamp, o.order_approved_at,
           o.order_delivered_carrier_date, o.order_delivered_customer_date,
           o.order_estimated_delivery_date
    FROM orders o
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
)
SELECT
    b.order_id,
    b.order_purchase_timestamp,
    rev.review_score,

    -- Сроки. late_days считается по календарным дням (см. docstring модуля):
    -- положительное значение = опоздание относительно обещанной даты.
    JULIANDAY(DATE(b.order_delivered_customer_date))
        - JULIANDAY(DATE(b.order_estimated_delivery_date))                             AS late_days,
    CASE WHEN JULIANDAY(DATE(b.order_delivered_customer_date))
            > JULIANDAY(DATE(b.order_estimated_delivery_date))
         THEN 1 ELSE 0 END                                                             AS is_late,
    JULIANDAY(b.order_delivered_customer_date) - JULIANDAY(b.order_purchase_timestamp) AS delivery_days,
    JULIANDAY(b.order_estimated_delivery_date) - JULIANDAY(b.order_purchase_timestamp) AS promised_days,
    JULIANDAY(b.order_delivered_carrier_date)  - JULIANDAY(b.order_approved_at)        AS seller_handling_days,
    (JULIANDAY(b.order_approved_at) - JULIANDAY(b.order_purchase_timestamp)) * 24      AS approval_hours,
    CAST(strftime('%w', b.order_purchase_timestamp) AS INTEGER)                        AS purchase_dow,
    CAST(strftime('%m', b.order_purchase_timestamp) AS INTEGER)                        AS purchase_month,

    -- Состав заказа
    ia.n_items, ia.n_sellers, ia.total_price, ia.total_freight, ia.max_item_price,

    -- Оплата
    pa.payment_value, pa.installments, pa.n_payment_rows,
    pm.payment_type,

    -- Товар
    COALESCE(t.product_category_name_english, 'unknown') AS product_category,
    pr.product_weight_g, pr.product_photos_qty,
    pr.product_length_cm * pr.product_height_cm * pr.product_width_cm AS product_volume_cm3,

    -- География
    c.customer_state, s.seller_state,
    CASE WHEN c.customer_state = s.seller_state THEN 1 ELSE 0 END AS same_state
FROM base b
JOIN rev            ON rev.order_id = b.order_id
JOIN item_agg  ia   ON ia.order_id  = b.order_id
JOIN pay_agg   pa   ON pa.order_id  = b.order_id
JOIN pay_main  pm   ON pm.order_id  = b.order_id
JOIN main_item mi   ON mi.order_id  = b.order_id
JOIN customers c    ON c.customer_id = b.customer_id
LEFT JOIN products pr ON pr.product_id = mi.product_id
LEFT JOIN sellers  s  ON s.seller_id   = mi.seller_id
LEFT JOIN product_category_name_translation t
       ON t.product_category_name = pr.product_category_name
"""
