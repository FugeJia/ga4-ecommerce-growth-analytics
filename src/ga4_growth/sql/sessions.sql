-- One row per (user_key, session_id), anchored to its earliest observed event.
-- Strict timestamps: ties are ambiguous in this historical schema and not promoted.
WITH users AS (
 SELECT user_key, min(event_date) AS first_observed_date,
 min(event_date) FILTER (WHERE event_name='first_visit') AS first_visit_date
 FROM events GROUP BY 1
), starts AS (
 SELECT user_key, session_id,
  arg_min(event_date, event_ts) AS session_date,
  arg_min(source, event_ts) AS source, arg_min(medium, event_ts) AS medium,
  arg_min(device, event_ts) AS device,
  min(event_ts) FILTER (WHERE event_name = 'view_item') AS view_ts
 FROM events WHERE session_id IS NOT NULL GROUP BY 1,2
), carts AS (
 SELECT s.*, min(e.event_ts) FILTER (
  WHERE e.event_name = 'add_to_cart' AND e.event_ts > s.view_ts) AS cart_ts
 FROM starts s LEFT JOIN events e USING (user_key, session_id) GROUP BY ALL
), checkouts AS (
 SELECT s.*, min(e.event_ts) FILTER (
  WHERE e.event_name = 'begin_checkout' AND e.event_ts > s.cart_ts) AS checkout_ts
 FROM carts s LEFT JOIN events e USING (user_key, session_id) GROUP BY ALL
), ordered AS (
SELECT s.*, min(e.event_ts) FILTER (
 WHERE e.event_name = 'purchase' AND e.event_ts > s.checkout_ts) AS purchase_ts
FROM checkouts s LEFT JOIN events e USING (user_key, session_id) GROUP BY ALL

)
SELECT o.*, CASE WHEN u.first_visit_date = o.session_date THEN 'new_observed'
 WHEN u.first_observed_date < o.session_date THEN 'returning_observed'
 ELSE 'unknown' END AS user_type
FROM ordered o JOIN users u USING (user_key)
