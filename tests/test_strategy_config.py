"""Tests for configurable VBD strategy parameters."""

from src.models import Player, Position, ProjectedStats, Team, RosterSlot, StrategyConfig
from src.scoring import score_all_players
from src.rankings import calculate_vbd, get_draft_recommendations


def _make_players():
    """Create a small test pool with known scores."""
    players = [
        Player(name="QB1", team="T", position=Position.QB, bye_week=7,
               projected_stats=ProjectedStats(pass_yards=4500, pass_tds=35, interceptions=10)),
        Player(name="QB2", team="T", position=Position.QB, bye_week=7,
               projected_stats=ProjectedStats(pass_yards=3500, pass_tds=22, interceptions=10)),
        Player(name="RB1", team="T", position=Position.RB, bye_week=7,
               projected_stats=ProjectedStats(rush_yards=1400, rush_tds=12, receptions=50, rec_yards=400, rec_tds=2)),
        Player(name="RB2", team="T", position=Position.RB, bye_week=7,
               projected_stats=ProjectedStats(rush_yards=900, rush_tds=6, receptions=30, rec_yards=200, rec_tds=1)),
        Player(name="RB3", team="T", position=Position.RB, bye_week=7,
               projected_stats=ProjectedStats(rush_yards=600, rush_tds=3, receptions=20, rec_yards=100, rec_tds=0)),
        Player(name="WR1", team="T", position=Position.WR, bye_week=7,
               projected_stats=ProjectedStats(receptions=100, rec_yards=1400, rec_tds=10)),
        Player(name="WR2", team="T", position=Position.WR, bye_week=7,
               projected_stats=ProjectedStats(receptions=60, rec_yards=800, rec_tds=5)),
        Player(name="WR3", team="T", position=Position.WR, bye_week=7,
               projected_stats=ProjectedStats(receptions=40, rec_yards=500, rec_tds=2)),
        Player(name="TE1", team="T", position=Position.TE, bye_week=7,
               projected_stats=ProjectedStats(receptions=70, rec_yards=900, rec_tds=7)),
    ]
    score_all_players(players)
    return players


def test_strategy_config_defaults_match_original():
    """Default StrategyConfig should produce same results as hardcoded values."""
    config = StrategyConfig()
    assert config.replacement_rank[Position.QB] == 1
    assert config.replacement_rank[Position.RB] == 2.2
    assert config.need_boost == 1.15
    assert config.scarcity_penalty == 0.8


def test_custom_replacement_ranks_change_vbd():
    """Changing replacement ranks should change VBD scores."""
    players = _make_players()
    # Use num_teams=1 so replacement indices stay within our small player pool.
    # With 3 RBs: rank 1.0 -> index int(1*1.0)=1 (RB2), rank 2.0 -> index int(1*2.0)=2 (RB3)
    default_config = StrategyConfig(
        replacement_rank={
            Position.QB: 1, Position.RB: 1.0, Position.WR: 1.0,
            Position.TE: 1, Position.K: 1, Position.DEF: 1,
        }
    )
    custom_config = StrategyConfig(
        replacement_rank={
            Position.QB: 1, Position.RB: 2.0, Position.WR: 2.0,
            Position.TE: 1, Position.K: 1, Position.DEF: 1,
        }
    )
    calculate_vbd(players, num_teams=1, config=default_config)
    rb1_default_vbd = next(p for p in players if p.name == "RB1").vbd_score

    calculate_vbd(players, num_teams=1, config=custom_config)
    rb1_custom_vbd = next(p for p in players if p.name == "RB1").vbd_score

    assert rb1_custom_vbd != rb1_default_vbd


def test_custom_need_boost_in_recommendations():
    """Custom need_boost should affect recommendation ordering."""
    players = _make_players()
    config_high_need = StrategyConfig(need_boost=2.0, scarcity_penalty=0.1)
    config_no_need = StrategyConfig(need_boost=1.0, scarcity_penalty=1.0)
    calculate_vbd(players)

    team_needs = [RosterSlot.QB]

    recs_high = get_draft_recommendations(players, team_needs, config=config_high_need)
    recs_none = get_draft_recommendations(players, team_needs, config=config_no_need)

    high_qb_rank = next((i for i, p in enumerate(recs_high) if p.position == Position.QB), 99)
    none_qb_rank = next((i for i, p in enumerate(recs_none) if p.position == Position.QB), 99)
    assert high_qb_rank <= none_qb_rank


def test_round_targeting_in_config():
    """Round-based targeting parameters exist and have defaults."""
    config = StrategyConfig()
    assert config.round_1_2_bias == "BPA"
    assert config.round_3_5_bias == "BPA"
    assert config.qb_target_round == 6
    assert config.te_target_round == 5
