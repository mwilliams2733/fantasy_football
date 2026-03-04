"""Tests for VBD rankings engine."""

from src.models import Player, Position, ProjectedStats
from src.scoring import calculate_fantasy_points
from src.rankings import calculate_vbd, get_replacement_level


def _make_player(name: str, pos: Position, pts: float) -> Player:
    p = Player(name=name, team="TST", position=pos, bye_week=7)
    p.fantasy_points = pts
    return p


def test_replacement_level():
    players = [_make_player(f"QB{i}", Position.QB, 300 - i * 10) for i in range(1, 20)]
    replacement = get_replacement_level(players, Position.QB, num_teams=12)
    assert replacement == 170.0


def test_vbd_scores():
    qbs = [_make_player(f"QB{i}", Position.QB, 400 - i * 10) for i in range(1, 20)]
    rbs = [_make_player(f"RB{i}", Position.RB, 300 - i * 5) for i in range(1, 40)]
    all_players = qbs + rbs
    ranked = calculate_vbd(all_players, num_teams=12)
    qb1 = next(p for p in ranked if p.name == "QB1")
    assert qb1.vbd_score == 120.0


def test_vbd_ranking_order():
    qbs = [_make_player(f"QB{i}", Position.QB, 400 - i * 10) for i in range(1, 20)]
    rbs = [_make_player(f"RB{i}", Position.RB, 300 - i * 5) for i in range(1, 40)]
    ranked = calculate_vbd(qbs + rbs, num_teams=12)
    for i in range(len(ranked) - 1):
        assert ranked[i].vbd_score >= ranked[i + 1].vbd_score
