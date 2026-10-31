"""Seeded synthetic fixture, never a substitute for Google's dataset."""

import random
from datetime import date, datetime, timedelta, timezone

import pandas as pd


def generate_demo(seed: int = 42, users: int = 1800) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    start = date(2020, 11, 1)
    for i in range(users):
        first = start + timedelta(days=rng.randrange(92))
        source, medium = rng.choice(
            [
                ("google", "organic"),
                ("google", "cpc"),
                ("(direct)", "(none)"),
                ("newsletter", "email"),
            ]
        )
        device = rng.choice(["desktop", "mobile", "tablet"])
        days = sorted(
            set(
                [first]
                + [first + timedelta(days=rng.randrange(1, 45)) for _ in range(rng.randrange(5))]
            )
        )
        for day in days:
            if day > date(2021, 1, 31):
                continue
            sid = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()) + i
            ts = datetime.combine(day, datetime.min.time(), timezone.utc) + timedelta(hours=10)
            path = ["session_start", "page_view"]
            if day == first:
                path.insert(0, "first_visit")
            if rng.random() < 0.78:
                path += ["view_item"]
                if rng.random() < (0.36 if device == "desktop" else 0.23):
                    path += ["add_to_cart"]
                    if rng.random() < 0.65:
                        path += ["begin_checkout"]
                        if rng.random() < 0.58:
                            path += ["purchase"]
            for j, name in enumerate(path):
                rows.append(
                    dict(
                        event_date=day,
                        event_ts=ts + timedelta(seconds=j * 10),
                        event_name=name,
                        user_key=f"synthetic-{i:05}",
                        session_id=sid,
                        source=source,
                        medium=medium,
                        device=device,
                        transaction_id=f"demo-order-{i}-{sid}" if name == "purchase" else None,
                        revenue_usd=round(rng.uniform(12, 180), 2) if name == "purchase" else None,
                    )
                )
    return pd.DataFrame(rows)
