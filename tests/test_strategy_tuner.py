"""Tests for the strategy parameter tuner."""

from src.models import StrategyConfig, Position
from src.strategy_tuner import (
    generate_random_config,
    TunerResult,
    run_tuning,
)


def test_generate_random_config_within_bounds():
    """Generated configs should have values within defined ranges."""
    for _ in range(20):
        config = generate_random_config()
        assert 0.8 <= config.replacement_rank[Position.QB] <= 1.5
        assert 1.5 <= config.replacement_rank[Position.RB] <= 3.0
        assert 1.5 <= config.replacement_rank[Position.WR] <= 3.0
        assert 0.8 <= config.replacement_rank[Position.TE] <= 1.5
        assert 1.0 <= config.need_boost <= 1.5
        assert 0.5 <= config.scarcity_penalty <= 1.0
        assert config.round_1_2_bias in ("BPA", "RB_heavy", "WR_heavy")
        assert config.round_3_5_bias in ("BPA", "RB_heavy", "WR_heavy")
        assert 4 <= config.qb_target_round <= 8
        assert 3 <= config.te_target_round <= 8


def test_tuner_result_ranking():
    """TunerResult instances sort by mean_points descending."""
    results = [
        TunerResult(config=StrategyConfig(), mean_points=100.0, iterations_run=10),
        TunerResult(config=StrategyConfig(), mean_points=150.0, iterations_run=10),
        TunerResult(config=StrategyConfig(), mean_points=120.0, iterations_run=10),
    ]
    ranked = sorted(results, key=lambda r: r.mean_points, reverse=True)
    assert ranked[0].mean_points == 150.0
    assert ranked[1].mean_points == 120.0
    assert ranked[2].mean_points == 100.0
