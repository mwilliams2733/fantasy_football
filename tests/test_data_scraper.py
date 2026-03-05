"""Tests for historical data scraping (uses mock HTML responses)."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.data_scraper import (
    parse_pfr_passing,
    parse_pfr_rushing,
    parse_pfr_receiving,
    parse_pfr_kicking,
    parse_pfr_defense,
    build_player_dataset,
    scrape_season,
    scrape_preseason_adp,
    parse_schedule,
    scrape_schedule,
    HISTORICAL_DIR,
)
from src.models import Position


SAMPLE_PASSING_HTML = """
<table id="passing">
<thead><tr><th>Player</th><th>Tm</th><th>Yds</th><th>TD</th><th>Int</th></tr></thead>
<tbody>
<tr><td data-stat="player"><a>Patrick Mahomes</a></td><td data-stat="team_name_abbr">KAN</td>
<td data-stat="pass_yds">4839</td><td data-stat="pass_td">26</td><td data-stat="pass_int">11</td></tr>
</tbody>
</table>
"""

SAMPLE_RUSHING_HTML = """
<table id="rushing">
<thead><tr><th>Player</th><th>Tm</th><th>Yds</th><th>TD</th></tr></thead>
<tbody>
<tr><td data-stat="player"><a>Saquon Barkley</a></td><td data-stat="team_name_abbr">PHI</td>
<td data-stat="rush_yds">2005</td><td data-stat="rush_td">13</td></tr>
</tbody>
</table>
"""

SAMPLE_RECEIVING_HTML = """
<table id="receiving">
<thead><tr><th>Player</th><th>Tm</th><th>Rec</th><th>Yds</th><th>TD</th></tr></thead>
<tbody>
<tr><td data-stat="player"><a>Ja'Marr Chase</a></td><td data-stat="team_name_abbr">CIN</td>
<td data-stat="rec">127</td><td data-stat="rec_yds">1708</td><td data-stat="rec_td">17</td></tr>
</tbody>
</table>
"""

SAMPLE_KICKING_HTML = """
<table id="kicking">
<thead><tr><th>Player</th><th>Tm</th><th>FGM</th><th>XPM</th></tr></thead>
<tbody>
<tr><td data-stat="player"><a>Justin Tucker</a></td><td data-stat="team_name_abbr">BAL</td>
<td data-stat="fgm">30</td><td data-stat="xpm">35</td></tr>
</tbody>
</table>
"""

SAMPLE_DEFENSE_HTML = """
<table id="team_stats">
<thead><tr><th>Tm</th><th>Sk</th><th>Int</th><th>TD</th><th>PF</th></tr></thead>
<tbody>
<tr><td data-stat="team_name"><a>Baltimore Ravens</a></td>
<td data-stat="sacks">48</td><td data-stat="pass_int">18</td>
<td data-stat="def_tds">4</td><td data-stat="points_opp">300</td></tr>
</tbody>
</table>
"""


def test_parse_pfr_passing():
    result = parse_pfr_passing(SAMPLE_PASSING_HTML)
    assert len(result) >= 1
    mahomes = result[0]
    assert mahomes["name"] == "Patrick Mahomes"
    assert mahomes["pass_yards"] == 4839
    assert mahomes["pass_tds"] == 26
    assert mahomes["interceptions"] == 11


def test_parse_pfr_passing_skips_header_rows():
    html = """
    <table id="passing">
    <thead><tr><th>Player</th></tr></thead>
    <tbody>
    <tr class="thead"><td data-stat="player">Player</td><td data-stat="team_name_abbr">Tm</td>
    <td data-stat="pass_yds">Yds</td><td data-stat="pass_td">TD</td><td data-stat="pass_int">Int</td></tr>
    <tr><td data-stat="player"><a>Joe Burrow*</a></td><td data-stat="team_name_abbr">CIN</td>
    <td data-stat="pass_yds">4000</td><td data-stat="pass_td">30</td><td data-stat="pass_int">8</td></tr>
    </tbody>
    </table>
    """
    result = parse_pfr_passing(html)
    assert len(result) == 1
    assert result[0]["name"] == "Joe Burrow"


def test_parse_pfr_passing_handles_missing_stats():
    html = """
    <table id="passing">
    <thead><tr><th>Player</th></tr></thead>
    <tbody>
    <tr><td data-stat="player"><a>Backup QB</a></td><td data-stat="team_name_abbr">NYG</td>
    <td data-stat="pass_yds"></td><td data-stat="pass_td"></td><td data-stat="pass_int"></td></tr>
    </tbody>
    </table>
    """
    result = parse_pfr_passing(html)
    assert len(result) == 1
    assert result[0]["pass_yards"] == 0
    assert result[0]["pass_tds"] == 0


def test_parse_pfr_passing_cleans_player_names():
    """PFR adds *, +, \\ suffixes to player names for Pro Bowl etc."""
    html = """
    <table id="passing">
    <thead><tr><th>Player</th></tr></thead>
    <tbody>
    <tr><td data-stat="player"><a>Lamar Jackson*+</a></td><td data-stat="team_name_abbr">BAL</td>
    <td data-stat="pass_yds">3000</td><td data-stat="pass_td">24</td><td data-stat="pass_int">4</td></tr>
    </tbody>
    </table>
    """
    result = parse_pfr_passing(html)
    assert result[0]["name"] == "Lamar Jackson"


def test_parse_pfr_rushing():
    result = parse_pfr_rushing(SAMPLE_RUSHING_HTML)
    assert len(result) >= 1
    saquon = result[0]
    assert saquon["name"] == "Saquon Barkley"
    assert saquon["rush_yards"] == 2005
    assert saquon["rush_tds"] == 13


def test_parse_pfr_receiving():
    result = parse_pfr_receiving(SAMPLE_RECEIVING_HTML)
    assert len(result) >= 1
    chase = result[0]
    assert chase["name"] == "Ja'Marr Chase"
    assert chase["receptions"] == 127
    assert chase["rec_yards"] == 1708
    assert chase["rec_tds"] == 17


def test_parse_pfr_kicking():
    result = parse_pfr_kicking(SAMPLE_KICKING_HTML)
    assert len(result) >= 1
    tucker = result[0]
    assert tucker["name"] == "Justin Tucker"
    assert tucker["field_goals"] == 30
    assert tucker["extra_points"] == 35


def test_parse_pfr_defense():
    result = parse_pfr_defense(SAMPLE_DEFENSE_HTML)
    assert len(result) >= 1
    ravens = result[0]
    assert "Baltimore" in ravens["name"] or "Ravens" in ravens["name"]
    assert ravens["sacks"] == 48
    assert ravens["def_interceptions"] == 18
    assert ravens["def_tds"] == 4
    assert abs(ravens["points_allowed_per_game"] - 300 / 17) < 0.1


def test_build_player_dataset_merges_stats():
    passing = [{"name": "Josh Allen", "team": "BUF", "pass_yards": 3731, "pass_tds": 28, "interceptions": 6}]
    rushing = [{"name": "Josh Allen", "team": "BUF", "rush_yards": 531, "rush_tds": 12}]
    receiving = [{"name": "Josh Allen", "team": "BUF", "receptions": 0, "rec_yards": 0, "rec_tds": 0}]
    kicking = []
    defense = []
    players = build_player_dataset(passing, rushing, receiving, kicking, defense)
    allen = next(p for p in players if p.name == "Josh Allen")
    assert allen.projected_stats.pass_yards == 3731
    assert allen.projected_stats.rush_yards == 531
    assert allen.projected_stats.rush_tds == 12
    assert allen.position == Position.QB


def test_build_player_dataset_assigns_rb_position():
    passing = []
    rushing = [{"name": "Derrick Henry", "team": "BAL", "rush_yards": 1500, "rush_tds": 14}]
    receiving = [{"name": "Derrick Henry", "team": "BAL", "receptions": 20, "rec_yards": 150, "rec_tds": 1}]
    kicking = []
    defense = []
    players = build_player_dataset(passing, rushing, receiving, kicking, defense)
    henry = next(p for p in players if p.name == "Derrick Henry")
    assert henry.position == Position.RB


def test_build_player_dataset_assigns_wr_position():
    passing = []
    rushing = []
    receiving = [{"name": "CeeDee Lamb", "team": "DAL", "receptions": 110, "rec_yards": 1350, "rec_tds": 10}]
    kicking = []
    defense = []
    players = build_player_dataset(passing, rushing, receiving, kicking, defense)
    lamb = next(p for p in players if p.name == "CeeDee Lamb")
    assert lamb.position == Position.WR


def test_build_player_dataset_assigns_k_position():
    passing = []
    rushing = []
    receiving = []
    kicking = [{"name": "Justin Tucker", "team": "BAL", "field_goals": 30, "extra_points": 35}]
    defense = []
    players = build_player_dataset(passing, rushing, receiving, kicking, defense)
    tucker = next(p for p in players if p.name == "Justin Tucker")
    assert tucker.position == Position.K


def test_build_player_dataset_assigns_def_position():
    passing = []
    rushing = []
    receiving = []
    kicking = []
    defense = [{"name": "Baltimore Ravens", "team": "BAL", "sacks": 48,
                "def_interceptions": 18, "def_tds": 4, "points_allowed_per_game": 17.6}]
    players = build_player_dataset(passing, rushing, receiving, kicking, defense)
    ravens = next(p for p in players if "Baltimore" in p.name or "Ravens" in p.name)
    assert ravens.position == Position.DEF


def test_scrape_season_caches_locally(tmp_path):
    with patch("src.data_scraper.HISTORICAL_DIR", tmp_path):
        with patch("src.data_scraper._fetch_page") as mock_fetch:
            mock_fetch.return_value = "<html><body></body></html>"
            with patch("src.data_scraper.build_player_dataset") as mock_build:
                from src.models import Player, ProjectedStats
                mock_build.return_value = [
                    Player(name="Test QB", team="TST", position=Position.QB, bye_week=7)
                ]
                result = scrape_season(2024)
                assert len(result) == 1
                cache_file = tmp_path / "2024_actual_stats.json"
                assert cache_file.exists()
                mock_fetch.reset_mock()
                mock_build.reset_mock()
                result2 = scrape_season(2024)
                assert len(result2) == 1
                mock_fetch.assert_not_called()


def test_scrape_preseason_adp_caches_locally(tmp_path):
    with patch("src.data_scraper.HISTORICAL_DIR", tmp_path):
        result = scrape_preseason_adp(2024)
        assert isinstance(result, dict)
        assert len(result) > 0
        # All values should be floats
        for name, adp in result.items():
            assert isinstance(adp, float)
        # Check cache file exists
        cache_file = tmp_path / "2024_preseason_adp.json"
        assert cache_file.exists()


def test_parse_schedule():
    html = """
    <table id="games">
    <thead><tr><th>Week</th><th>Winner/tie</th><th></th><th>Loser/tie</th></tr></thead>
    <tbody>
    <tr><td data-stat="week_num">1</td>
        <td data-stat="winner"><a href="/teams/kan/2024.htm">Kansas City Chiefs</a></td>
        <td data-stat="game_location"></td>
        <td data-stat="loser"><a href="/teams/rav/2024.htm">Baltimore Ravens</a></td></tr>
    <tr><td data-stat="week_num">1</td>
        <td data-stat="winner"><a href="/teams/phi/2024.htm">Philadelphia Eagles</a></td>
        <td data-stat="game_location">@</td>
        <td data-stat="loser"><a href="/teams/gnb/2024.htm">Green Bay Packers</a></td></tr>
    </tbody>
    </table>
    """
    schedule = parse_schedule(html)
    # KC played at home vs BAL
    assert "KC" in schedule
    assert schedule["KC"][0] == "BAL"
    # BAL played at KC
    assert "BAL" in schedule
    assert schedule["BAL"][0] == "KC"
    # PHI played @ GB (winner was away)
    assert "PHI" in schedule
    assert schedule["PHI"][0] == "GB"
    assert "GB" in schedule
    assert schedule["GB"][0] == "PHI"


def test_parse_schedule_handles_bye_weeks():
    """Teams with no game in a week should have None for that week."""
    html = """
    <table id="games">
    <thead><tr><th>Week</th><th>Winner/tie</th><th></th><th>Loser/tie</th></tr></thead>
    <tbody>
    <tr><td data-stat="week_num">1</td>
        <td data-stat="winner"><a href="/teams/kan/2024.htm">Kansas City Chiefs</a></td>
        <td data-stat="game_location"></td>
        <td data-stat="loser"><a href="/teams/rav/2024.htm">Baltimore Ravens</a></td></tr>
    <tr><td data-stat="week_num">3</td>
        <td data-stat="winner"><a href="/teams/kan/2024.htm">Kansas City Chiefs</a></td>
        <td data-stat="game_location"></td>
        <td data-stat="loser"><a href="/teams/phi/2024.htm">Philadelphia Eagles</a></td></tr>
    </tbody>
    </table>
    """
    schedule = parse_schedule(html)
    # KC has a bye in week 2 (index 1)
    assert schedule["KC"][0] == "BAL"
    assert schedule["KC"][1] is None
    assert schedule["KC"][2] == "PHI"


def test_parse_schedule_skips_non_numeric_weeks():
    """Playoff week labels like 'WildCard' should be skipped."""
    html = """
    <table id="games">
    <thead><tr><th>Week</th><th>Winner/tie</th><th></th><th>Loser/tie</th></tr></thead>
    <tbody>
    <tr><td data-stat="week_num">1</td>
        <td data-stat="winner"><a href="/teams/kan/2024.htm">Kansas City Chiefs</a></td>
        <td data-stat="game_location"></td>
        <td data-stat="loser"><a href="/teams/rav/2024.htm">Baltimore Ravens</a></td></tr>
    <tr><td data-stat="week_num">WildCard</td>
        <td data-stat="winner"><a href="/teams/kan/2024.htm">Kansas City Chiefs</a></td>
        <td data-stat="game_location"></td>
        <td data-stat="loser"><a href="/teams/phi/2024.htm">Philadelphia Eagles</a></td></tr>
    </tbody>
    </table>
    """
    schedule = parse_schedule(html)
    # Only week 1 game should be in schedule
    assert len(schedule["KC"]) == 1
    assert schedule["KC"][0] == "BAL"


def test_parse_schedule_empty_table():
    html = """<table id="games"><tbody></tbody></table>"""
    schedule = parse_schedule(html)
    assert schedule == {}


def test_scrape_schedule_caches_locally(tmp_path):
    with patch("src.data_scraper.HISTORICAL_DIR", tmp_path):
        with patch("src.data_scraper._fetch_page") as mock_fetch:
            mock_fetch.return_value = "<html><body><table id='games'><tbody></tbody></table></body></html>"
            scrape_schedule(2024)
            assert (tmp_path / "2024_schedule.json").exists()
            # Second call should use cache
            scrape_schedule(2024)
            assert mock_fetch.call_count == 1
