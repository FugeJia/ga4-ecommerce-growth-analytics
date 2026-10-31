-- True observed first_visit cohorts, not arbitrary first-in-extract users.
WITH firsts AS (
 SELECT user_key, min(event_date) AS cohort_date FROM events
 WHERE event_name = 'first_visit' GROUP BY 1
), members AS (
 SELECT * FROM firsts WHERE cohort_date BETWEEN $start AND $end
), activity AS (
 SELECT DISTINCT user_key, event_date FROM events
), horizons AS (SELECT unnest([1,7,30]) AS horizon)
SELECT date_trunc('week', m.cohort_date)::DATE AS cohort_week, h.horizon,
 count(*) FILTER (WHERE m.cohort_date + h.horizon <= $observation_end) AS eligible_users,
 count(*) FILTER (WHERE m.cohort_date + h.horizon <= $observation_end
   AND a.user_key IS NOT NULL) AS retained_users,
 count(*) FILTER (WHERE m.cohort_date + h.horizon <= $observation_end
   AND a.user_key IS NOT NULL)::DOUBLE /
 nullif(count(*) FILTER (WHERE m.cohort_date + h.horizon <= $observation_end), 0)
 AS retention_rate
FROM members m CROSS JOIN horizons h
LEFT JOIN activity a ON m.user_key = a.user_key AND a.event_date = m.cohort_date + h.horizon
GROUP BY 1,2 ORDER BY 1,2
