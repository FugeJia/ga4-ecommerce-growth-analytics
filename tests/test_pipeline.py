import json

import pytest
from streamlit.testing.v1 import AppTest

from ga4_growth.cli import save_input
from ga4_growth.demo import generate_demo
from ga4_growth.pipeline import build
from ga4_growth.warehouse import sql


def test_provenance_and_atomic_build(tmp_path):
    source = tmp_path / "events.parquet"
    save_input(generate_demo(users=30), source, {"data_mode": "synthetic_demo", "seed": 42})
    out = tmp_path / "marts"
    build(source, out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["data_mode"] == "synthetic_demo"
    assert set(manifest["marts"]) == {"daily", "funnel", "retention", "rfm"}
    assert (out / "report.md").exists()
    with pytest.raises(FileExistsError):
        build(source, out)
    sidecar = source.with_suffix(".manifest.json")
    metadata = json.loads(sidecar.read_text())
    metadata["sha256"] = "bad"
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="hash"):
        build(source, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_bigquery_sql_parses():
    import sqlglot

    assert sqlglot.parse_one(sql("extract.sql"), read="bigquery") is not None
    assert "_TABLE_SUFFIX BETWEEN @start_suffix AND @end_suffix" in sql("extract.sql")


def test_dashboard_renders():
    # CI prepares the default demo before executing the suite.
    app = AppTest.from_file("app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value.startswith("GA4 Growth Lab")
    assert len(app.metric) == 5
    assert len(app.warning) == 1


def test_dashboard_filter_recomputes_scope():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    all_users = int(app.metric[0].value.replace(",", ""))
    app.multiselect[0].select("google").run()
    assert not app.exception
    assert 0 < int(app.metric[0].value.replace(",", "")) < all_users
    app.multiselect[1].select("mobile").run()
    assert not app.exception
