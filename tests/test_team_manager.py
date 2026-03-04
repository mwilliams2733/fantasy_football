"""Tests for team management."""

from src.models import (
    Player, Team, League, Position,
    RosterEntry, RosterSlot,
)
from src.team_manager import add_player, drop_player, trade_players


def _make_league_with_player():
    p1 = Player(name="RB1", team="TST", position=Position.RB, bye_week=7)
    p1.fantasy_points = 200.0
    p1.vbd_score = 50.0
    p2 = Player(name="FA1", team="TST", position=Position.RB, bye_week=7)
    p2.fantasy_points = 150.0
    p2.vbd_score = 30.0
    team = Team(name="Team 1", draft_position=1)
    team.roster.append(RosterEntry(player=p1, slot=RosterSlot.RB))
    league = League(name="Test", teams=[team], available_players=[p2])
    return league, team, p1, p2


def test_add_player():
    league, team, p1, p2 = _make_league_with_player()
    add_player(league, team, p2)
    assert p2 in [e.player for e in team.roster]
    assert p2 not in league.available_players


def test_drop_player():
    league, team, p1, p2 = _make_league_with_player()
    drop_player(league, team, p1)
    assert p1 not in [e.player for e in team.roster]


def test_trade_players():
    p1 = Player(name="P1", team="A", position=Position.WR, bye_week=7)
    p1.fantasy_points = 200.0
    p2 = Player(name="P2", team="B", position=Position.WR, bye_week=7)
    p2.fantasy_points = 180.0
    t1 = Team(name="T1", draft_position=1)
    t1.roster.append(RosterEntry(player=p1, slot=RosterSlot.WR))
    t2 = Team(name="T2", draft_position=2)
    t2.roster.append(RosterEntry(player=p2, slot=RosterSlot.WR))
    league = League(name="Test", teams=[t1, t2])
    trade_players(league, t1, [p1], t2, [p2])
    assert p2 in [e.player for e in t1.roster]
    assert p1 in [e.player for e in t2.roster]
