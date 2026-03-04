"""Tests for the draft engine."""

from src.models import Player, Team, League, Position, RosterEntry, RosterSlot, TOTAL_ROUNDS
from src.draft import generate_snake_order, DraftEngine


def test_snake_order_round1():
    order = generate_snake_order(12, 15)
    assert order[0] == list(range(1, 13))


def test_snake_order_round2():
    order = generate_snake_order(12, 15)
    assert order[1] == list(range(12, 0, -1))


def test_snake_order_total_picks():
    order = generate_snake_order(12, 15)
    total = sum(len(r) for r in order)
    assert total == 180


def test_draft_engine_pick_removes_player():
    players = [
        Player(name=f"P{i}", team="TST", position=Position.RB, bye_week=7)
        for i in range(50)
    ]
    for p in players:
        p.fantasy_points = 100.0
        p.vbd_score = 50.0
    teams = [Team(name=f"Team {i}", draft_position=i) for i in range(1, 13)]
    league = League(name="Test", teams=teams, available_players=players.copy())
    engine = DraftEngine(league)
    engine.make_pick(teams[0], players[0])
    assert players[0] not in league.available_players
