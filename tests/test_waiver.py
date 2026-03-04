"""Tests for waiver wire recommendations."""

from src.models import (
    Player, Team, League, Position,
    RosterEntry, RosterSlot,
)
from src.waiver import get_waiver_recommendations


def test_waiver_recommends_upgrade():
    starter = Player(name="BadRB", team="A", position=Position.RB, bye_week=7)
    starter.fantasy_points = 80.0
    starter.vbd_score = -10.0
    free_agent = Player(name="GoodRB", team="B", position=Position.RB, bye_week=9)
    free_agent.fantasy_points = 180.0
    free_agent.vbd_score = 40.0
    team = Team(name="T1", draft_position=1)
    team.roster.append(RosterEntry(player=starter, slot=RosterSlot.RB))
    league = League(name="Test", teams=[team], available_players=[free_agent])
    recs = get_waiver_recommendations(league, team)
    assert len(recs) > 0
    assert recs[0]["add"].name == "GoodRB"
