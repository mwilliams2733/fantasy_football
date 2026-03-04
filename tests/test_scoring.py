"""Tests for the scoring engine."""

from src.models import Player, Position, ProjectedStats
from src.scoring import calculate_fantasy_points


def test_qb_scoring():
    stats = ProjectedStats(pass_yards=4000, pass_tds=30, interceptions=10, rush_yards=200, rush_tds=2)
    player = Player(name="Test QB", team="TST", position=Position.QB, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    assert pts == 352.0


def test_rb_scoring_half_ppr():
    stats = ProjectedStats(rush_yards=1200, rush_tds=10, receptions=40, rec_yards=300, rec_tds=2)
    player = Player(name="Test RB", team="TST", position=Position.RB, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    assert pts == 242.0


def test_wr_scoring_half_ppr():
    stats = ProjectedStats(receptions=100, rec_yards=1400, rec_tds=10, rush_yards=50, rush_tds=0)
    player = Player(name="Test WR", team="TST", position=Position.WR, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    assert pts == 255.0


def test_kicker_scoring():
    stats = ProjectedStats(field_goals=30, extra_points=35)
    player = Player(name="Test K", team="TST", position=Position.K, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    assert pts == 125.0


def test_defense_scoring():
    stats = ProjectedStats(sacks=40, def_interceptions=15, def_tds=3, points_allowed_per_game=20)
    player = Player(name="Test DEF", team="TST", position=Position.DEF, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    assert isinstance(pts, float)
    assert pts > 0
