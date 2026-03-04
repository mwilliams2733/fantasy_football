"""Integration test: full mock draft flow."""

from src.models import Player, Team, League, Position, ProjectedStats, TOTAL_ROUNDS
from src.scoring import score_all_players
from src.rankings import calculate_vbd
from src.draft import DraftEngine


def test_full_mock_draft():
    """Run a complete 15-round mock draft with 12 teams."""
    players = []
    for i in range(1, 40):
        players.append(Player(
            name=f"QB{i}", team="TST", position=Position.QB, bye_week=7,
            projected_stats=ProjectedStats(pass_yards=4500-i*50, pass_tds=35-i, interceptions=10),
        ))
    for i in range(1, 70):
        players.append(Player(
            name=f"RB{i}", team="TST", position=Position.RB, bye_week=7,
            projected_stats=ProjectedStats(rush_yards=1500-i*15, rush_tds=max(1, 12-i//5), receptions=max(5, 40-i//2), rec_yards=max(50, 400-i*5), rec_tds=2),
        ))
    for i in range(1, 70):
        players.append(Player(
            name=f"WR{i}", team="TST", position=Position.WR, bye_week=7,
            projected_stats=ProjectedStats(receptions=max(20, 100-i), rec_yards=max(200, 1400-i*15), rec_tds=max(1, 10-i//7), rush_yards=20, rush_tds=0),
        ))
    for i in range(1, 25):
        players.append(Player(
            name=f"TE{i}", team="TST", position=Position.TE, bye_week=7,
            projected_stats=ProjectedStats(receptions=max(15, 70-i*2), rec_yards=max(150, 900-i*30), rec_tds=max(1, 7-i//4)),
        ))
    for i in range(1, 20):
        players.append(Player(
            name=f"K{i}", team="TST", position=Position.K, bye_week=7,
            projected_stats=ProjectedStats(field_goals=max(15, 30-i//2), extra_points=max(20, 40-i)),
        ))
    for i in range(1, 33):
        players.append(Player(
            name=f"DEF{i}", team="TST", position=Position.DEF, bye_week=7,
            projected_stats=ProjectedStats(sacks=max(20, 40-i), def_interceptions=max(5, 15-i//3), def_tds=max(0, 3-i//10), points_allowed_per_game=18+i//3),
        ))

    score_all_players(players)
    calculate_vbd(players)

    teams = [Team(name=f"Team {i}", draft_position=i) for i in range(1, 13)]
    league = League(name="Test League", teams=teams, available_players=players.copy())
    engine = DraftEngine(league)

    while not engine.is_draft_complete:
        team = engine.current_drafter()
        engine.ai_pick(team)

    for team in teams:
        assert len(team.roster) == TOTAL_ROUNDS, f"{team.name} has {len(team.roster)} players"

    all_drafted = []
    for team in teams:
        all_drafted.extend([e.player.name for e in team.roster])
    assert len(all_drafted) == len(set(all_drafted)), "Duplicate draft picks detected"


def test_full_flow_with_real_data():
    """Test loading real player data, scoring, ranking, and drafting."""
    from src.persistence import load_players

    players = load_players()
    assert len(players) > 180  # need enough for 180 picks

    score_all_players(players)
    calculate_vbd(players)

    # Verify top players have reasonable scores
    top_player = max(players, key=lambda p: p.fantasy_points)
    assert top_player.fantasy_points > 200  # should be a top RB or WR

    # Run a mock draft with real data
    teams = [Team(name=f"Team {i}", draft_position=i) for i in range(1, 13)]
    league = League(name="Real Test", teams=teams, available_players=players.copy())
    engine = DraftEngine(league)

    while not engine.is_draft_complete:
        team = engine.current_drafter()
        engine.ai_pick(team)

    for team in teams:
        assert len(team.roster) == TOTAL_ROUNDS

    # Verify all picks unique
    all_names = set()
    for team in teams:
        for e in team.roster:
            assert e.player.name not in all_names, f"Duplicate: {e.player.name}"
            all_names.add(e.player.name)
