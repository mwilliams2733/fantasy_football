"""Backtest reporting module with Rich console output and CSV export."""

import csv
import math
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.backtest import SeasonBacktestResults
from src.models import StrategyConfig, Position


def _compute_std_dev(values: list[float], mean: float) -> float:
    """Compute standard deviation given values and their mean."""
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _win_rate(target: list[float], opponent: list[float]) -> float:
    """Compute fraction of iterations where target beats opponent."""
    if not target or not opponent:
        return 0.0
    wins = sum(1 for t, o in zip(target, opponent) if t > o)
    return wins / len(target)


def format_comparison_table(results: SeasonBacktestResults) -> str:
    """Create a Rich Table comparing VBD vs ADP vs Random strategies.

    Columns: Strategy, Mean Points, Std Dev, Win Rate vs others.
    Rendered to string using Console(record=True).
    """
    iterations = results.iterations

    vbd_pts = [r.vbd_team_points for r in iterations]
    adp_pts = [r.adp_team_points for r in iterations]
    rand_pts = [r.random_team_points for r in iterations]

    vbd_std = _compute_std_dev(vbd_pts, results.mean_vbd_points)
    adp_std = _compute_std_dev(adp_pts, results.mean_adp_points)
    rand_std = _compute_std_dev(rand_pts, results.mean_random_points)

    vbd_vs_adp = _win_rate(vbd_pts, adp_pts)
    vbd_vs_rand = _win_rate(vbd_pts, rand_pts)
    adp_vs_vbd = _win_rate(adp_pts, vbd_pts)
    adp_vs_rand = _win_rate(adp_pts, rand_pts)
    rand_vs_vbd = _win_rate(rand_pts, vbd_pts)
    rand_vs_adp = _win_rate(rand_pts, adp_pts)

    table = Table(title=f"Strategy Comparison - {results.season} Season")
    table.add_column("Strategy", style="bold")
    table.add_column("Mean Points", justify="right")
    table.add_column("Std Dev", justify="right")
    table.add_column("Win Rate vs Others", justify="right")

    table.add_row(
        "VBD",
        f"{results.mean_vbd_points:.1f}",
        f"{vbd_std:.1f}",
        f"vs ADP: {vbd_vs_adp:.1%}  vs Random: {vbd_vs_rand:.1%}",
    )
    table.add_row(
        "ADP",
        f"{results.mean_adp_points:.1f}",
        f"{adp_std:.1f}",
        f"vs VBD: {adp_vs_vbd:.1%}  vs Random: {adp_vs_rand:.1%}",
    )
    table.add_row(
        "Random",
        f"{results.mean_random_points:.1f}",
        f"{rand_std:.1f}",
        f"vs VBD: {rand_vs_vbd:.1%}  vs ADP: {rand_vs_adp:.1%}",
    )

    console = Console(record=True, width=120)
    console.print(table)
    return console.export_text()


def format_position_breakdown(results: SeasonBacktestResults) -> str:
    """Show performance by draft position (1-12).

    Uses results.points_by_position dict.
    """
    table = Table(title=f"Performance by Draft Position - {results.season} Season")
    table.add_column("Draft Position", justify="center", style="bold")
    table.add_column("Mean VBD Points", justify="right")

    for pos in range(1, 13):
        pts = results.points_by_position.get(pos, 0.0)
        table.add_row(str(pos), f"{pts:.1f}")

    console = Console(record=True, width=80)
    console.print(table)
    return console.export_text()


def format_tuning_results(tuner_results: list[Any]) -> str:
    """Show top configs with parameters and performance.

    Each TunerResult has: config (StrategyConfig), mean_points, iterations_run.
    """
    # Sort by mean_points descending
    sorted_results = sorted(tuner_results, key=lambda r: r.mean_points, reverse=True)

    table = Table(title="Strategy Tuning Results")
    table.add_column("Rank", justify="center", style="bold")
    table.add_column("Mean Points", justify="right")
    table.add_column("QB Repl", justify="right")
    table.add_column("RB Repl", justify="right")
    table.add_column("WR Repl", justify="right")
    table.add_column("TE Repl", justify="right")
    table.add_column("Need Boost", justify="right")
    table.add_column("Scarcity", justify="right")
    table.add_column("Rd 1-2 Bias", justify="center")
    table.add_column("Rd 3-5 Bias", justify="center")

    for rank, result in enumerate(sorted_results, start=1):
        cfg = result.config
        repl = cfg.replacement_rank
        table.add_row(
            str(rank),
            f"{result.mean_points:.1f}",
            f"{repl.get(Position.QB, 1.0):.1f}",
            f"{repl.get(Position.RB, 2.2):.1f}",
            f"{repl.get(Position.WR, 2.2):.1f}",
            f"{repl.get(Position.TE, 1.1):.1f}",
            f"{cfg.need_boost:.2f}",
            f"{cfg.scarcity_penalty:.2f}",
            cfg.round_1_2_bias,
            cfg.round_3_5_bias,
        )

    console = Console(record=True, width=120)
    console.print(table)
    return console.export_text()


def format_before_after(
    current: StrategyConfig,
    best: StrategyConfig,
    current_pts: float,
    best_pts: float,
) -> str:
    """Side-by-side comparison of current vs recommended config.

    Shows each parameter and the difference.
    """
    table = Table(title="Configuration Comparison: Current vs Recommended")
    table.add_column("Parameter", style="bold")
    table.add_column("Current", justify="right")
    table.add_column("Recommended", justify="right")
    table.add_column("Difference", justify="right")

    # Mean points row
    diff_pts = best_pts - current_pts
    table.add_row(
        "Mean Points",
        f"{current_pts:.1f}",
        f"{best_pts:.1f}",
        f"{diff_pts:+.1f}",
    )

    # Replacement ranks
    for pos in [Position.QB, Position.RB, Position.WR, Position.TE]:
        cur_val = current.replacement_rank.get(pos, 1.0)
        best_val = best.replacement_rank.get(pos, 1.0)
        diff = best_val - cur_val
        table.add_row(
            f"{pos.value} Replacement Rank",
            f"{cur_val:.1f}",
            f"{best_val:.1f}",
            f"{diff:+.1f}",
        )

    # Scalar parameters
    params = [
        ("Need Boost", current.need_boost, best.need_boost),
        ("Scarcity Penalty", current.scarcity_penalty, best.scarcity_penalty),
        ("QB Target Round", float(current.qb_target_round), float(best.qb_target_round)),
        ("TE Target Round", float(current.te_target_round), float(best.te_target_round)),
    ]
    for name, cur_val, best_val in params:
        diff = best_val - cur_val
        table.add_row(name, f"{cur_val:.2f}", f"{best_val:.2f}", f"{diff:+.2f}")

    # String parameters
    table.add_row(
        "Round 1-2 Bias",
        current.round_1_2_bias,
        best.round_1_2_bias,
        "changed" if current.round_1_2_bias != best.round_1_2_bias else "-",
    )
    table.add_row(
        "Round 3-5 Bias",
        current.round_3_5_bias,
        best.round_3_5_bias,
        "changed" if current.round_3_5_bias != best.round_3_5_bias else "-",
    )

    console = Console(record=True, width=100)
    console.print(table)
    return console.export_text()


def export_results_csv(results: SeasonBacktestResults, filepath: str) -> None:
    """Write iteration results to CSV.

    Columns: draft_position, vbd_team_points, adp_team_points,
             random_team_points, bust_count, hit_count.
    """
    fieldnames = [
        "draft_position",
        "vbd_team_points",
        "adp_team_points",
        "random_team_points",
        "bust_count",
        "hit_count",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for iteration in results.iterations:
            writer.writerow({
                "draft_position": iteration.draft_position,
                "vbd_team_points": iteration.vbd_team_points,
                "adp_team_points": iteration.adp_team_points,
                "random_team_points": iteration.random_team_points,
                "bust_count": iteration.bust_count,
                "hit_count": iteration.hit_count,
            })


def export_tuning_csv(tuner_results: list[Any], filepath: str) -> None:
    """Write tuning results to CSV.

    Includes all config parameters and mean_points.
    """
    fieldnames = [
        "rank",
        "mean_points",
        "iterations_run",
        "qb_replacement_rank",
        "rb_replacement_rank",
        "wr_replacement_rank",
        "te_replacement_rank",
        "need_boost",
        "scarcity_penalty",
        "round_1_2_bias",
        "round_3_5_bias",
        "qb_target_round",
        "te_target_round",
    ]

    sorted_results = sorted(tuner_results, key=lambda r: r.mean_points, reverse=True)

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rank, result in enumerate(sorted_results, start=1):
            cfg = result.config
            repl = cfg.replacement_rank
            writer.writerow({
                "rank": rank,
                "mean_points": result.mean_points,
                "iterations_run": result.iterations_run,
                "qb_replacement_rank": repl.get(Position.QB, 1.0),
                "rb_replacement_rank": repl.get(Position.RB, 2.2),
                "wr_replacement_rank": repl.get(Position.WR, 2.2),
                "te_replacement_rank": repl.get(Position.TE, 1.1),
                "need_boost": cfg.need_boost,
                "scarcity_penalty": cfg.scarcity_penalty,
                "round_1_2_bias": cfg.round_1_2_bias,
                "round_3_5_bias": cfg.round_3_5_bias,
                "qb_target_round": cfg.qb_target_round,
                "te_target_round": cfg.te_target_round,
            })


def print_full_report(
    season_results: list[SeasonBacktestResults],
    console: Console,
) -> None:
    """Render all tables to the provided Rich Console object.

    Shows comparison and position breakdown for each season.
    """
    for results in season_results:
        console.print()
        console.print(Panel(
            Text(f"Season {results.season} Backtest Report", style="bold"),
            style="blue",
        ))

        # Comparison table
        comparison = format_comparison_table(results)
        console.print(comparison)

        # Position breakdown
        breakdown = format_position_breakdown(results)
        console.print(breakdown)

        # Summary stats
        console.print(f"\n  Bust Rate: {results.mean_bust_rate:.1%}")
        console.print(f"  Hit Rate:  {results.mean_hit_rate:.1%}")
        console.print()
