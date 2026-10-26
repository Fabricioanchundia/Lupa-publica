import argparse

import pytest

from lupa_publica.cli import build_parser, parse_month
from lupa_publica.extract import Month


def test_parse_month_accepts_yyyy_mm() -> None:
    assert parse_month("2025-02") == Month(2025, 2)


@pytest.mark.parametrize("text", ["2025", "2025-13", "febrero", "2025-02-01"])
def test_parse_month_rejects_bad_input(text: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_month(text)


def test_ingest_defaults_to_six_months() -> None:
    args = build_parser().parse_args(["ingest"])

    assert args.command == "ingest"
    assert args.months == 6


def test_backfill_requires_a_range() -> None:
    args = build_parser().parse_args(["backfill", "--from", "2025-01", "--to", "2025-03"])

    assert (args.start, args.end) == (Month(2025, 1), Month(2025, 3))


def test_report_accepts_an_output_path() -> None:
    args = build_parser().parse_args(["report", "--output", "docs/coverage-report.md"])

    assert args.command == "report"
    assert str(args.output) == "docs/coverage-report.md"
