"""Tests for the draft engine."""

from src.models import Player, Team, League, Position, ProjectedStats, RosterEntry, RosterSlot, TOTAL_ROUNDS
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


def test_draft_respects_roster_limits():
    """AI should not draft a 3rd QB, 2nd K, or 2nd DEF."""
    from src.scoring import score_all_players
    from src.rankings import calculate_vbd

    # Create player pool large enough for 12-team, 15-round draft (180 picks)
    # Include many QBs, Ks, and DEFs to tempt the engine into over-drafting
    # Need plenty of RB/WR/TE since those have no roster cap and fill remaining slots
    players = []
    for i in range(20):
        players.append(Player(name=f"QB{i}", team="TST", position=Position.QB, bye_week=7,
                              projected_stats=ProjectedStats(pass_yards=4000 - i * 100, pass_tds=30 - i)))
    for i in range(60):
        players.append(Player(name=f"RB{i}", team="TST", position=Position.RB, bye_week=7,
                              projected_stats=ProjectedStats(rush_yards=max(100, 1000 - i * 15), rush_tds=max(1, 8 - i))))
    for i in range(60):
        players.append(Player(name=f"WR{i}", team="TST", position=Position.WR, bye_week=7,
                              projected_stats=ProjectedStats(rec_yards=max(100, 1000 - i * 15), rec_tds=max(1, 8 - i), receptions=max(10, 80 - i * 2))))
    for i in range(40):
        players.append(Player(name=f"TE{i}", team="TST", position=Position.TE, bye_week=7,
                              projected_stats=ProjectedStats(rec_yards=max(100, 600 - i * 12), rec_tds=max(1, 5 - i), receptions=max(10, 50 - i * 2))))
    for i in range(5):
        players.append(Player(name=f"K{i}", team="TST", position=Position.K, bye_week=7,
                              projected_stats=ProjectedStats(field_goals=max(10, 30 - i * 3), extra_points=max(10, 35 - i * 3))))
    for i in range(5):
        players.append(Player(name=f"DEF{i}", team=f"D{i}", position=Position.DEF, bye_week=7,
                              projected_stats=ProjectedStats(sacks=max(10, 40 - i * 5), def_interceptions=max(5, 15 - i * 2), def_tds=max(1, 3))))

    score_all_players(players)
    calculate_vbd(players)

    teams = [Team(name=f"Team{i}", draft_position=i) for i in range(1, 13)]
    league = League(name="Test", teams=teams, available_players=players.copy())
    engine = DraftEngine(league)

    while not engine.is_draft_complete:
        current = engine.current_drafter()
        engine.ai_pick(current)

    # Check every team respects limits
    for t in teams:
        qb_count = t.position_count(Position.QB)
        k_count = t.position_count(Position.K)
        def_count = t.position_count(Position.DEF)
        assert qb_count <= 2, f"{t.name} has {qb_count} QBs"
        assert k_count <= 1, f"{t.name} has {k_count} Ks"
        assert def_count <= 1, f"{t.name} has {def_count} DEFs"
