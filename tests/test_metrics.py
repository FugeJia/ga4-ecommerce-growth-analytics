from datetime import date

import pandas as pd
import pytest

from ga4_growth.demo import generate_demo
from ga4_growth.statistics import analyze_experiment, detect_anomalies, sample_size
from ga4_growth.warehouse import Warehouse


def events(rows):
    result = []
    for user, sid, day, second, name, transaction, revenue in rows:
        result.append(
            dict(
                user_key=user,
                session_id=sid,
                event_date=day,
                event_ts=f"{day}T10:00:{second:02}Z",
                event_name=name,
                transaction_id=transaction,
                revenue_usd=revenue,
                source="google",
                medium="organic",
                device="desktop",
            )
        )
    return pd.DataFrame(result)


def test_funnel_order_ties_and_user_session_collision():
    frame = events(
        [
            ("a", 1, "2020-11-01", 0, "view_item", None, None),
            ("a", 1, "2020-11-01", 1, "add_to_cart", None, None),
            ("a", 1, "2020-11-01", 2, "begin_checkout", None, None),
            ("a", 1, "2020-11-01", 3, "purchase", "t1", 20),
            ("b", 1, "2020-11-01", 0, "add_to_cart", None, None),
            ("b", 1, "2020-11-01", 1, "view_item", None, None),
            ("b", 1, "2020-11-01", 2, "purchase", "t2", 30),
            ("c", 1, "2020-11-01", 0, "view_item", None, None),
            ("c", 1, "2020-11-01", 0, "add_to_cart", None, None),
        ]
    )
    w = Warehouse(frame)
    try:
        row = w.funnel().iloc[0]
        assert list(row[["view_item", "add_to_cart", "begin_checkout", "purchase"]]) == [3, 1, 1, 1]
        assert w.daily().orders.sum() == 2
    finally:
        w.close()


def test_retention_censoring_exact_day_and_week_denominators():
    frame = events(
        [
            ("a", 1, "2021-01-01", 0, "first_visit", None, None),
            ("a", 2, "2021-01-08", 0, "page_view", None, None),
            ("b", 3, "2021-01-08", 0, "first_visit", None, None),
            ("c", 4, "2021-01-09", 0, "first_visit", None, None),
            ("x", 5, "2021-01-09", 1, "page_view", None, None),
        ]
    )
    w = Warehouse(frame)
    try:
        r = w.retention()
        first = r[(r.cohort_week == pd.Timestamp("2020-12-28")) & (r.horizon == 7)].iloc[0]
        assert first.eligible_users == 1 and first.retention_rate == 1
        immature = r[(r.cohort_week == pd.Timestamp("2021-01-04")) & (r.horizon == 7)].iloc[0]
        assert immature.eligible_users == 0 and pd.isna(immature.retention_rate)
        assert r[r.horizon == 1].eligible_users.sum() == 2  # x has no first_visit
    finally:
        w.close()


def test_order_dedup_and_collision_gate():
    frame = events(
        [
            ("a", 1, "2020-11-01", 1, "purchase", "t1", 20),
            ("a", 1, "2020-11-01", 2, "purchase", "t1", 20),
        ]
    )
    w = Warehouse(pd.concat([frame, frame.iloc[:1]], ignore_index=True))
    try:
        assert w.daily().orders.sum() == 1
        assert w.daily().revenue_usd.sum() == 20
        assert w.quality["duplicate_normalized_rows"] == 1
    finally:
        w.close()
    frame.loc[1, "user_key"] = "b"
    with pytest.raises(ValueError, match="Conflicting"):
        Warehouse(frame)


def test_unknown_ids_and_missing_revenue_not_in_rfm():
    frame = events(
        [
            ("a", 1, "2020-11-01", 0, "purchase", "t1", None),
            ("<Other>", 2, "2020-11-01", 1, "page_view", None, None),
        ]
    )
    w = Warehouse(frame)
    try:
        assert w.quality["missing_user_events"] == 1
        assert w.quality["purchase_orders_missing_revenue"] == 1
        assert w.rfm().empty
    finally:
        w.close()


def test_rfm_uses_observation_end_not_computer_clock():
    frame = events(
        [
            ("a", 1, "2020-11-01", 0, "purchase", "t1", 60),
            ("a", 2, "2021-01-25", 0, "purchase", "t2", 60),
            ("b", 3, "2020-11-01", 0, "purchase", "t3", 20),
            ("z", 4, "2021-01-31", 0, "page_view", None, None),
        ]
    )
    w = Warehouse(frame)
    try:
        r = w.rfm().set_index("user_key")
        assert r.loc["a", "segment"] == "high_value"
        assert r.loc["a", "recency_days"] == 6
        assert r.loc["b", "segment"] == "lapsed"
    finally:
        w.close()


def test_calendar_spine_and_no_current_day_baseline_leak():
    dates = pd.date_range("2020-11-01", periods=30)
    base = pd.DataFrame(
        dict(event_date=dates, dau=[100, 101] * 14 + [100, 10000], purchase_cvr=[0.1] * 30)
    )
    result = detect_anomalies(base)
    assert result.iloc[-1].dau_baseline < 102
    assert result.iloc[-1].dau_alert
    w = Warehouse(
        events(
            [
                ("a", 1, "2020-11-01", 0, "page_view", None, None),
                ("a", 2, "2020-11-03", 0, "page_view", None, None),
            ]
        )
    )
    try:
        assert w.daily().dau.tolist() == [1, 0, 1]
    finally:
        w.close()


def test_experiment_null_effect_sparse_and_srm():
    frame = pd.DataFrame(
        dict(
            user_key=range(200),
            variant=["control"] * 100 + ["treatment"] * 100,
            converted=([1] * 20 + [0] * 80) * 2,
        )
    )
    result = analyze_experiment(frame)
    assert result["p_value"] == 1 and result["absolute_lift"] == 0
    assert result["ci_low"] < 0 < result["ci_high"]
    frame.converted = 0
    assert analyze_experiment(frame)["method"] == "fisher_exact"
    unbalanced = frame.copy()
    unbalanced["variant"] = ["control"] * 190 + ["treatment"] * 10
    assert analyze_experiment(unbalanced)["decision"] == "invalid_srm"
    with pytest.raises(ValueError):
        analyze_experiment(pd.concat([frame, frame.iloc[:1]]))
    assert 6000 < sample_size(0.2, 0.02) < 7000
    with pytest.raises(ValueError):
        sample_size(0.99, 0.02)


def test_seed_is_reproducible():
    pd.testing.assert_frame_equal(generate_demo(users=10), generate_demo(users=10))
    assert generate_demo(users=10).event_date.max() <= date(2021, 1, 31)


def test_funnel_user_evidence_and_missing_session_exclusion():
    frame = events(
        [
            ("a", 1, "2020-11-01", 0, "first_visit", None, None),
            ("a", 1, "2020-11-01", 1, "view_item", None, None),
            ("a", 2, "2020-11-02", 0, "view_item", None, None),
            ("b", 3, "2020-11-02", 0, "view_item", None, None),
            ("c", None, "2020-11-02", 1, "purchase", "t1", 20),
        ]
    )
    w = Warehouse(frame)
    try:
        result = w.funnel().set_index("user_type")
        assert result.loc["new_observed", "view_item"] == 1
        assert result.loc["returning_observed", "view_item"] == 1
        assert result.loc["unknown", "view_item"] == 1
        assert result.sessions.sum() == 3
        assert w.daily().orders.sum() == 1
        assert w.quality["missing_session_events"] == 1
    finally:
        w.close()
