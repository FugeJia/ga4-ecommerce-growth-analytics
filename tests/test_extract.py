from argparse import Namespace
from unittest.mock import Mock

import pytest
from google.cloud import bigquery

from ga4_growth.cli import extract
from ga4_growth.demo import generate_demo
from ga4_growth.provenance import verify_input


def args(tmp_path, **overrides):
    values = dict(
        project="test-project",
        start="2020-11-01",
        end="2020-11-02",
        max_bytes=1000,
        execute=False,
        output=tmp_path / "public.parquet",
    )
    return Namespace(**(values | overrides))


def test_extract_default_is_dry_run_and_cost_cap_is_enforced(monkeypatch, tmp_path):
    calls = []
    client = Mock()

    def query(statement, job_config, location):
        calls.append((statement, job_config.dry_run, job_config.maximum_bytes_billed, location))
        return Mock(total_bytes_processed=500)

    client.query.side_effect = query
    monkeypatch.setattr(bigquery, "Client", Mock(return_value=client))
    extract(args(tmp_path))
    assert len(calls) == 1 and calls[0][1:] == (True, 1000, "US")
    assert not (tmp_path / "public.parquet").exists()
    with pytest.raises(ValueError, match="cap"):
        extract(args(tmp_path, max_bytes=100))
    assert all(call[1] for call in calls)


def test_extract_explicit_execution_saves_verified_manifest(monkeypatch, tmp_path):
    client = Mock()
    result = Mock()
    result.to_dataframe.return_value = generate_demo(users=5)
    job = Mock(job_id="unit-test-job", total_bytes_processed=500, total_bytes_billed=500)
    job.result.return_value = result
    client.query.side_effect = [Mock(total_bytes_processed=500), job]
    monkeypatch.setattr(bigquery, "Client", Mock(return_value=client))
    extract(args(tmp_path, execute=True))
    metadata = verify_input(tmp_path / "public.parquet")
    # This is a mocked API contract test, not a real public-data extraction.
    assert metadata["data_mode"] == "bigquery_public"
    assert metadata["job_id"] == "unit-test-job"
    assert client.query.call_count == 2
    result.to_dataframe.assert_called_once_with(create_bqstorage_client=False)


def test_extract_invalid_date_stops_before_client_creation(monkeypatch, tmp_path):
    factory = Mock()
    monkeypatch.setattr(bigquery, "Client", factory)
    with pytest.raises(ValueError):
        extract(args(tmp_path, start="2022-01-01"))
    factory.assert_not_called()
