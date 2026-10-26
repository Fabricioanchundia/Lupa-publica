"""Command-line interface: ``lupa ingest``, ``lupa backfill`` and ``lupa report``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from lupa_publica.extract import Month
from lupa_publica.pipeline import DataPaths, IngestResult, ingest, last_months, month_range
from lupa_publica.report import build_report, render_markdown


def parse_month(text: str) -> Month:
    """Parse ``YYYY-MM`` into a Month (used by argparse)."""
    try:
        year, month = (int(part) for part in text.split("-"))
        return Month(year, month)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {text!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lupa", description="Lupa Pública data pipeline")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="default: data")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logs")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = commands.add_parser(
        "ingest", help="refresh the most recent months (rolling window, re-downloads)"
    )
    ingest_cmd.add_argument("--months", type=int, default=6, help="window size (default: 6)")

    backfill_cmd = commands.add_parser(
        "backfill", help="load a historical range, skipping files already downloaded"
    )
    backfill_cmd.add_argument("--from", dest="start", type=parse_month, required=True)
    backfill_cmd.add_argument("--to", dest="end", type=parse_month, required=True)

    report_cmd = commands.add_parser("report", help="data coverage report in Markdown")
    report_cmd.add_argument(
        "--output", type=Path, help="write the report to this file instead of printing it"
    )
    return parser


def print_summary(result: IngestResult) -> None:
    print(f"\n{'month':<8} {'processes':>10} {'rejected':>9} {'duplicates':>11}")
    for report in result.months:
        print(
            f"{report.month:<8} {report.written:>10,} {report.rejected:>9,} "
            f"{report.duplicates:>11,}"
        )
    for label, error in result.failures.items():
        print(f"{label:<8} FAILED: {error}")
    if result.load is not None:
        print(
            f"\nbronze.releases: {result.load.rows:,} processes "
            f"from {result.load.files} monthly files"
        )
    print("status:", "OK" if result.ok else "FAILED")


def run_report(paths: DataPaths, output: Path | None) -> int:
    text = render_markdown(build_report(paths.db))
    if output is None:
        print(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"report written to {output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    paths = DataPaths(args.data_dir)

    if args.command == "report":
        return run_report(paths, args.output)

    if args.command == "ingest":
        if args.months < 1:
            parser.error("--months must be at least 1")
        months = last_months(args.months, date.today())
        refresh = True
    else:
        try:
            months = month_range(args.start, args.end)
        except ValueError as exc:
            parser.error(str(exc))
        refresh = False

    result = ingest(months, paths, refresh=refresh)
    print_summary(result)
    return 0 if result.ok else 1
