"""Scoring engine for half PPR, 6pt TD fantasy football."""

from src.models import Player, Position


# Scoring constants
PASS_YARD_POINTS = 1.0 / 25.0
PASS_TD_POINTS = 6.0
INT_POINTS = -2.0
RUSH_YARD_POINTS = 1.0 / 10.0
RUSH_TD_POINTS = 6.0
REC_YARD_POINTS = 1.0 / 10.0
REC_TD_POINTS = 6.0
RECEPTION_POINTS = 0.5
FG_POINTS = 3.0
XP_POINTS = 1.0
SACK_POINTS = 1.0
DEF_INT_POINTS = 2.0
DEF_TD_POINTS = 6.0


def _defense_points_allowed_bonus(points_allowed_per_game: float) -> float:
    ppg = points_allowed_per_game
    if ppg < 10:
        return 80.0
    elif ppg < 15:
        return 50.0
    elif ppg < 20:
        return 25.0
    elif ppg < 25:
        return 5.0
    elif ppg < 30:
        return -10.0
    else:
        return -25.0


def calculate_fantasy_points(player: Player) -> float:
    s = player.projected_stats
    points = 0.0
    points += s.pass_yards * PASS_YARD_POINTS
    points += s.pass_tds * PASS_TD_POINTS
    points += s.interceptions * INT_POINTS
    points += s.rush_yards * RUSH_YARD_POINTS
    points += s.rush_tds * RUSH_TD_POINTS
    points += s.receptions * RECEPTION_POINTS
    points += s.rec_yards * REC_YARD_POINTS
    points += s.rec_tds * REC_TD_POINTS
    points += s.field_goals * FG_POINTS
    points += s.extra_points * XP_POINTS
    points += s.sacks * SACK_POINTS
    points += s.def_interceptions * DEF_INT_POINTS
    points += s.def_tds * DEF_TD_POINTS
    if player.position == Position.DEF:
        points += _defense_points_allowed_bonus(s.points_allowed_per_game)
    player.fantasy_points = points
    return points


def score_all_players(players: list[Player]) -> list[Player]:
    for player in players:
        calculate_fantasy_points(player)
    return sorted(players, key=lambda p: p.fantasy_points, reverse=True)
