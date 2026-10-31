-- Standard SQL; historic schema only. No modern session attribution columns.
-- Correlated parameter lookups avoid multiplying events by UNNEST(items).
SELECT
 PARSE_DATE('%Y%m%d', event_date) AS event_date,
 TIMESTAMP_MICROS(event_timestamp) AS event_ts,
 event_name,
 user_pseudo_id AS user_key,
 (SELECT MAX(value.int_value) FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
 COALESCE(NULLIF(traffic_source.source, ''), '(unknown)') AS source,
 COALESCE(NULLIF(traffic_source.medium, ''), '(unknown)') AS medium,
 COALESCE(device.category, '(unknown)') AS device,
 NULLIF(ecommerce.transaction_id, '') AS transaction_id,
 ecommerce.purchase_revenue_in_usd AS revenue_usd
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start_suffix AND @end_suffix
