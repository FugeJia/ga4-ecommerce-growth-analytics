-- Conflicting transaction ownership is rejected before this query.
SELECT * FROM events
WHERE event_name = 'purchase' AND transaction_id IS NOT NULL
QUALIFY row_number() OVER (
 PARTITION BY transaction_id ORDER BY event_ts DESC, revenue_usd DESC NULLS LAST,
 user_key, session_id NULLS LAST, source, medium, device, event_date
) = 1
