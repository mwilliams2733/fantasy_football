# Matchup-Based Lineup Optimizer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a matchup-aware lineup optimizer that scrapes NFL schedules and defense rankings from PFR, adjusts player projections by weekly matchup, finds optimal lineups via permutation search, and validates via Monte Carlo simulation. Enforce roster composition rules (max 2 QB, 1 K, 1 DEF).

**Architecture:** Extend `data_scraper.py` with schedule/defense ranking scraping. New `matchup_optimizer.py` module handles matchup adjustments, permutation search, and Monte Carlo simulation. New API route and UI panel in the team manager page. Roster rules enforced in draft engine and team manager.

**Tech Stack:** Python, BeautifulSoup (PFR scraping), Flask (API), vanilla JS (UI), existing scoring/models infrastructure.

---

### Task 1: Scrape NFL Schedule from PFR

**Files:**
- Modify: `src/data_scraper.py`
- Test: `tests/test_data_scraper.py`

**Step 1: Write the failing test**

Add to `tests/test_data_scraper.py`:

```python
def test_parse_schedule():
    from src.data_scraper import parse_schedule
    html = """
    <table id="games">
    <thead><tr><th>Week</th><th>Winner/tie</th><th></th><th>Loser/tie</th></tr></thead>
    <tbody>
    <tr><td data-stat="week_num">1</td>
        <td data-stat="winner"><a href="/teams/kan/2024.htm">Kansas City Chiefs</a></td>
        <td data-stat="game_location"></td>
        <td data-stat="loser"><a href="/teams/bal/2024.htm">Baltimore Ravens</a></td></tr>
    <tr><td data-stat="week_num">1</td>
        <td data-stat="winner"><a href="/teams/phi/2024.htm">Philadelphia Eagles</a></td>
        <td data-stat="game_location">@</td>
        <td data-stat="loser"><a href="/teams/gnb/2024.htm">Green Bay Packers</a></td></tr>
    </tbody>
    </table>
    """
    schedule = parse_schedule(html)
    # KAN played at home vs BAL
    assert "KAN" in schedule
    assert schedule["KAN"][0] == "BAL"
    # BAL played at KAN
    assert "BAL" in schedule
    assert schedule["BAL"][0] == "KAN"
    # PHI played @ GNB (winner was away)
    assert "PHI" in schedule
    assert schedule["PHI"][0] == "GNB"
    assert "GNB" in schedule
    assert schedule["GNB"][0] == "PHI"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_scraper.py::test_parse_schedule -v`
Expected: FAIL with `ImportError: cannot import name 'parse_schedule'`

**Step 3: Implement `parse_schedule()`**

Add to `src/data_scraper.py`:

```python
# Team abbreviation mapping for PFR URL paths
_PFR_TEAM_ABBREVS = {
    "crd": "ARI", "atl": "ATL", "rav": "BAL", "buf": "BUF",
    "car": "CAR", "chi": "CHI", "cin": "CIN", "cle": "CLE",
    "dal": "DAL", "den": "DEN", "det": "DET", "gnb": "GBP",
    "htx": "HOU", "clt": "IND", "jax": "JAX", "kan": "KCC",
    "rai": "LVR", "sdg": "LAC", "ram": "LAR", "mia": "MIA",
    "min": "MIN", "nwe": "NEP", "nor": "NOS", "nyg": "NYG",
    "nyj": "NYJ", "phi": "PHI", "pit": "PIT", "sfo": "SFO",
    "sea": "SEA", "tam": "TBB", "oti": "TEN", "was": "WAS",
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_data_scraper.py::test_parse_schedule -v`
Expected: PASS

**Step 5: Add `scrape_schedule()` with caching**

Add to `src/data_scraper.py`:

```python
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
```

**Step 6: Write cache test**

```python
def test_scrape_schedule_caches_locally(tmp_path):
    from unittest.mock import patch
    from src.data_scraper import scrape_schedule
    with patch("src.data_scraper.HISTORICAL_DIR", tmp_path):
        with patch("src.data_scraper._fetch_page") as mock_fetch:
            mock_fetch.return_value = "<html><body><table id='games'><tbody></tbody></table></body></html>"
            scrape_schedule(2024)
            assert (tmp_path / "2024_schedule.json").exists()
            # Second call should use cache
            scrape_schedule(2024)
            assert mock_fetch.call_count == 1
```

**Step 7: Run all tests, then commit**

Run: `pytest tests/test_data_scraper.py -v`
Expected: All pass

```bash
git add src/data_scraper.py tests/test_data_scraper.py
git commit -m "feat: add NFL schedule scraping from PFR"
```

---

### Task 2: Scrape Defense Rankings from PFR

**Files:**
- Modify: `src/data_scraper.py`
- Test: `tests/test_data_scraper.py`

**Step 1: Write the failing test**

```python
def test_scrape_defense_rankings_structure(tmp_path):
    """Defense rankings should rank teams 1-32 per position."""
    from unittest.mock import patch
    from src.data_scraper import scrape_defense_rankings

    # Create a fake cached file with known data
    import json
    fake_rankings = {
        "KCC": {"vs_QB": 5, "vs_RB": 10, "vs_WR": 15, "vs_TE": 20},
        "BAL": {"vs_QB": 1, "vs_RB": 2, "vs_WR": 3, "vs_TE": 4},
    }
    cache_file = tmp_path / "2024_defense_rankings.json"
    with open(cache_file, "w") as f:
        json.dump(fake_rankings, f)

    with patch("src.data_scraper.HISTORICAL_DIR", tmp_path):
        rankings = scrape_defense_rankings(2024)
        assert "KCC" in rankings
        assert rankings["KCC"]["vs_QB"] == 5
        assert rankings["BAL"]["vs_RB"] == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_scraper.py::test_scrape_defense_rankings_structure -v`
Expected: FAIL with `ImportError`

**Step 3: Implement defense rankings scraping**

Add to `src/data_scraper.py`:

```python
def _compute_defense_rankings(defense_stats: list[dict]) -> dict[str, dict[str, int]]:
    """Compute per-position defense rankings from raw defense stats.

    Ranks teams 1-32 (1 = best defense = fewest points allowed).
    Uses points_allowed_per_game as proxy for overall defense quality,
    with sacks/interceptions as secondary signals for positional impact.
    """
    if not defense_stats:
        return {}

    # Sort by points allowed (ascending = best defense first)
    sorted_teams = sorted(defense_stats, key=lambda d: d.get("points_allowed_per_game", 99))

    rankings: dict[str, dict[str, int]] = {}
    for rank_idx, team_data in enumerate(sorted_teams):
        team = team_data.get("team", "")
        if not team:
            continue
        base_rank = rank_idx + 1
        # All positions get same base rank (derived from total defense)
        # Adjust slightly: high-sack teams are harder for QBs
        rankings[team] = {
            "vs_QB": base_rank,
            "vs_RB": base_rank,
            "vs_WR": base_rank,
            "vs_TE": base_rank,
        }

    return rankings


def scrape_defense_rankings(year: int) -> dict[str, dict[str, int]]:
    """Scrape and compute defense rankings for a given year. Cached to disk."""
    cache_file = HISTORICAL_DIR / f"{year}_defense_rankings.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    url = PFR_URLS["defense"].format(year=year)
    html = _fetch_page(url)
    defense_stats = parse_pfr_defense(html)
    rankings = _compute_defense_rankings(defense_stats)

    with open(cache_file, "w") as f:
        json.dump(rankings, f, indent=2)

    return rankings
```

**Step 4: Run tests**

Run: `pytest tests/test_data_scraper.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/data_scraper.py tests/test_data_scraper.py
git commit -m "feat: add defense rankings scraping from PFR"
```

---

### Task 3: Matchup Optimizer Core — Matchup Adjustment + Permutations

**Files:**
- Create: `src/matchup_optimizer.py`
- Create: `tests/test_matchup_optimizer.py`

**Step 1: Write failing tests**

Create `tests/test_matchup_optimizer.py`:

```python
"""Tests for matchup-based lineup optimizer."""

from src.models import Player, Team, Position, ProjectedStats, RosterEntry, RosterSlot
from src.scoring import calculate_fantasy_points


def _make_player(name, pos, pts, team="NYG"):
    """Helper to create a scored player."""
    p = Player(name=name, team=team, position=Position(pos), bye_week=7)
    p.fantasy_points = pts
    return p


def test_matchup_multiplier():
    from src.matchup_optimizer import get_matchup_multiplier
    # Rank 1 (best defense) should reduce points
    assert get_matchup_multiplier(1) < 1.0
    # Rank 16 (average) should be ~neutral
    assert abs(get_matchup_multiplier(16) - 1.0) < 0.02
    # Rank 32 (worst defense) should boost points
    assert get_matchup_multiplier(32) > 1.0


def test_matchup_adjusted_points():
    from src.matchup_optimizer import get_matchup_adjusted_points
    player = _make_player("TestQB", "QB", 300.0, team="KCC")
    defense_rankings = {"BAL": {"vs_QB": 1, "vs_RB": 16, "vs_WR": 32, "vs_TE": 10}}
    # QB vs rank-1 defense should reduce points
    adj = get_matchup_adjusted_points(player, "BAL", defense_rankings)
    assert adj < 300.0


def test_generate_lineup_permutations():
    from src.matchup_optimizer import generate_lineup_permutations
    # Build a roster: 1 QB, 3 RBs, 2 WRs, 1 TE, 1 K, 1 DEF
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 300), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 200), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 180), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB3", "RB", 120), slot=RosterSlot.BENCH),
        RosterEntry(player=_make_player("WR1", "WR", 250), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 220), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("TE1", "TE", 150), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("K1", "K", 100), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 80), slot=RosterSlot.DEF),
    ]
    team = Team(name="Test", draft_position=1, roster=roster)
    perms = generate_lineup_permutations(team)
    # Should have at least 2 permutations (RB3 in FLEX vs not)
    assert len(perms) >= 2
    # Each permutation should have exactly 9 starters
    for lineup in perms:
        starters = [e for e in lineup if e.slot != RosterSlot.BENCH]
        assert len(starters) == 9


def test_validate_roster_rules():
    from src.matchup_optimizer import validate_roster_rules
    # Valid roster: 1 QB, 2 RB, 2 WR, 1 TE, 1 K, 1 DEF = 8 players
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 300), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 200), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 180), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("WR1", "WR", 250), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 220), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("TE1", "TE", 150), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("K1", "K", 100), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 80), slot=RosterSlot.DEF),
    ]
    team = Team(name="Test", draft_position=1, roster=roster)
    violations = validate_roster_rules(team)
    assert len(violations) == 0

    # Add 3rd QB — should violate
    roster.append(RosterEntry(player=_make_player("QB2", "QB", 200), slot=RosterSlot.BENCH))
    roster.append(RosterEntry(player=_make_player("QB3", "QB", 150), slot=RosterSlot.BENCH))
    team2 = Team(name="Bad", draft_position=1, roster=roster)
    violations = validate_roster_rules(team2)
    assert len(violations) == 1
    assert "QB" in violations[0]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_matchup_optimizer.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement `src/matchup_optimizer.py`**

```python
"""Matchup-based lineup optimizer with permutation search and Monte Carlo simulation."""

import random
from itertools import combinations
from dataclasses import dataclass, field
from src.models import (
    Player, Team, Position, RosterEntry, RosterSlot,
    ROSTER_SLOTS, FLEX_ELIGIBLE,
)


# --- Roster Rules ---

MAX_ROSTER = {Position.QB: 2, Position.K: 1, Position.DEF: 1}


def validate_roster_rules(team: Team) -> list[str]:
    """Check roster composition rules. Returns list of violation messages."""
    violations = []
    for pos, max_count in MAX_ROSTER.items():
        count = team.position_count(pos)
        if count > max_count:
            violations.append(f"Too many {pos.value}s: {count} (max {max_count})")
    return violations


# --- Matchup Adjustment ---

def get_matchup_multiplier(defense_rank: int) -> float:
    """Convert defense rank (1-32) to a projection multiplier.

    Rank 1 (best D): 0.84, Rank 16: 1.01, Rank 32 (worst D): 1.16
    """
    return 1.0 + (17 - defense_rank) * 0.01


def get_matchup_adjusted_points(
    player: Player, opponent: str, defense_rankings: dict[str, dict[str, int]]
) -> float:
    """Adjust a player's fantasy points based on opponent defense ranking."""
    pos_key = f"vs_{player.position.value}"
    opp_rankings = defense_rankings.get(opponent, {})
    rank = opp_rankings.get(pos_key, 16)  # Default to average if unknown
    multiplier = get_matchup_multiplier(rank)
    return player.fantasy_points * multiplier


# --- Lineup Permutations ---

def generate_lineup_permutations(team: Team) -> list[list[RosterEntry]]:
    """Generate all valid starter lineup permutations.

    Fixed slots filled by best at each position. FLEX is the variable —
    tries every eligible RB/WR/TE not already starting.
    Returns list of complete rosters (starters + bench).
    """
    roster = team.roster
    players_by_pos: dict[Position, list[RosterEntry]] = {}
    for e in roster:
        players_by_pos.setdefault(e.player.position, []).append(e)

    # Sort each position group by points descending
    for pos in players_by_pos:
        players_by_pos[pos].sort(key=lambda e: e.player.fantasy_points, reverse=True)

    # Fixed starters: best at each required slot
    fixed_starters: list[RosterEntry] = []
    used_names: set[str] = set()

    slot_positions = [
        (RosterSlot.QB, Position.QB, ROSTER_SLOTS[RosterSlot.QB]),
        (RosterSlot.RB, Position.RB, ROSTER_SLOTS[RosterSlot.RB]),
        (RosterSlot.WR, Position.WR, ROSTER_SLOTS[RosterSlot.WR]),
        (RosterSlot.TE, Position.TE, ROSTER_SLOTS[RosterSlot.TE]),
        (RosterSlot.K, Position.K, ROSTER_SLOTS[RosterSlot.K]),
        (RosterSlot.DEF, Position.DEF, ROSTER_SLOTS[RosterSlot.DEF]),
    ]

    for slot, pos, count in slot_positions:
        candidates = [e for e in players_by_pos.get(pos, []) if e.player.name not in used_names]
        for c in candidates[:count]:
            fixed_starters.append(RosterEntry(player=c.player, slot=slot))
            used_names.add(c.player.name)

    # FLEX candidates: eligible players not already starting
    flex_candidates = [
        e for e in roster
        if e.player.position in FLEX_ELIGIBLE and e.player.name not in used_names
    ]

    if not flex_candidates:
        # Only one lineup possible
        bench = [
            RosterEntry(player=e.player, slot=RosterSlot.BENCH)
            for e in roster if e.player.name not in used_names
        ]
        return [fixed_starters + bench]

    # Generate one permutation per FLEX candidate
    permutations = []
    for flex_entry in flex_candidates:
        lineup = list(fixed_starters)
        lineup.append(RosterEntry(player=flex_entry.player, slot=RosterSlot.FLEX))
        flex_used = used_names | {flex_entry.player.name}
        bench = [
            RosterEntry(player=e.player, slot=RosterSlot.BENCH)
            for e in roster if e.player.name not in flex_used
        ]
        permutations.append(lineup + bench)

    return permutations


# --- Lineup Evaluation ---

@dataclass
class LineupEvaluation:
    """Result of evaluating a single lineup variant."""
    total_points: float
    players: list[dict]  # [{name, slot, base_pts, adjusted_pts, opponent, matchup_grade}]


@dataclass
class MonteCarloResult:
    """Result of Monte Carlo simulation on a lineup."""
    mean: float
    floor: float  # 10th percentile
    ceiling: float  # 90th percentile
    consistency: float  # % of sims above league average


@dataclass
class LineupRecommendation:
    """A recommended lineup with evaluation and Monte Carlo stats."""
    lineup: list[RosterEntry]
    evaluation: LineupEvaluation
    monte_carlo: MonteCarloResult


def evaluate_lineup(
    lineup: list[RosterEntry],
    opponent_map: dict[str, str],  # {player_team: opponent_team}
    defense_rankings: dict[str, dict[str, int]],
) -> LineupEvaluation:
    """Score a lineup using matchup-adjusted projections."""
    total = 0.0
    players = []
    for entry in lineup:
        if entry.slot == RosterSlot.BENCH:
            continue
        p = entry.player
        opponent = opponent_map.get(p.team, "")
        base_pts = p.fantasy_points
        adj_pts = get_matchup_adjusted_points(p, opponent, defense_rankings) if opponent else base_pts

        # Matchup grade
        pos_key = f"vs_{p.position.value}"
        rank = defense_rankings.get(opponent, {}).get(pos_key, 16) if opponent else 16
        if rank <= 8:
            grade = "tough"
        elif rank <= 24:
            grade = "neutral"
        else:
            grade = "favorable"

        total += adj_pts
        players.append({
            "name": p.name,
            "slot": entry.slot.value,
            "position": p.position.value,
            "base_pts": round(base_pts, 1),
            "adjusted_pts": round(adj_pts, 1),
            "opponent": opponent or "BYE",
            "matchup_grade": grade,
        })

    return LineupEvaluation(total_points=round(total, 1), players=players)


def monte_carlo_lineup(
    lineup: list[RosterEntry],
    opponent_map: dict[str, str],
    defense_rankings: dict[str, dict[str, int]],
    simulations: int = 500,
) -> MonteCarloResult:
    """Run Monte Carlo simulation on a lineup with random variance."""
    sim_totals = []
    for _ in range(simulations):
        total = 0.0
        for entry in lineup:
            if entry.slot == RosterSlot.BENCH:
                continue
            p = entry.player
            opponent = opponent_map.get(p.team, "")
            base = get_matchup_adjusted_points(p, opponent, defense_rankings) if opponent else p.fantasy_points
            # Add variance: normal distribution with 15% stddev
            varied = max(0, random.gauss(base, base * 0.15))
            total += varied
        sim_totals.append(total)

    sim_totals.sort()
    n = len(sim_totals)
    floor_idx = max(0, int(n * 0.10) - 1)
    ceiling_idx = min(n - 1, int(n * 0.90))
    mean = sum(sim_totals) / n
    # League average: ~110 pts/week for a 9-starter lineup
    league_avg = 110.0
    consistency = sum(1 for t in sim_totals if t >= league_avg) / n * 100

    return MonteCarloResult(
        mean=round(mean, 1),
        floor=round(sim_totals[floor_idx], 1),
        ceiling=round(sim_totals[ceiling_idx], 1),
        consistency=round(consistency, 1),
    )


def optimize_with_matchups(
    team: Team,
    week: int,
    schedule: dict[str, list[str | None]],
    defense_rankings: dict[str, dict[str, int]],
) -> dict:
    """Main entry point: find optimal lineup for a given week.

    Returns dict with recommended_lineup, alternatives, and analysis.
    """
    # Build opponent map for this week
    opponent_map: dict[str, str] = {}
    for team_abbrev, opponents in schedule.items():
        week_idx = week - 1
        if week_idx < len(opponents) and opponents[week_idx] is not None:
            opponent_map[team_abbrev] = opponents[week_idx]

    # Generate all valid lineup permutations
    permutations = generate_lineup_permutations(team)

    # Evaluate each permutation
    evaluations: list[tuple[list[RosterEntry], LineupEvaluation]] = []
    for lineup in permutations:
        ev = evaluate_lineup(lineup, opponent_map, defense_rankings)
        evaluations.append((lineup, ev))

    # Sort by total matchup-adjusted points descending
    evaluations.sort(key=lambda x: x[1].total_points, reverse=True)

    # Take top 3 and run Monte Carlo
    recommendations: list[LineupRecommendation] = []
    for lineup, ev in evaluations[:3]:
        mc = monte_carlo_lineup(lineup, opponent_map, defense_rankings)
        recommendations.append(LineupRecommendation(lineup=lineup, evaluation=ev, monte_carlo=mc))

    # Sort final recommendations by Monte Carlo mean
    recommendations.sort(key=lambda r: r.monte_carlo.mean, reverse=True)

    recommended = recommendations[0] if recommendations else None
    alternatives = recommendations[1:] if len(recommendations) > 1 else []

    return {
        "recommended": _recommendation_to_dict(recommended) if recommended else None,
        "alternatives": [_recommendation_to_dict(a) for a in alternatives],
        "week": week,
        "roster_violations": validate_roster_rules(team),
    }


def _recommendation_to_dict(rec: LineupRecommendation) -> dict:
    """Convert a LineupRecommendation to a JSON-serializable dict."""
    return {
        "total_points": rec.evaluation.total_points,
        "players": rec.evaluation.players,
        "monte_carlo": {
            "mean": rec.monte_carlo.mean,
            "floor": rec.monte_carlo.floor,
            "ceiling": rec.monte_carlo.ceiling,
            "consistency": rec.monte_carlo.consistency,
        },
    }
```

**Step 4: Run tests**

Run: `pytest tests/test_matchup_optimizer.py -v`
Expected: All 4 tests pass

**Step 5: Commit**

```bash
git add src/matchup_optimizer.py tests/test_matchup_optimizer.py
git commit -m "feat: add matchup optimizer with permutation search and Monte Carlo"
```

---

### Task 4: Monte Carlo and Full Optimizer Tests

**Files:**
- Modify: `tests/test_matchup_optimizer.py`

**Step 1: Add Monte Carlo and optimizer integration tests**

```python
def test_monte_carlo_returns_valid_stats():
    from src.matchup_optimizer import monte_carlo_lineup
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 20.0, "KCC"), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 15.0, "KCC"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 12.0, "BAL"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("WR1", "WR", 18.0, "BAL"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 14.0, "PHI"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("TE1", "TE", 10.0, "PHI"), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("FLEX1", "RB", 8.0, "KCC"), slot=RosterSlot.FLEX),
        RosterEntry(player=_make_player("K1", "K", 7.0, "DAL"), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 6.0, "DAL"), slot=RosterSlot.DEF),
    ]
    opponent_map = {"KCC": "BAL", "BAL": "KCC", "PHI": "DAL", "DAL": "PHI"}
    defense_rankings = {
        "BAL": {"vs_QB": 3, "vs_RB": 5, "vs_WR": 10, "vs_TE": 15},
        "KCC": {"vs_QB": 20, "vs_RB": 18, "vs_WR": 22, "vs_TE": 25},
        "DAL": {"vs_QB": 16, "vs_RB": 16, "vs_WR": 16, "vs_TE": 16},
        "PHI": {"vs_QB": 10, "vs_RB": 8, "vs_WR": 12, "vs_TE": 14},
    }
    mc = monte_carlo_lineup(roster, opponent_map, defense_rankings, simulations=200)
    assert mc.floor <= mc.mean <= mc.ceiling
    assert 0.0 <= mc.consistency <= 100.0


def test_optimize_with_matchups_returns_recommendation():
    from src.matchup_optimizer import optimize_with_matchups
    roster = [
        RosterEntry(player=_make_player("QB1", "QB", 20.0, "KCC"), slot=RosterSlot.QB),
        RosterEntry(player=_make_player("RB1", "RB", 15.0, "KCC"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB2", "RB", 12.0, "BAL"), slot=RosterSlot.RB),
        RosterEntry(player=_make_player("RB3", "RB", 8.0, "BAL"), slot=RosterSlot.BENCH),
        RosterEntry(player=_make_player("WR1", "WR", 18.0, "PHI"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("WR2", "WR", 14.0, "PHI"), slot=RosterSlot.WR),
        RosterEntry(player=_make_player("TE1", "TE", 10.0, "DAL"), slot=RosterSlot.TE),
        RosterEntry(player=_make_player("K1", "K", 7.0, "DAL"), slot=RosterSlot.K),
        RosterEntry(player=_make_player("DEF1", "DEF", 6.0, "DAL"), slot=RosterSlot.DEF),
    ]
    team = Team(name="Test", draft_position=1, roster=roster)
    schedule = {
        "KCC": ["BAL", "DEN"], "BAL": ["KCC", "CIN"],
        "PHI": ["DAL", "NYG"], "DAL": ["PHI", "WAS"],
    }
    defense_rankings = {
        "BAL": {"vs_QB": 3, "vs_RB": 5, "vs_WR": 10, "vs_TE": 15},
        "KCC": {"vs_QB": 20, "vs_RB": 18, "vs_WR": 22, "vs_TE": 25},
        "DAL": {"vs_QB": 16, "vs_RB": 16, "vs_WR": 16, "vs_TE": 16},
        "PHI": {"vs_QB": 10, "vs_RB": 8, "vs_WR": 12, "vs_TE": 14},
    }
    result = optimize_with_matchups(team, week=1, schedule=schedule, defense_rankings=defense_rankings)
    assert result["recommended"] is not None
    assert result["week"] == 1
    assert "monte_carlo" in result["recommended"]
    assert result["recommended"]["monte_carlo"]["floor"] <= result["recommended"]["monte_carlo"]["ceiling"]
```

**Step 2: Run all matchup optimizer tests**

Run: `pytest tests/test_matchup_optimizer.py -v`
Expected: All 6 tests pass

**Step 3: Commit**

```bash
git add tests/test_matchup_optimizer.py
git commit -m "test: add Monte Carlo and optimizer integration tests"
```

---

### Task 5: Enforce Roster Rules in Draft Engine

**Files:**
- Modify: `src/draft.py`
- Modify: `tests/test_draft.py`

**Step 1: Write failing test**

Add to `tests/test_draft.py`:

```python
def test_draft_respects_roster_limits():
    """AI should not draft a 3rd QB, 2nd K, or 2nd DEF."""
    from src.models import Player, Team, League, Position, ProjectedStats, RosterEntry, RosterSlot
    from src.draft import DraftEngine
    from src.scoring import score_all_players
    from src.rankings import calculate_vbd

    # Create player pool with many QBs to tempt the engine
    players = []
    for i in range(20):
        players.append(Player(name=f"QB{i}", team="TST", position=Position.QB, bye_week=7,
                              projected_stats=ProjectedStats(pass_yards=4000 - i * 100, pass_tds=30 - i)))
    for i in range(20):
        players.append(Player(name=f"RB{i}", team="TST", position=Position.RB, bye_week=7,
                              projected_stats=ProjectedStats(rush_yards=1000 - i * 30, rush_tds=8 - i)))
    for i in range(20):
        players.append(Player(name=f"WR{i}", team="TST", position=Position.WR, bye_week=7,
                              projected_stats=ProjectedStats(rec_yards=1000 - i * 30, rec_tds=8 - i, receptions=80 - i * 3)))
    for i in range(10):
        players.append(Player(name=f"TE{i}", team="TST", position=Position.TE, bye_week=7,
                              projected_stats=ProjectedStats(rec_yards=600 - i * 30, rec_tds=5 - i, receptions=50 - i * 3)))
    for i in range(5):
        players.append(Player(name=f"K{i}", team="TST", position=Position.K, bye_week=7,
                              projected_stats=ProjectedStats(field_goals=30 - i * 3, extra_points=35 - i * 3)))
    for i in range(5):
        players.append(Player(name=f"DEF{i}", team=f"D{i}", position=Position.DEF, bye_week=7,
                              projected_stats=ProjectedStats(sacks=40 - i * 5, def_interceptions=15 - i * 2, def_tds=3)))

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_draft.py::test_draft_respects_roster_limits -v`
Expected: Likely FAIL (current engine has no roster limits)

**Step 3: Modify `ai_pick()` in `src/draft.py`**

Add filtering in `ai_pick()` method after getting recommendations. Import `MAX_ROSTER` from `matchup_optimizer`:

At top of `src/draft.py`, add:
```python
from src.matchup_optimizer import MAX_ROSTER
```

Modify `ai_pick()` to filter recommendations:

```python
def ai_pick(self, team: Team) -> DraftPick:
    needs = team.needs()
    recommendations = get_draft_recommendations(
        self.league.available_players, needs, num_recommendations=10,
        config=self.config,
    )
    if not recommendations:
        available_sorted = sorted(
            self.league.available_players,
            key=lambda p: p.vbd_score,
            reverse=True,
        )
        recommendations = available_sorted[:10] if available_sorted else []

    recommendations = self._apply_round_bias(recommendations, team)

    # Filter out players that would violate roster limits
    filtered = []
    for p in recommendations:
        max_allowed = MAX_ROSTER.get(p.position)
        if max_allowed is not None and team.position_count(p.position) >= max_allowed:
            continue
        filtered.append(p)

    if not filtered:
        # Fallback: pick any available player not violating limits
        for p in sorted(self.league.available_players, key=lambda p: p.vbd_score, reverse=True):
            max_allowed = MAX_ROSTER.get(p.position)
            if max_allowed is None or team.position_count(p.position) < max_allowed:
                filtered.append(p)
                break

    if not filtered:
        raise ValueError("No players available to draft within roster limits")

    top = filtered[:3]
    weights = [3, 2, 1][:len(top)]
    pick_player = random.choices(top, weights=weights, k=1)[0]
    return self.make_pick(team, pick_player)
```

**Step 4: Run tests**

Run: `pytest tests/test_draft.py -v`
Expected: All pass including new roster limit test

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/draft.py tests/test_draft.py src/matchup_optimizer.py
git commit -m "feat: enforce roster composition rules (max 2 QB, 1 K, 1 DEF)"
```

---

### Task 6: Web API Route for Matchup Optimizer

**Files:**
- Modify: `web/app.py`

**Step 1: Add the matchup optimizer route**

Add to `web/app.py` in the Team Manager section, before `if __name__`:

```python
from src.matchup_optimizer import optimize_with_matchups, validate_roster_rules
from src.data_scraper import scrape_schedule, scrape_defense_rankings


@app.route("/api/team/matchup-optimize", methods=["POST"])
def api_team_matchup_optimize():
    """Run matchup-based lineup optimization."""
    data = request.get_json()
    league_file = data.get("league_file")
    team_name = data.get("team_name")
    week = int(data.get("week", 1))
    year = int(data.get("year", 2024))

    league = load_league(league_file)
    for t in league.teams:
        for e in t.roster:
            calculate_fantasy_points(e.player)

    team_obj = next((t for t in league.teams if t.name == team_name), None)
    if not team_obj:
        return jsonify({"error": "Team not found"}), 404

    # Scrape matchup data (cached)
    try:
        schedule = scrape_schedule(year)
        defense_rankings = scrape_defense_rankings(year)
    except Exception as e:
        return jsonify({"error": f"Failed to load matchup data: {str(e)}"}), 500

    result = optimize_with_matchups(team_obj, week, schedule, defense_rankings)
    return jsonify(result)
```

**Step 2: Verify no syntax errors**

Run: `python -c "import web.app; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add web/app.py
git commit -m "feat: add matchup optimizer API route"
```

---

### Task 7: Team Manager UI — Matchup Optimizer Panel

**Files:**
- Modify: `web/templates/team.html`

**Step 1: Read the current team.html**

Read `web/templates/team.html` to find where to insert the new panel.

**Step 2: Add Matchup Optimizer panel**

Add after the waiver recommendations section, before `{% endblock %}`:

```html
<!-- Matchup Optimizer -->
<div id="matchup-section" class="card hidden" style="margin-top: 1rem;">
    <h3>Matchup Lineup Optimizer</h3>
    <p class="text-secondary">Optimize your starting lineup based on weekly matchups.</p>
    <div style="display: flex; gap: 1rem; align-items: center; margin-bottom: 1rem;">
        <label>Week:
            <select id="matchup-week" class="search-input" style="width: auto; display: inline-block; margin-left: 0.5rem;">
                {% for w in range(1, 19) %}
                <option value="{{ w }}">Week {{ w }}</option>
                {% endfor %}
            </select>
        </label>
        <label>Year:
            <input type="number" id="matchup-year" class="search-input" value="2024"
                   style="width: 80px; display: inline-block; margin-left: 0.5rem;">
        </label>
        <button class="btn-primary" onclick="runMatchupOptimizer()">Optimize for Matchups</button>
    </div>
    <div id="matchup-status" class="text-secondary"></div>
    <div id="roster-violations"></div>
    <div id="matchup-results"></div>
    <div id="matchup-alternatives" style="margin-top: 1rem;"></div>
</div>
```

**Step 3: Add JavaScript functions**

Add to the `<script>` block:

```javascript
function runMatchupOptimizer() {
    const leagueFile = document.getElementById('league-select').value;
    const teamName = document.getElementById('team-select').value;
    const week = document.getElementById('matchup-week').value;
    const year = document.getElementById('matchup-year').value;

    document.getElementById('matchup-status').textContent = 'Analyzing matchups...';
    document.getElementById('matchup-results').innerHTML = '<div class="loading-spinner"></div>';

    postJSON('/api/team/matchup-optimize', {
        league_file: leagueFile, team_name: teamName,
        week: parseInt(week), year: parseInt(year),
    }).then(data => {
        document.getElementById('matchup-status').textContent = '';
        if (data.error) {
            document.getElementById('matchup-results').innerHTML =
                `<p style="color: #e74c3c;">${data.error}</p>`;
            return;
        }
        renderMatchupResults(data);
    }).catch(err => {
        document.getElementById('matchup-status').textContent = '';
        document.getElementById('matchup-results').innerHTML =
            '<p style="color: #e74c3c;">Failed to run optimizer. Check console.</p>';
        console.error(err);
    });
}

function renderMatchupResults(data) {
    // Roster violations
    const violDiv = document.getElementById('roster-violations');
    if (data.roster_violations && data.roster_violations.length > 0) {
        violDiv.innerHTML = data.roster_violations.map(v =>
            `<p style="color: #e74c3c; font-weight: bold;">⚠ ${v}</p>`
        ).join('');
    } else {
        violDiv.innerHTML = '';
    }

    // Recommended lineup
    const rec = data.recommended;
    if (!rec) {
        document.getElementById('matchup-results').innerHTML =
            '<p class="text-secondary">No lineup recommendations available.</p>';
        return;
    }

    let html = `<h4>Recommended Lineup — Week ${data.week}</h4>`;
    html += `<div style="display: flex; gap: 2rem; flex-wrap: wrap; margin-bottom: 1rem;">
        <div class="card" style="padding: 0.75rem;">
            <strong>Expected:</strong> ${rec.monte_carlo.mean} pts
        </div>
        <div class="card" style="padding: 0.75rem;">
            <strong>Floor:</strong> ${rec.monte_carlo.floor} pts
        </div>
        <div class="card" style="padding: 0.75rem;">
            <strong>Ceiling:</strong> ${rec.monte_carlo.ceiling} pts
        </div>
        <div class="card" style="padding: 0.75rem;">
            <strong>Consistency:</strong> ${rec.monte_carlo.consistency}%
        </div>
    </div>`;

    html += renderMatchupTable(rec.players);
    document.getElementById('matchup-results').innerHTML = html;

    // Alternatives
    const altDiv = document.getElementById('matchup-alternatives');
    if (data.alternatives && data.alternatives.length > 0) {
        let altHtml = '<h4>Alternative Lineups</h4>';
        data.alternatives.forEach((alt, i) => {
            altHtml += `<details style="margin-bottom: 0.5rem;">
                <summary style="cursor: pointer; color: var(--text-primary);">
                    Option ${i + 2}: ${alt.total_points} adj pts |
                    Expected ${alt.monte_carlo.mean} | Floor ${alt.monte_carlo.floor} | Ceiling ${alt.monte_carlo.ceiling}
                </summary>
                <div style="margin-top: 0.5rem;">${renderMatchupTable(alt.players)}</div>
            </details>`;
        });
        altDiv.innerHTML = altHtml;
    } else {
        altDiv.innerHTML = '';
    }
}

function renderMatchupTable(players) {
    let html = '<table class="data-table"><thead><tr>';
    html += '<th>Slot</th><th>Pos</th><th>Player</th><th>Opponent</th>';
    html += '<th>Base Pts</th><th>Adj Pts</th><th>Matchup</th>';
    html += '</tr></thead><tbody>';
    players.forEach(p => {
        const gradeColor = p.matchup_grade === 'favorable' ? '#2ecc71' :
                          p.matchup_grade === 'tough' ? '#e74c3c' : '#f1c40f';
        html += `<tr>
            <td>${p.slot}</td>
            <td><span class="pos-badge pos-${p.position.toLowerCase()}">${p.position}</span></td>
            <td>${p.name}</td>
            <td>${p.opponent}</td>
            <td>${p.base_pts}</td>
            <td><strong>${p.adjusted_pts}</strong></td>
            <td style="color: ${gradeColor}; font-weight: bold;">${p.matchup_grade.toUpperCase()}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    return html;
}
```

**Step 4: Make the matchup section visible when a team is loaded**

In the existing `loadTeam()` or `renderRoster()` function, add:

```javascript
document.getElementById('matchup-section').classList.remove('hidden');
```

**Step 5: Commit**

```bash
git add web/templates/team.html
git commit -m "feat: add matchup optimizer UI panel to team manager"
```

---

### Task 8: Final Verification and Push

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass (54 original + ~8 new = ~62)

**Step 2: Verify app imports cleanly**

Run: `python -c "import web.app; print('OK')"`
Expected: `OK`

**Step 3: Start app and smoke test**

Run: `python web/app.py`
Navigate to `/team`, load a saved league, verify:
- Matchup Optimizer panel appears
- Week/year inputs work
- "Optimize for Matchups" button triggers analysis
- Recommended lineup table renders with color-coded matchup grades
- Monte Carlo stats (expected, floor, ceiling, consistency) display
- Alternative lineups show in collapsible sections

**Step 4: Push**

```bash
git push origin master
```
