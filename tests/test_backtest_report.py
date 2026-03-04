"""Tests for backtest reporting and CSV export."""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from src.backtest_report import (
    format_comparison_table,
    format_position_breakdown,
    format_tuning_results,
    format_before_after,
    export_results_csv,
    export_tuning_csv,
    print_full_report,
)
from src.backtest import BacktestResult, SeasonBacktestResults
from src.models import StrategyConfig, Position


def _make_mock_season_results():
    iterations = [
        BacktestResult(
            draft_position=pos,
            vbd_team_points=250.0 + pos * 5,
            adp_team_points=230.0 + pos * 3,
            random_team_points=200.0 + pos * 2,
            all_team_points=[240.0] * 12,
            vbd_picks=[],
            bust_count=2,
            hit_count=5,
        )
        for pos in range(1, 13)
    ]
    return SeasonBacktestResults(
        season=2024,
        iterations=iterations,
        config=StrategyConfig(),
        mean_vbd_points=280.0,
        mean_adp_points=250.0,
        mean_random_points=220.0,
        mean_bust_rate=0.13,
        mean_hit_rate=0.33,
        points_by_position={i: 250.0 + i * 5 for i in range(1, 13)},
    )


def test_format_comparison_table_returns_string():
    results = _make_mock_season_results()
    table_str = format_comparison_table(results)
    assert isinstance(table_str, str)
    assert "VBD" in table_str
    assert "ADP" in table_str
    assert "Random" in table_str


def test_format_comparison_table_contains_points():
    results = _make_mock_season_results()
    table_str = format_comparison_table(results)
    # Should contain the mean points values
    assert "280" in table_str
    assert "250" in table_str
    assert "220" in table_str


def test_format_position_breakdown_returns_string():
    results = _make_mock_season_results()
    table_str = format_position_breakdown(results)
    assert isinstance(table_str, str)
    assert len(table_str) > 0


def test_format_position_breakdown_contains_positions():
    results = _make_mock_season_results()
    table_str = format_position_breakdown(results)
    # Should contain position numbers 1-12
    for pos in range(1, 13):
        assert str(pos) in table_str


def test_format_tuning_results():
    @dataclass
    class MockTunerResult:
        config: StrategyConfig
        mean_points: float
        iterations_run: int
        season_results: list = field(default_factory=list)

    tuner_results = [
        MockTunerResult(
            config=StrategyConfig(need_boost=1.2, scarcity_penalty=0.9),
            mean_points=290.0,
            iterations_run=100,
        ),
        MockTunerResult(
            config=StrategyConfig(need_boost=1.1, scarcity_penalty=0.7),
            mean_points=275.0,
            iterations_run=100,
        ),
    ]
    table_str = format_tuning_results(tuner_results)
    assert isinstance(table_str, str)
    assert "290" in table_str
    assert "275" in table_str


def test_format_before_after():
    current = StrategyConfig(need_boost=1.15, scarcity_penalty=0.8)
    best = StrategyConfig(need_boost=1.25, scarcity_penalty=0.9)
    table_str = format_before_after(current, best, 250.0, 290.0)
    assert isinstance(table_str, str)
    assert "250" in table_str
    assert "290" in table_str


def test_export_results_csv(tmp_path):
    results = _make_mock_season_results()
    filepath = tmp_path / "test_results.csv"
    export_results_csv(results, str(filepath))
    assert filepath.exists()
    with open(filepath) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 12
    assert "draft_position" in rows[0]
    assert "vbd_team_points" in rows[0]


def test_export_results_csv_values(tmp_path):
    results = _make_mock_season_results()
    filepath = tmp_path / "test_results.csv"
    export_results_csv(results, str(filepath))
    with open(filepath) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # First iteration: draft_position=1, vbd=255.0, adp=233.0, random=202.0
    assert rows[0]["draft_position"] == "1"
    assert float(rows[0]["vbd_team_points"]) == 255.0
    assert float(rows[0]["adp_team_points"]) == 233.0
    assert float(rows[0]["random_team_points"]) == 202.0
    assert rows[0]["bust_count"] == "2"
    assert rows[0]["hit_count"] == "5"


def test_export_tuning_csv(tmp_path):
    @dataclass
    class MockTunerResult:
        config: StrategyConfig
        mean_points: float
        iterations_run: int
        season_results: list = field(default_factory=list)

    tuner_results = [
        MockTunerResult(
            config=StrategyConfig(),
            mean_points=280.0,
            iterations_run=100,
        ),
    ]
    filepath = tmp_path / "tuning.csv"
    export_tuning_csv(tuner_results, str(filepath))
    assert filepath.exists()
    with open(filepath) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert "mean_points" in rows[0]
    assert "need_boost" in rows[0]


def test_print_full_report():
    from rich.console import Console
    results = _make_mock_season_results()
    console = Console(record=True)
    print_full_report([results], console)
    output = console.export_text()
    assert "2024" in output
    assert len(output) > 0
