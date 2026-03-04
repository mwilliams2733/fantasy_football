"""Strategy parameter tuner using random search."""

import random
from dataclasses import dataclass
from src.models import Position, StrategyConfig
from src.backtest import run_backtest, SeasonBacktestResults


@dataclass
class TunerResult:
    """Result from tuning a single parameter configuration."""
    config: StrategyConfig
    mean_points: float
    iterations_run: int
    season_results: list[SeasonBacktestResults] | None = None


def generate_random_config() -> StrategyConfig:
    """Generate a random StrategyConfig within defined bounds."""
    return StrategyConfig(
        replacement_rank={
            Position.QB: round(random.uniform(0.8, 1.5), 2),
            Position.RB: round(random.uniform(1.5, 3.0), 2),
            Position.WR: round(random.uniform(1.5, 3.0), 2),
            Position.TE: round(random.uniform(0.8, 1.5), 2),
            Position.K: 1,
            Position.DEF: 1,
        },
        need_boost=round(random.uniform(1.0, 1.5), 2),
        scarcity_penalty=round(random.uniform(0.5, 1.0), 2),
        round_1_2_bias=random.choice(["BPA", "RB_heavy", "WR_heavy"]),
        round_3_5_bias=random.choice(["BPA", "RB_heavy", "WR_heavy"]),
        qb_target_round=random.randint(4, 8),
        te_target_round=random.randint(3, 8),
    )


def run_tuning(
    projection_players_by_season: dict,  # {year: list[Player]}
    actual_players_by_season: dict,      # {year: list[Player]}
    num_configs: int = 200,
    search_iterations: int = 100,
    validation_iterations: int = 1000,
    top_n: int = 5,
    progress_callback=None,  # callback(current, total, phase_name)
) -> list[TunerResult]:
    """Run random search over parameter space.

    Phase 1: Generate num_configs random configs, run search_iterations backtests per season each
    Phase 2: Re-run top_n configs at validation_iterations for final ranking
    Returns list of validated TunerResults sorted by mean_points descending
    """
    # Phase 1: Search
    search_results = []
    for i in range(num_configs):
        config = generate_random_config()
        total_points = 0.0
        seasons_tested = 0
        for year, proj_players in projection_players_by_season.items():
            actual_players = actual_players_by_season[year]
            result = run_backtest(proj_players, actual_players, config, search_iterations, season=year)
            total_points += result.mean_vbd_points
            seasons_tested += 1
        mean_pts = total_points / max(seasons_tested, 1)
        search_results.append(TunerResult(config=config, mean_points=mean_pts, iterations_run=search_iterations))
        if progress_callback:
            progress_callback(i + 1, num_configs, "search")

    # Phase 2: Validate top configs
    search_results.sort(key=lambda r: r.mean_points, reverse=True)
    top_configs = search_results[:top_n]

    validated = []
    for i, tr in enumerate(top_configs):
        total_points = 0.0
        season_results = []
        for year, proj_players in projection_players_by_season.items():
            actual_players = actual_players_by_season[year]
            result = run_backtest(proj_players, actual_players, tr.config, validation_iterations, season=year)
            total_points += result.mean_vbd_points
            season_results.append(result)
        mean_pts = total_points / max(len(projection_players_by_season), 1)
        validated.append(TunerResult(
            config=tr.config, mean_points=mean_pts,
            iterations_run=validation_iterations, season_results=season_results,
        ))
        if progress_callback:
            progress_callback(i + 1, top_n, "validate")

    validated.sort(key=lambda r: r.mean_points, reverse=True)
    return validated
