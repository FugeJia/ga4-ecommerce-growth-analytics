"""Shared SQL marts used by batch builds and interactive dashboard."""

from importlib.resources import files

import duckdb
import pandas as pd

PLACEHOLDERS = {"", "<Other>", "(not set)", "(data deleted)"}
COLUMNS = [
    "event_date",
    "event_ts",
    "event_name",
    "user_key",
    "session_id",
    "source",
    "medium",
    "device",
    "transaction_id",
    "revenue_usd",
]


def sql(name: str) -> str:
    return files("ga4_growth").joinpath("sql", name).read_text()


class Warehouse:
    def __init__(self, frame: pd.DataFrame):
        if not set(COLUMNS).issubset(frame.columns) or frame.empty:
            raise ValueError("Nonempty normalized event contract required")
        frame = frame[COLUMNS].copy()
        frame["event_date"] = pd.to_datetime(frame.event_date).dt.date
        frame["event_ts"] = pd.to_datetime(frame.event_ts, utc=True)
        if frame[["event_date", "event_ts", "event_name"]].isna().any().any():
            raise ValueError("Missing date, timestamp or event name")
        if not frame.event_name.str.fullmatch("[a-z][a-z0-9_]*").all():
            raise ValueError("Invalid event naming convention")
        frame["session_id"] = pd.to_numeric(frame.session_id, errors="raise").astype("Int64")
        frame["revenue_usd"] = pd.to_numeric(frame.revenue_usd, errors="raise")
        for col in ["user_key", "transaction_id"]:
            frame[col] = frame[col].astype("string").replace(list(PLACEHOLDERS), pd.NA)
        for col in ["source", "medium", "device"]:
            frame[col] = (
                frame[col]
                .astype("string")
                .fillna("(unknown)")
                .replace(list(PLACEHOLDERS), "(unknown)")
            )
        duplicate_count = int(frame.duplicated().sum())
        missing_users = int(frame.user_key.isna().sum())
        self.quality = dict(
            raw_events=len(frame),
            duplicate_normalized_rows=duplicate_count,
            missing_user_events=missing_users,
            missing_session_events=int(frame.session_id.isna().sum()),
            purchase_missing_transaction=int(
                ((frame.event_name == "purchase") & frame.transaction_id.isna()).sum()
            ),
        )
        # Keep quality evidence; exclude rows that cannot support person-level metrics.
        clean = frame.drop_duplicates().dropna(subset=["user_key"])
        if clean.empty:
            raise ValueError("No identifiable events after quarantine")
        self.con = duckdb.connect()
        self.con.register("input_events", clean)
        self.con.execute("CREATE TABLE events AS SELECT * FROM input_events")
        conflicts = self.query("""SELECT transaction_id FROM events WHERE event_name='purchase'
          AND transaction_id IS NOT NULL GROUP BY 1 HAVING count(DISTINCT user_key)>1
          OR count(DISTINCT revenue_usd)>1""")
        if not conflicts.empty:
            self.close()
            raise ValueError(
                "Conflicting transaction ownership or revenue; inspect source before build"
            )
        self.con.execute("CREATE TABLE sessions AS " + sql("sessions.sql"))
        self.con.execute("CREATE TABLE orders AS " + sql("orders.sql"))
        self.quality["purchase_orders_missing_revenue"] = int(
            self.query("SELECT count(*) AS n FROM orders WHERE revenue_usd IS NULL").iloc[0, 0]
        )
        self.quality["purchase_orders_negative_revenue"] = int(
            self.query("SELECT count(*) AS n FROM orders WHERE revenue_usd < 0").iloc[0, 0]
        )
        self.quality["clean_events"] = len(clean)
        self.start = clean.event_date.min()
        self.end = clean.event_date.max()

    def query(self, statement, params=None):
        return self.con.execute(statement, params or {}).df()

    def daily(self):
        return self.query(
            """WITH dates AS (
          SELECT unnest(generate_series($start::DATE,$end::DATE,INTERVAL 1 DAY))::DATE event_date
        ), activity AS (
          SELECT event_date, count(DISTINCT user_key) dau,
          count(DISTINCT user_key) FILTER (WHERE event_name='purchase') buyers,
          count(DISTINCT user_key) FILTER (WHERE event_name='first_visit') new_users,
          count(*) events FROM events GROUP BY 1
        ), sales AS (
          SELECT event_date, count(*) orders, sum(revenue_usd) revenue_usd FROM orders GROUP BY 1
        ) SELECT d.event_date, coalesce(a.dau,0) dau, coalesce(a.buyers,0) buyers,
          coalesce(a.new_users,0) new_users, coalesce(a.events,0) events,
          coalesce(s.orders,0) orders, s.revenue_usd,
          a.buyers::DOUBLE/nullif(a.dau,0) purchase_cvr
        FROM dates d LEFT JOIN activity a USING(event_date) LEFT JOIN sales s USING(event_date)
        ORDER BY 1""",
            {"start": self.start, "end": self.end},
        )

    def funnel(self):
        return self.query("""SELECT source,medium,device,user_type,
          count(*) sessions, count(view_ts) view_item, count(cart_ts) add_to_cart,
          count(checkout_ts) begin_checkout, count(purchase_ts) purchase
          FROM sessions GROUP BY 1,2,3,4 ORDER BY sessions DESC""")

    def retention(self, start=None, end=None, observation_end=None):
        return self.query(
            sql("retention.sql"),
            {
                "start": start or self.start,
                "end": end or self.end,
                "observation_end": observation_end or self.end,
            },
        )

    def rfm(self):
        return self.query(
            """WITH customers AS (
          SELECT user_key, date_diff('day',max(event_date),$as_of::DATE) recency_days,
            count(*) frequency, sum(revenue_usd) monetary_usd
          FROM orders GROUP BY 1
          HAVING count(*) FILTER(WHERE revenue_usd IS NULL OR revenue_usd<0)=0
        ) SELECT *, CASE
          WHEN recency_days<=30 AND frequency>=2 AND monetary_usd>=100 THEN 'high_value'
          WHEN recency_days<=30 THEN 'potential'
          WHEN recency_days<=60 THEN 'dormant' ELSE 'lapsed' END segment
        FROM customers ORDER BY monetary_usd DESC, user_key""",
            {"as_of": self.end},
        )

    def close(self):
        self.con.close()
