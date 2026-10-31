import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ga4_growth.provenance import verify_input
from ga4_growth.statistics import detect_anomalies
from ga4_growth.warehouse import Warehouse


def build(input_path: Path, output: Path):
    provenance = verify_input(input_path)
    digest = provenance["sha256"]
    warehouse = Warehouse(pd.read_parquet(input_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ga4-build-", dir=output.parent))
    try:
        marts = dict(
            daily=detect_anomalies(warehouse.daily()),
            funnel=warehouse.funnel(),
            retention=warehouse.retention(),
            rfm=warehouse.rfm(),
        )
        for name, frame in marts.items():
            frame.to_csv(staging / f"{name}.csv", index=False)
        (staging / "quality.json").write_text(json.dumps(warehouse.quality, indent=2))
        manifest = {
            **provenance,
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_sha": provenance.get("git_sha"),
            "metrics_version": "1.0.0",
            "observation_start": str(warehouse.start),
            "observation_end": str(warehouse.end),
            "input_sha256": digest,
            "marts": {k: len(v) for k, v in marts.items()},
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
        daily, funnel = marts["daily"], marts["funnel"]
        totals = funnel[["view_item", "add_to_cart", "begin_checkout", "purchase"]].sum()
        report = f"""# Run report

Data mode: **{provenance["data_mode"]}**

Observed range: {warehouse.start} to {warehouse.end}.

- Normalized events: {warehouse.quality["clean_events"]:,}
- Distinct observed users: {warehouse.query("SELECT count(DISTINCT user_key) FROM events").iloc[0, 0]:,}
- Sessions with view_item: {totals["view_item"]:,}
- Strict ordered purchase sessions: {totals["purchase"]:,}
- Deduplicated orders: {int(daily.orders.sum()):,}

Synthetic results demonstrate implementation only. Public results describe obfuscated historical data.
No causal impact, live deployment, or collection completeness is established.
"""
        (staging / "report.md").write_text(report)
        # Publish only a successful full build; refuse accidental directory replacement.
        if output.exists():
            raise FileExistsError(f"{output} exists; choose a new output directory")
        staging.rename(output)
        return manifest
    finally:
        warehouse.close()
        if staging.exists():
            shutil.rmtree(staging)
