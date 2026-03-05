"""Tests for matchup-based lineup optimizer."""

from src.models import Player, Team, Position, ProjectedStats, RosterEntry, RosterSlot
from src.scoring import calculate_fantasy_points


def _make_player(name, pos, pts, team="NYG"):
    """Helper to create a scored player."""
    p = Player(name=name, team=team, position=Position(pos), bye_week=7)
    p.fantasy_points = pts
    return p


def test_matchup_multiplier():
    from src.matchup_optimizer import get_matchup_multiplier
    # Rank 1 (best defense) should reduce points
    assert get_matchup_multiplier(1) < 1.0
    # Rank 16 (average) should be ~neutral
    assert abs(get_matchup_multiplier(16) - 1.0) < 0.02
    # Rank 32 (worst defense) should boost points
    assert get_matchup_multiplier(32) > 1.0


def test_matchup_adjusted_points():
    from src.matchup_optimizer import get_matchup_adjusted_points
    player = _make_player("TestQB", "QB", 300.0, team="KCC")
    defense_rankings = {"BAL": {"vs_QB": 1, "vs_RB": 16, "vs_WR": 32, "vs_TE": 10}}
    # QB vs rank-1 defense should reduce points
    adj = get_matchup_adjusted_points(player, "BAL", defense_rankings)
    assert adj < 300.0


def test_generate_lineup_permutations():
    from src.matchup_optimizer import generate_lineup_permutations
    # Build a roster: 1 QB, 3 RBs, 2 WRs, 1 TE, 1 K, 1 DEF
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 300), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 200), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 180), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB3", "RB", 120), slot=RosterSlot.BENCH),
        RosterEntry(player=_make_player("WR1", "WR", 250), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 220), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR3", "WR", 100), slot=RosterSlot.BENCH),
        RosterEntry(player=_make_player("TE1", "TE", 150), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("K1", "K", 100), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 80), slot=RosterSlot.DEF),
    ]
    team = Team(name="Test", draft_position=1, roster=roster)
    perms = generate_lineup_permutations(team)
    # Should have at least 2 permutations (RB3 in FLEX vs not)
    assert len(perms) >= 2
    # Each permutation should have exactly 9 starters
    for lineup in perms:
        starters = [e for e in lineup if e.slot != RosterSlot.BENCH]
        assert len(starters) == 9


def test_validate_roster_rules():
    from src.matchup_optimizer import validate_roster_rules
    # Valid roster: 1 QB, 2 RB, 2 WR, 1 TE, 1 K, 1 DEF = 8 players
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 300), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 200), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 180), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("WR1", "WR", 250), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 220), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("TE1", "TE", 150), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("K1", "K", 100), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 80), slot=RosterSlot.DEF),
    ]
    team = Team(name="Test", draft_position=1, roster=roster)
    violations = validate_roster_rules(team)
    assert len(violations) == 0

    # Add 3rd QB — should violate
    roster.append(RosterEntry(player=_make_player("QB2", "QB", 200), slot=RosterSlot.BENCH))
    roster.append(RosterEntry(player=_make_player("QB3", "QB", 150), slot=RosterSlot.BENCH))
    team2 = Team(name="Bad", draft_position=1, roster=roster)
    violations = validate_roster_rules(team2)
    assert len(violations) == 1
    assert "QB" in violations[0]


def test_monte_carlo_returns_valid_stats():
    from src.matchup_optimizer import monte_carlo_lineup
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 20.0, "KCC"), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 15.0, "KCC"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 12.0, "BAL"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("WR1", "WR", 18.0, "BAL"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 14.0, "PHI"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("TE1", "TE", 10.0, "PHI"), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("FLEX1", "RB", 8.0, "KCC"), slot=RosterSlot.FLEX),
        RosterEntry(player=_make_player("K1", "K", 7.0, "DAL"), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 6.0, "DAL"), slot=RosterSlot.DEF),
    ]
    opponent_map = {"KCC": "BAL", "BAL": "KCC", "PHI": "DAL", "DAL": "PHI"}
    defense_rankings = {
        "BAL": {"vs_QB": 3, "vs_RB": 5, "vs_WR": 10, "vs_TE": 15},
        "KCC": {"vs_QB": 20, "vs_RB": 18, "vs_WR": 22, "vs_TE": 25},
        "DAL": {"vs_QB": 16, "vs_RB": 16, "vs_WR": 16, "vs_TE": 16},
        "PHI": {"vs_QB": 10, "vs_RB": 8, "vs_WR": 12, "vs_TE": 14},
    }
    mc = monte_carlo_lineup(roster, opponent_map, defense_rankings, simulations=200)
    assert mc.floor <= mc.mean <= mc.ceiling
    assert 0.0 <= mc.consistency <= 100.0


def test_optimize_with_matchups_returns_recommendation():
    from src.matchup_optimizer import optimize_with_matchups
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 20.0, "KCC"), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 15.0, "KCC"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 12.0, "BAL"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB3", "RB", 8.0, "BAL"), slot=RosterSlot.BENCH),
        RosterEntry(player=_make_player("WR1", "WR", 18.0, "PHI"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 14.0, "PHI"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("TE1", "TE", 10.0, "DAL"), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("K1", "K", 7.0, "DAL"), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 6.0, "DAL"), slot=RosterSlot.DEF),
    ]
    team = Team(name="Test", draft_position=1, roster=roster)
    schedule = {
        "KCC": ["BAL", "DEN"], "BAL": ["KCC", "CIN"],
        "PHI": ["DAL", "NYG"], "DAL": ["PHI", "WAS"],
    }
    defense_rankings = {
        "BAL": {"vs_QB": 3, "vs_RB": 5, "vs_WR": 10, "vs_TE": 15},
        "KCC": {"vs_QB": 20, "vs_RB": 18, "vs_WR": 22, "vs_TE": 25},
        "DAL": {"vs_QB": 16, "vs_RB": 16, "vs_WR": 16, "vs_TE": 16},
        "PHI": {"vs_QB": 10, "vs_RB": 8, "vs_WR": 12, "vs_TE": 14},
    }
    result = optimize_with_matchups(team, week=1, schedule=schedule, defense_rankings=defense_rankings)
    assert result["recommended"] is not None
    assert result["week"] == 1
    assert "monte_carlo" in result["recommended"]
    assert result["recommended"]["monte_carlo"]["floor"] <= result["recommended"]["monte_carlo"]["ceiling"]
