import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from importlib.metadata import version
from pathlib import Path

from ga4_growth.demo import generate_demo
from ga4_growth.pipeline import build
from ga4_growth.provenance import file_sha256
from ga4_growth.warehouse import sql


def save_input(frame, output, metadata):
    if output.exists() or output.with_suffix(".manifest.json").exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    metadata.update(
        sha256=file_sha256(output),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        package_version=version("ga4-growth-analytics"),
    )
    output.with_suffix(".manifest.json").write_text(json.dumps(metadata, indent=2))


def extract(args):
    from google.cloud import bigquery

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if not date(2020, 11, 1) <= start <= end <= date(2021, 1, 31):
        raise ValueError("Range must be within 2020-11-01 .. 2021-01-31")
    if args.max_bytes <= 0:
        raise ValueError("max-bytes must be positive")
    if args.execute and (
        args.output.exists() or args.output.with_suffix(".manifest.json").exists()
    ):
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    client = bigquery.Client(project=args.project, location="US")
    params = [
        bigquery.ScalarQueryParameter("start_suffix", "STRING", start.strftime("%Y%m%d")),
        bigquery.ScalarQueryParameter("end_suffix", "STRING", end.strftime("%Y%m%d")),
    ]
    config = bigquery.QueryJobConfig(
        query_parameters=params,
        dry_run=True,
        use_query_cache=False,
        maximum_bytes_billed=args.max_bytes,
    )
    statement = sql("extract.sql")
    estimate = client.query(statement, job_config=config, location="US")
    print(
        json.dumps(
            {
                "dry_run": True,
                "estimated_bytes": estimate.total_bytes_processed,
                "max_bytes": args.max_bytes,
            }
        )
    )
    if estimate.total_bytes_processed > args.max_bytes:
        raise ValueError("Estimated scan exceeds cap")
    if not args.execute:
        return
    config.dry_run = False
    job = client.query(statement, job_config=config, location="US")
    frame = job.result().to_dataframe(create_bqstorage_client=False)
    save_input(
        frame,
        args.output,
        dict(
            data_mode="bigquery_public",
            source="bigquery-public-data.ga4_obfuscated_sample_ecommerce",
            query_sha256=hashlib.sha256(statement.encode()).hexdigest(),
            start=args.start,
            end=args.end,
            job_id=job.job_id,
            location="US",
            bytes_processed=job.total_bytes_processed,
            bytes_billed=job.total_bytes_billed,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description="GA4 reproducible growth analytics")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Generate clearly labeled synthetic events")
    demo.add_argument("--output", type=Path, default=Path("data/demo/events.parquet"))
    demo.add_argument("--seed", type=int, default=42)
    ext = sub.add_parser("extract", help="BigQuery dry run by default; --execute downloads")
    ext.add_argument("--project", required=True)
    ext.add_argument("--start", default="2020-11-01")
    ext.add_argument("--end", default="2021-01-31")
    ext.add_argument("--max-bytes", type=int, default=10_000_000_000)
    ext.add_argument("--execute", action="store_true")
    ext.add_argument("--output", type=Path, default=Path("data/public/events.parquet"))
    run = sub.add_parser("build")
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "demo":
        save_input(
            generate_demo(args.seed),
            args.output,
            dict(data_mode="synthetic_demo", seed=args.seed, source="seeded_generator"),
        )
    elif args.command == "extract":
        extract(args)
    else:
        print(json.dumps(build(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
