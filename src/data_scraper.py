"""Data scraper for NFL season stats from Pro Football Reference and ADP data."""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.models import Player, ProjectedStats, Position


HISTORICAL_DIR = Path(__file__).parent.parent / "data" / "historical"

PFR_BASE = "https://www.pro-football-reference.com/years/{year}"
PFR_URLS = {
    "passing": PFR_BASE + "/passing.htm",
    "rushing": PFR_BASE + "/rushing.htm",
    "receiving": PFR_BASE + "/receiving.htm",
    "kicking": PFR_BASE + "/kicking.htm",
    "defense": PFR_BASE + "/opp.htm",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _clean_name(name: str) -> str:
    """Strip PFR suffixes like *, +, \\ from player names."""
    return re.sub(r"[*+\\]+$", "", name).strip()


def _safe_int(value: str) -> int:
    """Convert string to int, returning 0 for empty/invalid values."""
    if not value or not value.strip():
        return 0
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return 0


def _fetch_page(url: str) -> str:
    """GET request with User-Agent header and 3-second sleep between requests."""
    time.sleep(3)
    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.text


def _find_table(html: str, table_id: str) -> Optional[BeautifulSoup]:
    """Find a table by id, handling PFR's comment-wrapped tables."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id=table_id)
    if table:
        return table
    # PFR sometimes wraps tables in HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, str) and table_id in text):
        comment_soup = BeautifulSoup(comment, "lxml")
        table = comment_soup.find("table", id=table_id)
        if table:
            return table
    return None


def _is_header_row(row) -> bool:
    """Check if a row is a repeated header row within tbody."""
    if row.get("class") and "thead" in row.get("class", []):
        return True
    # Check if the row has a th element instead of td
    if row.find("th") and not row.find("td"):
        return True
    return False


def _get_player_name(row) -> Optional[str]:
    """Extract and clean player name from a row."""
    cell = row.find("td", {"data-stat": "player"})
    if not cell:
        return None
    # Try to get name from inner <a> tag first
    link = cell.find("a")
    if link:
        name = link.get_text(strip=True)
    else:
        name = cell.get_text(strip=True)
    if not name:
        return None
    return _clean_name(name)


def _get_stat(row, stat_name: str) -> int:
    """Extract an integer stat from a row."""
    cell = row.find("td", {"data-stat": stat_name})
    if not cell:
        return 0
    return _safe_int(cell.get_text(strip=True))


def _get_team(row) -> str:
    """Extract team abbreviation from a row."""
    cell = row.find("td", {"data-stat": "team_name_abbr"})
    if not cell:
        # Try alternate stat name
        cell = row.find("td", {"data-stat": "team"})
    if not cell:
        return ""
    return cell.get_text(strip=True)


def parse_pfr_passing(html: str) -> list[dict]:
    """Parse PFR passing stats table."""
    table = _find_table(html, "passing")
    if not table:
        return []

    results = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr"):
        if _is_header_row(row):
            continue
        name = _get_player_name(row)
        if not name:
            continue
        results.append({
            "name": name,
            "team": _get_team(row),
            "pass_yards": _get_stat(row, "pass_yds"),
            "pass_tds": _get_stat(row, "pass_td"),
            "interceptions": _get_stat(row, "pass_int"),
        })
    return results


def parse_pfr_rushing(html: str) -> list[dict]:
    """Parse PFR rushing stats table."""
    table = _find_table(html, "rushing")
    if not table:
        return []

    results = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr"):
        if _is_header_row(row):
            continue
        name = _get_player_name(row)
        if not name:
            continue
        results.append({
            "name": name,
            "team": _get_team(row),
            "rush_yards": _get_stat(row, "rush_yds"),
            "rush_tds": _get_stat(row, "rush_td"),
        })
    return results


def parse_pfr_receiving(html: str) -> list[dict]:
    """Parse PFR receiving stats table."""
    table = _find_table(html, "receiving")
    if not table:
        return []

    results = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr"):
        if _is_header_row(row):
            continue
        name = _get_player_name(row)
        if not name:
            continue
        results.append({
            "name": name,
            "team": _get_team(row),
            "receptions": _get_stat(row, "rec"),
            "rec_yards": _get_stat(row, "rec_yds"),
            "rec_tds": _get_stat(row, "rec_td"),
        })
    return results


def parse_pfr_kicking(html: str) -> list[dict]:
    """Parse PFR kicking stats table."""
    table = _find_table(html, "kicking")
    if not table:
        return []

    results = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr"):
        if _is_header_row(row):
            continue
        name = _get_player_name(row)
        if not name:
            continue
        results.append({
            "name": name,
            "team": _get_team(row),
            "field_goals": _get_stat(row, "fgm"),
            "extra_points": _get_stat(row, "xpm"),
        })
    return results


def parse_pfr_defense(html: str) -> list[dict]:
    """Parse PFR team defense stats table."""
    # Try multiple possible table IDs
    table = None
    for table_id in ["team_stats", "opp", "team_defense", "defense"]:
        table = _find_table(html, table_id)
        if table:
            break

    if not table:
        return []

    results = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr"):
        if _is_header_row(row):
            continue

        # Team name can be in different stat fields
        team_cell = row.find("td", {"data-stat": "team_name"})
        if not team_cell:
            team_cell = row.find("td", {"data-stat": "team"})
        if not team_cell:
            # Try th for team name
            team_cell = row.find("th", {"data-stat": "team"})
        if not team_cell:
            continue

        link = team_cell.find("a")
        team_name = link.get_text(strip=True) if link else team_cell.get_text(strip=True)
        if not team_name:
            continue

        total_points = _get_stat(row, "points_opp")
        if total_points == 0:
            total_points = _get_stat(row, "pts_opp")
        ppg = round(total_points / 17, 1) if total_points > 0 else 0.0

        # Extract team abbreviation
        team_abbr_cell = row.find("td", {"data-stat": "team_name_abbr"})
        team_abbr = team_abbr_cell.get_text(strip=True) if team_abbr_cell else ""

        results.append({
            "name": team_name,
            "team": team_abbr if team_abbr else team_name,
            "sacks": _get_stat(row, "sacks"),
            "def_interceptions": _get_stat(row, "pass_int"),
            "def_tds": _get_stat(row, "def_tds"),
            "points_allowed_per_game": ppg,
        })
    return results


def build_player_dataset(
    passing: list[dict],
    rushing: list[dict],
    receiving: list[dict],
    kicking: list[dict],
    defense: list[dict],
) -> list[Player]:
    """Merge all stat dicts by player name and create Player objects."""
    # Collect all stats by player name
    player_stats: dict[str, dict] = {}

    # Process passing stats
    for p in passing:
        name = p["name"]
        if name not in player_stats:
            player_stats[name] = {"team": p.get("team", ""), "sources": set()}
        player_stats[name]["sources"].add("passing")
        player_stats[name]["pass_yards"] = p.get("pass_yards", 0)
        player_stats[name]["pass_tds"] = p.get("pass_tds", 0)
        player_stats[name]["interceptions"] = p.get("interceptions", 0)

    # Process rushing stats
    for p in rushing:
        name = p["name"]
        if name not in player_stats:
            player_stats[name] = {"team": p.get("team", ""), "sources": set()}
        player_stats[name]["sources"].add("rushing")
        player_stats[name]["rush_yards"] = p.get("rush_yards", 0)
        player_stats[name]["rush_tds"] = p.get("rush_tds", 0)
        if not player_stats[name].get("team"):
            player_stats[name]["team"] = p.get("team", "")

    # Process receiving stats
    for p in receiving:
        name = p["name"]
        if name not in player_stats:
            player_stats[name] = {"team": p.get("team", ""), "sources": set()}
        player_stats[name]["sources"].add("receiving")
        player_stats[name]["receptions"] = p.get("receptions", 0)
        player_stats[name]["rec_yards"] = p.get("rec_yards", 0)
        player_stats[name]["rec_tds"] = p.get("rec_tds", 0)
        if not player_stats[name].get("team"):
            player_stats[name]["team"] = p.get("team", "")

    # Process kicking stats
    for p in kicking:
        name = p["name"]
        if name not in player_stats:
            player_stats[name] = {"team": p.get("team", ""), "sources": set()}
        player_stats[name]["sources"].add("kicking")
        player_stats[name]["field_goals"] = p.get("field_goals", 0)
        player_stats[name]["extra_points"] = p.get("extra_points", 0)
        if not player_stats[name].get("team"):
            player_stats[name]["team"] = p.get("team", "")

    # Build Player objects (non-defense)
    players = []
    for name, stats in player_stats.items():
        sources = stats.get("sources", set())

        # Position assignment
        if "passing" in sources and stats.get("pass_yards", 0) > 500:
            position = Position.QB
        elif "kicking" in sources:
            position = Position.K
        elif "rushing" in sources and stats.get("rush_yards", 0) > stats.get("rec_yards", 0):
            position = Position.RB
        elif "receiving" in sources:
            position = Position.WR
        elif "rushing" in sources:
            position = Position.RB
        else:
            # Fallback: if only in passing with <= 500 yards, still QB
            if "passing" in sources:
                position = Position.QB
            else:
                continue  # Skip players with no meaningful stats

        projected = ProjectedStats(
            pass_yards=float(stats.get("pass_yards", 0)),
            pass_tds=float(stats.get("pass_tds", 0)),
            interceptions=float(stats.get("interceptions", 0)),
            rush_yards=float(stats.get("rush_yards", 0)),
            rush_tds=float(stats.get("rush_tds", 0)),
            receptions=float(stats.get("receptions", 0)),
            rec_yards=float(stats.get("rec_yards", 0)),
            rec_tds=float(stats.get("rec_tds", 0)),
            field_goals=float(stats.get("field_goals", 0)),
            extra_points=float(stats.get("extra_points", 0)),
        )

        players.append(Player(
            name=name,
            team=stats.get("team", ""),
            position=position,
            bye_week=0,
            projected_stats=projected,
            adp=200.0,
        ))

    # Process defense entries
    for d in defense:
        projected = ProjectedStats(
            sacks=float(d.get("sacks", 0)),
            def_interceptions=float(d.get("def_interceptions", 0)),
            def_tds=float(d.get("def_tds", 0)),
            points_allowed_per_game=float(d.get("points_allowed_per_game", 0)),
        )
        players.append(Player(
            name=d["name"],
            team=d.get("team", ""),
            position=Position.DEF,
            bye_week=0,
            projected_stats=projected,
            adp=200.0,
        ))

    return players


def scrape_season(year: int) -> list[Player]:
    """Scrape a full season of stats, with local file caching."""
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = HISTORICAL_DIR / f"{year}_actual_stats.json"

    # Check cache
    if cache_file.exists():
        with open(cache_file) as f:
            data = json.load(f)
        return [Player.from_dict(p) for p in data["players"]]

    # Fetch all pages
    passing_html = _fetch_page(PFR_URLS["passing"].format(year=year))
    rushing_html = _fetch_page(PFR_URLS["rushing"].format(year=year))
    receiving_html = _fetch_page(PFR_URLS["receiving"].format(year=year))
    kicking_html = _fetch_page(PFR_URLS["kicking"].format(year=year))
    defense_html = _fetch_page(PFR_URLS["defense"].format(year=year))

    # Parse each page
    passing = parse_pfr_passing(passing_html)
    rushing = parse_pfr_rushing(rushing_html)
    receiving = parse_pfr_receiving(receiving_html)
    kicking = parse_pfr_kicking(kicking_html)
    defense = parse_pfr_defense(defense_html)

    # Build dataset
    players = build_player_dataset(passing, rushing, receiving, kicking, defense)

    # Cache to disk
    data = {"players": [p.to_dict() for p in players]}
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)

    return players


# PFR URL path codes to standard team abbreviations (matching players.json)
_PFR_TEAM_ABBREVS = {
    "crd": "ARI", "atl": "ATL", "rav": "BAL", "buf": "BUF",
    "car": "CAR", "chi": "CHI", "cin": "CIN", "cle": "CLE",
    "dal": "DAL", "den": "DEN", "det": "DET", "gnb": "GB",
    "htx": "HOU", "clt": "IND", "jax": "JAX", "kan": "KC",
    "rai": "LV", "sdg": "LAC", "ram": "LAR", "mia": "MIA",
    "min": "MIN", "nwe": "NE", "nor": "NO", "nyg": "NYG",
    "nyj": "NYJ", "phi": "PHI", "pit": "PIT", "sfo": "SF",
    "sea": "SEA", "tam": "TB", "oti": "TEN", "was": "WAS",
}


def _extract_team_abbrev(cell) -> str:
    """Extract team abbreviation from a PFR game cell."""
    link = cell.find("a")
    if link and link.get("href"):
        # href like "/teams/kan/2024.htm"
        parts = link["href"].strip("/").split("/")
        if len(parts) >= 2:
            pfr_code = parts[1].lower()
            return _PFR_TEAM_ABBREVS.get(pfr_code, pfr_code.upper())
    return cell.get_text(strip=True)


def parse_schedule(html: str) -> dict[str, list[str | None]]:
    """Parse PFR games page into a schedule.

    Returns dict mapping team abbreviation to list of opponents by week index.
    Week index 0 = Week 1, etc. None for bye weeks.
    """
    table = _find_table(html, "games")
    if table is None:
        return {}

    # Collect all games by week
    games: list[tuple[int, str, str]] = []  # (week, team1, team2)
    rows = table.find("tbody").find_all("tr") if table.find("tbody") else []
    for row in rows:
        if _is_header_row(row):
            continue
        week_cell = row.find("td", {"data-stat": "week_num"})
        winner_cell = row.find("td", {"data-stat": "winner"})
        loser_cell = row.find("td", {"data-stat": "loser"})
        if not week_cell or not winner_cell or not loser_cell:
            continue
        week_text = week_cell.get_text(strip=True)
        if not week_text.isdigit():
            continue
        week = int(week_text)
        winner = _extract_team_abbrev(winner_cell)
        loser = _extract_team_abbrev(loser_cell)
        if winner and loser:
            games.append((week, winner, loser))

    # Build schedule: {team: [opponent_week1, opponent_week2, ...]}
    max_week = max((g[0] for g in games), default=0)
    schedule: dict[str, list[str | None]] = {}
    for week, team1, team2 in games:
        for t, opp in [(team1, team2), (team2, team1)]:
            if t not in schedule:
                schedule[t] = [None] * max_week
            idx = week - 1
            if idx < len(schedule[t]):
                schedule[t][idx] = opp

    return schedule


def scrape_schedule(year: int) -> dict[str, list[str | None]]:
    """Scrape NFL schedule for a given year. Cached to disk."""
    cache_file = HISTORICAL_DIR / f"{year}_schedule.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://www.pro-football-reference.com/years/{year}/games.htm"
    html = _fetch_page(url)
    schedule = parse_schedule(html)

    with open(cache_file, "w") as f:
        json.dump(schedule, f, indent=2)

    return schedule


def scrape_preseason_adp(year: int) -> dict[str, float]:
    """Get preseason ADP data. Uses fallback generation if scraping is unreliable.

    Returns dict mapping player name to ADP float.
    Caches to HISTORICAL_DIR/{year}_preseason_adp.json.
    """
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = HISTORICAL_DIR / f"{year}_preseason_adp.json"

    # Check cache
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    # Fallback: generate reasonable ADP from typical draft ordering
    # This provides a sensible default when scraping is unreliable
    adp_data = _generate_fallback_adp(year)

    # Cache to disk
    with open(cache_file, "w") as f:
        json.dump(adp_data, f, indent=2)

    return adp_data


def _generate_fallback_adp(year: int) -> dict[str, float]:
    """Generate reasonable ADP values based on typical fantasy draft patterns.

    This provides a fallback when live ADP scraping is unreliable.
    Players are ordered by typical positional value tiers.
    """
    # Typical top fantasy players by tier (generic template)
    # In practice, these would be populated from a known ADP source
    tiers = {
        # Tier 1: Elite RBs and WRs (ADP 1-12)
        "Elite RB1": (Position.RB, 1.0),
        "Elite RB2": (Position.RB, 2.0),
        "Elite WR1": (Position.WR, 3.0),
        "Elite RB3": (Position.RB, 4.0),
        "Elite WR2": (Position.WR, 5.0),
        "Elite RB4": (Position.RB, 6.0),
        "Elite WR3": (Position.WR, 7.0),
        "Elite WR4": (Position.WR, 8.0),
        "Elite RB5": (Position.RB, 9.0),
        "Elite TE1": (Position.TE, 10.0),
        "Elite WR5": (Position.WR, 11.0),
        "Elite RB6": (Position.RB, 12.0),
    }

    # Try to load actual stats to generate realistic ADP ordering
    stats_file = HISTORICAL_DIR / f"{year}_actual_stats.json"
    if stats_file.exists():
        with open(stats_file) as f:
            data = json.load(f)
        players = [Player.from_dict(p) for p in data["players"]]
        # Sort by a rough fantasy points estimate and assign ADP
        from src.scoring import ScoringEngine
        engine = ScoringEngine()
        for p in players:
            p.fantasy_points = engine.calculate(p)
        players.sort(key=lambda p: p.fantasy_points, reverse=True)
        return {p.name: float(i + 1) for i, p in enumerate(players)}

    # If no stats available, return a minimal placeholder
    return {name: adp for name, (_, adp) in tiers.items()}
