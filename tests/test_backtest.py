"""Tests for the backtest engine."""

import copy
from src.models import Player, Team, League, Position, ProjectedStats, StrategyConfig, RosterSlot, RosterEntry
from src.scoring import score_all_players
from src.rankings import calculate_vbd
from src.backtest import (
    run_single_draft,
    compute_team_actual_points,
    run_backtest,
    BacktestResult,
    SeasonBacktestResults,
)


def _make_test_pool(n_per_pos=20):
    """Create a deterministic player pool for backtest testing."""
    players = []
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"QB{i}", team="T", position=Position.QB, bye_week=7, adp=float(20 + i),
            projected_stats=ProjectedStats(pass_yards=4500 - i * 50, pass_tds=35 - i, interceptions=10),
        ))
    for i in range(1, n_per_pos * 3 + 1):
        players.append(Player(
            name=f"RB{i}", team="T", position=Position.RB, bye_week=7, adp=float(i),
            projected_stats=ProjectedStats(rush_yards=1500 - i * 15, rush_tds=max(1, 12 - i // 5),
                                           receptions=max(5, 40 - i), rec_yards=max(50, 400 - i * 5), rec_tds=2),
        ))
    for i in range(1, n_per_pos * 3 + 1):
        players.append(Player(
            name=f"WR{i}", team="T", position=Position.WR, bye_week=7, adp=float(10 + i),
            projected_stats=ProjectedStats(receptions=max(20, 100 - i), rec_yards=max(200, 1400 - i * 15),
                                           rec_tds=max(1, 10 - i // 7)),
        ))
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"TE{i}", team="T", position=Position.TE, bye_week=7, adp=float(40 + i),
            projected_stats=ProjectedStats(receptions=max(15, 70 - i * 2), rec_yards=max(150, 900 - i * 30), rec_tds=max(1, 7 - i // 4)),
        ))
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"K{i}", team="T", position=Position.K, bye_week=7, adp=float(130 + i),
            projected_stats=ProjectedStats(field_goals=max(15, 30 - i), extra_points=max(20, 40 - i)),
        ))
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"DEF{i}", team="T", position=Position.DEF, bye_week=7, adp=float(140 + i),
            projected_stats=ProjectedStats(sacks=max(20, 40 - i), def_interceptions=max(5, 15 - i),
                                           def_tds=max(0, 3 - i // 10), points_allowed_per_game=18 + i),
        ))
    return players


def test_run_single_draft_returns_result():
    """A single draft simulation returns a BacktestResult with all teams."""
    projection_players = _make_test_pool()
    actual_players = _make_test_pool()
    score_all_players(projection_players)
    score_all_players(actual_players)
    calculate_vbd(projection_players)

    config = StrategyConfig()
    result = run_single_draft(
        projection_players=projection_players,
        actual_players=actual_players,
        vbd_team_position=1,
        config=config,
    )
    assert isinstance(result, BacktestResult)
    assert result.vbd_team_points > 0
    assert len(result.all_team_points) == 12
    assert result.draft_position == 1


def test_compute_team_actual_points():
    """Rescoring a team with actual stats returns a positive total."""
    players = _make_test_pool(n_per_pos=5)
    score_all_players(players)

    team = Team(name="T1", draft_position=1)
    team.roster = [
        RosterEntry(player=players[0], slot=RosterSlot.QB),
        RosterEntry(player=players[5], slot=RosterSlot.RB),
        RosterEntry(player=players[6], slot=RosterSlot.RB),
        RosterEntry(player=players[20], slot=RosterSlot.WR),
        RosterEntry(player=players[21], slot=RosterSlot.WR),
        RosterEntry(player=players[35], slot=RosterSlot.TE),
        RosterEntry(player=players[7], slot=RosterSlot.FLEX),
        RosterEntry(player=players[40], slot=RosterSlot.K),
        RosterEntry(player=players[45], slot=RosterSlot.DEF),
    ]
    actual_lookup = {p.name: p for p in players}
    points = compute_team_actual_points(team, actual_lookup)
    assert points > 0


def test_run_backtest_small_iterations():
    """Run backtest with 3 iterations returns aggregated results."""
    projection_players = _make_test_pool()
    actual_players = _make_test_pool()
    score_all_players(projection_players)
    score_all_players(actual_players)
    calculate_vbd(projection_players)

    results = run_backtest(
        projection_players=projection_players,
        actual_players=actual_players,
        config=StrategyConfig(),
        iterations=3,
    )
    assert isinstance(results, SeasonBacktestResults)
    assert len(results.iterations) == 3
    assert results.mean_vbd_points > 0
    assert results.mean_random_points >= 0
    assert results.mean_adp_points >= 0
