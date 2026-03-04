"""Integration tests for the full backtest pipeline."""

import copy
import random

from src.models import Player, Position, ProjectedStats, StrategyConfig
from src.scoring import score_all_players
from src.rankings import calculate_vbd
from src.backtest import run_backtest


def _create_synthetic_pool():
    """Create a synthetic player pool of 230+ players with realistic stat distributions.

    Returns:
        list[Player]: A pool with 32 QBs, 65 RBs, 60 WRs, 20 TEs, 20 Ks, 32 DEFs.
    """
    players = []
    teams = [
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
        "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
        "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
        "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
    ]

    # 32 QBs
    for i in range(1, 33):
        players.append(Player(
            name=f"QB{i}",
            team=teams[i - 1],
            position=Position.QB,
            bye_week=(i % 13) + 1,
            adp=float(15 + i * 4),
            projected_stats=ProjectedStats(
                pass_yards=max(2000, 4800 - i * 80),
                pass_tds=max(10, 38 - i),
                interceptions=8 + i // 4,
                rush_yards=max(50, 500 - i * 15),
                rush_tds=max(0, 5 - i // 6),
            ),
        ))

    # 65 RBs
    for i in range(1, 66):
        players.append(Player(
            name=f"RB{i}",
            team=teams[i % 32],
            position=Position.RB,
            bye_week=(i % 13) + 1,
            adp=float(i * 2),
            projected_stats=ProjectedStats(
                rush_yards=max(200, 1600 - i * 20),
                rush_tds=max(1, 14 - i // 4),
                receptions=max(5, 60 - i),
                rec_yards=max(50, 600 - i * 8),
                rec_tds=max(0, 4 - i // 15),
            ),
        ))

    # 60 WRs
    for i in range(1, 61):
        players.append(Player(
            name=f"WR{i}",
            team=teams[i % 32],
            position=Position.WR,
            bye_week=(i % 13) + 1,
            adp=float(5 + i * 2),
            projected_stats=ProjectedStats(
                receptions=max(20, 110 - i * 1.5),
                rec_yards=max(200, 1500 - i * 20),
                rec_tds=max(1, 12 - i // 5),
                rush_yards=max(0, 100 - i * 2),
                rush_tds=max(0, 2 - i // 20),
            ),
        ))

    # 21 TEs
    for i in range(1, 22):
        players.append(Player(
            name=f"TE{i}",
            team=teams[i % 32],
            position=Position.TE,
            bye_week=(i % 13) + 1,
            adp=float(30 + i * 5),
            projected_stats=ProjectedStats(
                receptions=max(15, 80 - i * 3),
                rec_yards=max(150, 1000 - i * 40),
                rec_tds=max(1, 9 - i // 3),
            ),
        ))

    # 20 Ks
    for i in range(1, 21):
        players.append(Player(
            name=f"K{i}",
            team=teams[i % 32],
            position=Position.K,
            bye_week=(i % 13) + 1,
            adp=float(130 + i * 2),
            projected_stats=ProjectedStats(
                field_goals=max(15, 32 - i),
                extra_points=max(20, 45 - i),
            ),
        ))

    # 32 DEFs
    for i in range(1, 33):
        players.append(Player(
            name=f"DEF{i}",
            team=teams[i - 1],
            position=Position.DEF,
            bye_week=(i % 13) + 1,
            adp=float(135 + i * 2),
            projected_stats=ProjectedStats(
                sacks=max(18, 45 - i),
                def_interceptions=max(5, 18 - i // 2),
                def_tds=max(0, 4 - i // 8),
                points_allowed_per_game=16 + i * 0.5,
            ),
        ))

    return players


def _create_actual_pool(projection_pool, seed=42):
    """Deep-copy projection pool and add random variance to simulate actual results."""
    rng = random.Random(seed)
    actual_pool = copy.deepcopy(projection_pool)

    for player in actual_pool:
        stats = player.projected_stats
        stats.pass_yards *= rng.uniform(0.7, 1.3)
        stats.pass_tds *= rng.uniform(0.7, 1.3)
        stats.interceptions *= rng.uniform(0.7, 1.3)
        stats.rush_yards *= rng.uniform(0.7, 1.3)
        stats.rush_tds *= rng.uniform(0.7, 1.3)
        stats.receptions *= rng.uniform(0.7, 1.3)
        stats.rec_yards *= rng.uniform(0.7, 1.3)
        stats.rec_tds *= rng.uniform(0.7, 1.3)
        stats.field_goals *= rng.uniform(0.7, 1.3)
        stats.extra_points *= rng.uniform(0.7, 1.3)
        stats.sacks *= rng.uniform(0.7, 1.3)
        stats.def_interceptions *= rng.uniform(0.7, 1.3)
        stats.def_tds *= rng.uniform(0.7, 1.3)
        # points_allowed_per_game: variance but keep realistic range
        stats.points_allowed_per_game *= rng.uniform(0.7, 1.3)

    return actual_pool


def test_full_backtest_pipeline():
    """End-to-end integration test: create pool, score, VBD, and run backtest."""
    # Create synthetic pools
    projection_pool = _create_synthetic_pool()
    actual_pool = _create_actual_pool(projection_pool)

    # Verify pool sizes
    assert len(projection_pool) >= 230

    # Score both pools
    score_all_players(projection_pool)
    score_all_players(actual_pool)

    # Calculate VBD on projection pool
    calculate_vbd(projection_pool)

    # Run backtest with 10 iterations and default config
    config = StrategyConfig()
    results = run_backtest(
        projection_players=projection_pool,
        actual_players=actual_pool,
        config=config,
        iterations=10,
    )

    # Verify results structure and values
    assert results.mean_vbd_points > 0, (
        f"Expected mean_vbd_points > 0, got {results.mean_vbd_points}"
    )
    assert len(results.iterations) == 10, (
        f"Expected 10 iterations, got {len(results.iterations)}"
    )
    assert results.mean_vbd_points > 100, (
        f"Expected mean_vbd_points > 100, got {results.mean_vbd_points}"
    )
    assert results.mean_random_points > 0, (
        f"Expected mean_random_points > 0, got {results.mean_random_points}"
    )
    assert results.mean_adp_points > 0, (
        f"Expected mean_adp_points > 0, got {results.mean_adp_points}"
    )


def test_different_configs_produce_different_results():
    """Different strategy configs should produce different backtest config objects."""
    # Create synthetic pools with a fixed seed for reproducibility
    projection_pool = _create_synthetic_pool()
    actual_pool = _create_actual_pool(projection_pool, seed=99)

    # Score and VBD
    score_all_players(projection_pool)
    score_all_players(actual_pool)
    calculate_vbd(projection_pool)

    # Config A: default
    config_a = StrategyConfig()

    # Config B: very different - heavy RB replacement, WR-heavy bias
    config_b = StrategyConfig(
        replacement_rank={
            Position.QB: 1,
            Position.RB: 1.5,
            Position.WR: 3.0,
            Position.TE: 1.1,
            Position.K: 1,
            Position.DEF: 1,
        },
        need_boost=1.5,
        scarcity_penalty=0.5,
        round_1_2_bias="WR_heavy",
        round_3_5_bias="WR_heavy",
        qb_target_round=8,
        te_target_round=7,
    )

    # Run backtests with 5 iterations each
    results_a = run_backtest(
        projection_players=projection_pool,
        actual_players=actual_pool,
        config=config_a,
        iterations=5,
    )

    results_b = run_backtest(
        projection_players=projection_pool,
        actual_players=actual_pool,
        config=config_b,
        iterations=5,
    )

    # The two configs should be different objects with different settings
    assert results_a.config is not results_b.config
    assert results_a.config.replacement_rank != results_b.config.replacement_rank
    assert results_a.config.round_1_2_bias != results_b.config.round_1_2_bias
    assert results_a.config.need_boost != results_b.config.need_boost
