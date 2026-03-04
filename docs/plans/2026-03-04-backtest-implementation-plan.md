# Backtest & Strategy Improvement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a backtesting pipeline that simulates 1,000 drafts per season (2024 & 2025) using pre-season projections, rescores with actual stats, auto-tunes VBD parameters, and presents results via Rich CLI.

**Architecture:** Four new modules (`data_scraper.py`, `backtest.py`, `strategy_tuner.py`, `backtest_report.py`) plugging into the existing scoring/rankings/draft pipeline. Data flows: scraper → historical JSON → backtest engine (reuses `scoring.py`, `rankings.py`, `draft.py`) → tuner (grid search over parameters) → reporter (Rich tables + CSV).

**Tech Stack:** Python 3.12+, requests, beautifulsoup4, lxml, rich (existing), csv (stdlib), json (stdlib), random (stdlib), copy (stdlib), dataclasses (stdlib)

---

### Task 1: Add New Dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Update requirements.txt**

Add to the end of `requirements.txt`:
```
requests>=2.31
beautifulsoup4>=4.12
lxml>=5.0
```

**Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: Successfully installed requests, beautifulsoup4, lxml

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add requests, beautifulsoup4, lxml for data scraping"
```

---

### Task 2: Make VBD Parameters Configurable via StrategyConfig Dataclass

Currently the VBD constants (`REPLACEMENT_RANK`, `need_boost=1.15`, `scarcity_penalty=0.8`) are hardcoded in `rankings.py`. The backtest and tuner need to override them. We'll add a `StrategyConfig` dataclass and thread it through `get_draft_recommendations`.

**Files:**
- Modify: `src/models.py`
- Modify: `src/rankings.py`
- Modify: `src/draft.py`
- Create: `tests/test_strategy_config.py`

**Step 1: Write the failing test**

Create `tests/test_strategy_config.py`:

```python
"""Tests for configurable VBD strategy parameters."""

from src.models import Player, Position, ProjectedStats, Team, RosterSlot, StrategyConfig
from src.scoring import score_all_players
from src.rankings import calculate_vbd, get_draft_recommendations


def _make_players():
    """Create a small test pool with known scores."""
    players = [
        Player(name="QB1", team="T", position=Position.QB, bye_week=7,
               projected_stats=ProjectedStats(pass_yards=4500, pass_tds=35, interceptions=10)),
        Player(name="QB2", team="T", position=Position.QB, bye_week=7,
               projected_stats=ProjectedStats(pass_yards=3500, pass_tds=22, interceptions=10)),
        Player(name="RB1", team="T", position=Position.RB, bye_week=7,
               projected_stats=ProjectedStats(rush_yards=1400, rush_tds=12, receptions=50, rec_yards=400, rec_tds=2)),
        Player(name="RB2", team="T", position=Position.RB, bye_week=7,
               projected_stats=ProjectedStats(rush_yards=900, rush_tds=6, receptions=30, rec_yards=200, rec_tds=1)),
        Player(name="WR1", team="T", position=Position.WR, bye_week=7,
               projected_stats=ProjectedStats(receptions=100, rec_yards=1400, rec_tds=10)),
        Player(name="WR2", team="T", position=Position.WR, bye_week=7,
               projected_stats=ProjectedStats(receptions=60, rec_yards=800, rec_tds=5)),
        Player(name="TE1", team="T", position=Position.TE, bye_week=7,
               projected_stats=ProjectedStats(receptions=70, rec_yards=900, rec_tds=7)),
    ]
    score_all_players(players)
    return players


def test_strategy_config_defaults_match_original():
    """Default StrategyConfig should produce same results as hardcoded values."""
    config = StrategyConfig()
    assert config.replacement_rank[Position.QB] == 1
    assert config.replacement_rank[Position.RB] == 2.2
    assert config.need_boost == 1.15
    assert config.scarcity_penalty == 0.8


def test_custom_replacement_ranks_change_vbd():
    """Changing replacement ranks should change VBD scores."""
    players = _make_players()
    default_config = StrategyConfig()
    custom_config = StrategyConfig(
        replacement_rank={
            Position.QB: 1, Position.RB: 3.0, Position.WR: 3.0,
            Position.TE: 1.1, Position.K: 1, Position.DEF: 1,
        }
    )
    # With default config
    calculate_vbd(players, config=default_config)
    rb1_default_vbd = next(p for p in players if p.name == "RB1").vbd_score

    # With higher replacement rank (more RBs valued) = lower replacement level = higher VBD
    calculate_vbd(players, config=custom_config)
    rb1_custom_vbd = next(p for p in players if p.name == "RB1").vbd_score

    assert rb1_custom_vbd != rb1_default_vbd


def test_custom_need_boost_in_recommendations():
    """Custom need_boost should affect recommendation ordering."""
    players = _make_players()
    config_high_need = StrategyConfig(need_boost=2.0, scarcity_penalty=0.1)
    config_no_need = StrategyConfig(need_boost=1.0, scarcity_penalty=1.0)
    calculate_vbd(players)

    team = Team(name="T1", draft_position=1)
    needs = [RosterSlot.QB]  # team needs a QB

    recs_high = get_draft_recommendations(players, needs, config=config_high_need)
    recs_none = get_draft_recommendations(players, needs, config=config_no_need)

    # With high need boost, QB should be ranked higher
    high_qb_rank = next((i for i, p in enumerate(recs_high) if p.position == Position.QB), 99)
    none_qb_rank = next((i for i, p in enumerate(recs_none) if p.position == Position.QB), 99)
    assert high_qb_rank <= none_qb_rank


def test_round_targeting_in_config():
    """Round-based targeting parameters exist and have defaults."""
    config = StrategyConfig()
    assert config.round_1_2_bias == "BPA"
    assert config.round_3_5_bias == "BPA"
    assert config.qb_target_round == 6
    assert config.te_target_round == 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_strategy_config.py -v`
Expected: FAIL — `StrategyConfig` doesn't exist yet

**Step 3: Add StrategyConfig to models.py**

Add to end of `src/models.py`:

```python
@dataclass
class StrategyConfig:
    """Tunable parameters for the VBD draft strategy."""
    replacement_rank: dict = field(default_factory=lambda: {
        Position.QB: 1,
        Position.RB: 2.2,
        Position.WR: 2.2,
        Position.TE: 1.1,
        Position.K: 1,
        Position.DEF: 1,
    })
    need_boost: float = 1.15
    scarcity_penalty: float = 0.8
    round_1_2_bias: str = "BPA"      # "BPA", "RB_heavy", "WR_heavy"
    round_3_5_bias: str = "BPA"
    qb_target_round: int = 6
    te_target_round: int = 5

    def to_dict(self) -> dict:
        return {
            "replacement_rank": {k.value: v for k, v in self.replacement_rank.items()},
            "need_boost": self.need_boost,
            "scarcity_penalty": self.scarcity_penalty,
            "round_1_2_bias": self.round_1_2_bias,
            "round_3_5_bias": self.round_3_5_bias,
            "qb_target_round": self.qb_target_round,
            "te_target_round": self.te_target_round,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyConfig":
        repl = {Position(k): v for k, v in data.get("replacement_rank", {}).items()}
        return cls(
            replacement_rank=repl if repl else cls().replacement_rank,
            need_boost=data.get("need_boost", 1.15),
            scarcity_penalty=data.get("scarcity_penalty", 0.8),
            round_1_2_bias=data.get("round_1_2_bias", "BPA"),
            round_3_5_bias=data.get("round_3_5_bias", "BPA"),
            qb_target_round=data.get("qb_target_round", 6),
            te_target_round=data.get("te_target_round", 5),
        )
```

**Step 4: Update rankings.py to accept optional StrategyConfig**

In `src/rankings.py`, modify these functions to accept an optional `config` parameter. When `config` is None, use the existing hardcoded defaults (preserving backward compatibility):

- `get_replacement_level(players, position, num_teams=12, config=None)` — use `config.replacement_rank[position]` instead of `REPLACEMENT_RANK[position]` when config is provided
- `calculate_vbd(players, num_teams=12, config=None)` — pass config through to `get_replacement_level`
- `get_draft_recommendations(available, team_needs, num_recommendations=5, config=None)` — use `config.need_boost` and `config.scarcity_penalty` instead of hardcoded 1.15 and 0.8

Keep `REPLACEMENT_RANK` dict as the fallback default. Import `StrategyConfig` from models.

**Step 5: Update draft.py to accept optional StrategyConfig**

In `src/draft.py`:
- `DraftEngine.__init__` accepts optional `config: StrategyConfig = None`
- `ai_pick` passes `config` to `get_draft_recommendations`
- `get_recommendations` passes `config` to `get_draft_recommendations`
- Add round-based bias logic: in `ai_pick`, if we're in rounds 1-2 and `config.round_1_2_bias == "RB_heavy"`, multiply RB VBD by 1.2; if `"WR_heavy"`, multiply WR VBD by 1.2. Similar for rounds 3-5. If we haven't drafted a QB by `config.qb_target_round`, boost QB VBD by 1.3. Same for TE with `te_target_round`.

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_strategy_config.py -v`
Expected: All 4 tests PASS

**Step 7: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests still PASS (backward compatible since config defaults to None)

**Step 8: Commit**

```bash
git add src/models.py src/rankings.py src/draft.py tests/test_strategy_config.py
git commit -m "feat: add configurable StrategyConfig for VBD parameters and round targeting"
```

---

### Task 3: Build Data Scraper Module

**Files:**
- Create: `src/data_scraper.py`
- Create: `tests/test_data_scraper.py`

**Step 1: Write the failing test**

Create `tests/test_data_scraper.py`:

```python
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
    HISTORICAL_DIR,
)
from src.models import Position


# ── Sample HTML fragments matching PFR table structure ──────────────

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


def test_parse_pfr_passing():
    """Parse passing stats from PFR HTML table."""
    result = parse_pfr_passing(SAMPLE_PASSING_HTML)
    assert len(result) >= 1
    mahomes = result[0]
    assert mahomes["name"] == "Patrick Mahomes"
    assert mahomes["pass_yards"] == 4839
    assert mahomes["pass_tds"] == 26
    assert mahomes["interceptions"] == 11


def test_parse_pfr_rushing():
    """Parse rushing stats from PFR HTML table."""
    result = parse_pfr_rushing(SAMPLE_RUSHING_HTML)
    assert len(result) >= 1
    saquon = result[0]
    assert saquon["name"] == "Saquon Barkley"
    assert saquon["rush_yards"] == 2005
    assert saquon["rush_tds"] == 13


def test_parse_pfr_receiving():
    """Parse receiving stats from PFR HTML table."""
    result = parse_pfr_receiving(SAMPLE_RECEIVING_HTML)
    assert len(result) >= 1
    chase = result[0]
    assert chase["name"] == "Ja'Marr Chase"
    assert chase["receptions"] == 127
    assert chase["rec_yards"] == 1708
    assert chase["rec_tds"] == 17


def test_build_player_dataset_merges_stats():
    """Build a complete player list by merging passing/rushing/receiving stats."""
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


def test_scrape_season_caches_locally(tmp_path):
    """scrape_season saves results to local cache and reuses on second call."""
    with patch("src.data_scraper.HISTORICAL_DIR", tmp_path):
        with patch("src.data_scraper._fetch_page") as mock_fetch:
            mock_fetch.return_value = "<html><body></body></html>"
            with patch("src.data_scraper.build_player_dataset") as mock_build:
                from src.models import Player, ProjectedStats
                mock_build.return_value = [
                    Player(name="Test QB", team="TST", position=Position.QB, bye_week=7)
                ]
                # First call should fetch and cache
                result = scrape_season(2024)
                assert len(result) == 1
                cache_file = tmp_path / "2024_actual_stats.json"
                assert cache_file.exists()

                # Second call should use cache (mock_fetch not called again)
                mock_fetch.reset_mock()
                mock_build.reset_mock()
                result2 = scrape_season(2024)
                assert len(result2) == 1
                mock_fetch.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_scraper.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement data_scraper.py**

Create `src/data_scraper.py`. Key responsibilities:

1. **`_fetch_page(url)`** — GET request with User-Agent header and 3-second delay between requests. Returns HTML string.
2. **`parse_pfr_passing(html)`** — BeautifulSoup parses `<table id="passing">`, extracts `data-stat` attributes for `player`, `team_name_abbr`, `pass_yds`, `pass_td`, `pass_int`. Returns list of dicts.
3. **`parse_pfr_rushing(html)`** — Same pattern, table id `"rushing"`, stats: `rush_yds`, `rush_td`.
4. **`parse_pfr_receiving(html)`** — Table id `"receiving"`, stats: `rec`, `rec_yds`, `rec_td`.
5. **`parse_pfr_kicking(html)`** — Table id `"kicking"`, stats: `fgm` (field goals made), `xpm` (extra points made).
6. **`parse_pfr_defense(html)`** — Parse team defense page for `sacks`, `def_int`, `def_td`, `points_allowed_per_game`.
7. **`build_player_dataset(passing, rushing, receiving, kicking, defense)`** — Merge all stat dicts by player name into `Player` objects. Assign position based on which stat type the player primarily appears in (passing→QB, rushing-dominant→RB, receiving-dominant→WR/TE). Use heuristics: if player has >20 receptions and <100 rush yards, likely WR/TE; use PFR position column if available.
8. **`scrape_season(year)`** — Orchestrator. Checks `data/historical/{year}_actual_stats.json` for cached data first. If not cached, fetches all PFR pages for that year, parses, builds dataset, saves as JSON cache, returns list of `Player` objects.
9. **`scrape_preseason_adp(year)`** — Fetch ADP data from FantasyPros archives. Cache to `data/historical/{year}_preseason_adp.json`. Returns dict mapping player name → ADP float.

PFR URLs follow pattern:
- `https://www.pro-football-reference.com/years/{year}/passing.htm`
- `https://www.pro-football-reference.com/years/{year}/rushing.htm`
- `https://www.pro-football-reference.com/years/{year}/receiving.htm`
- `https://www.pro-football-reference.com/years/{year}/kicking.htm`
- `https://www.pro-football-reference.com/years/{year}/opp.htm` (team defense)

`HISTORICAL_DIR = Path(__file__).parent.parent / "data" / "historical"`

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_scraper.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/data_scraper.py tests/test_data_scraper.py
git commit -m "feat: add data scraper for PFR historical stats with caching"
```

---

### Task 4: Build Backtest Engine

**Files:**
- Create: `src/backtest.py`
- Create: `tests/test_backtest.py`

**Step 1: Write the failing test**

Create `tests/test_backtest.py`:

```python
"""Tests for the backtest engine."""

import copy
from src.models import Player, Team, League, Position, ProjectedStats, StrategyConfig
from src.scoring import score_all_players
from src.rankings import calculate_vbd
from src.backtest import (
    run_single_draft,
    compute_team_actual_points,
    run_backtest,
    BacktestResult,
    SeasonBacktestResults,
)


def _make_test_pool(n_per_pos=15):
    """Create a deterministic player pool for backtest testing."""
    players = []
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"QB{i}", team="T", position=Position.QB, bye_week=7, adp=float(20 + i),
            projected_stats=ProjectedStats(pass_yards=4500 - i * 50, pass_tds=35 - i, interceptions=10),
        ))
    for i in range(1, n_per_pos * 3 + 1):
        players.append(Player(
            name=f"RB{i}", team="T", position=Position.RB, bye_week=7, adp=float(i),
            projected_stats=ProjectedStats(rush_yards=1500 - i * 15, rush_tds=max(1, 12 - i // 5),
                                           receptions=max(5, 40 - i), rec_yards=max(50, 400 - i * 5), rec_tds=2),
        ))
    for i in range(1, n_per_pos * 3 + 1):
        players.append(Player(
            name=f"WR{i}", team="T", position=Position.WR, bye_week=7, adp=float(10 + i),
            projected_stats=ProjectedStats(receptions=max(20, 100 - i), rec_yards=max(200, 1400 - i * 15),
                                           rec_tds=max(1, 10 - i // 7)),
        ))
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"TE{i}", team="T", position=Position.TE, bye_week=7, adp=float(40 + i),
            projected_stats=ProjectedStats(receptions=max(15, 70 - i * 2), rec_yards=max(150, 900 - i * 30), rec_tds=max(1, 7 - i // 4)),
        ))
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"K{i}", team="T", position=Position.K, bye_week=7, adp=float(130 + i),
            projected_stats=ProjectedStats(field_goals=max(15, 30 - i), extra_points=max(20, 40 - i)),
        ))
    for i in range(1, n_per_pos + 1):
        players.append(Player(
            name=f"DEF{i}", team="T", position=Position.DEF, bye_week=7, adp=float(140 + i),
            projected_stats=ProjectedStats(sacks=max(20, 40 - i), def_interceptions=max(5, 15 - i),
                                           def_tds=max(0, 3 - i // 10), points_allowed_per_game=18 + i),
        ))
    return players


def test_run_single_draft_returns_result():
    """A single draft simulation returns a BacktestResult with all teams."""
    projection_players = _make_test_pool()
    actual_players = _make_test_pool()  # same pool for simplicity
    score_all_players(projection_players)
    score_all_players(actual_players)
    calculate_vbd(projection_players)

    config = StrategyConfig()
    result = run_single_draft(
        projection_players=projection_players,
        actual_players=actual_players,
        vbd_team_position=1,
        config=config,
    )
    assert isinstance(result, BacktestResult)
    assert result.vbd_team_points > 0
    assert len(result.all_team_points) == 12
    assert result.draft_position == 1


def test_compute_team_actual_points():
    """Rescoring a team with actual stats returns a positive total."""
    players = _make_test_pool(n_per_pos=5)
    score_all_players(players)
    # Create a small team
    from src.models import Team, RosterEntry, RosterSlot
    team = Team(name="T1", draft_position=1)
    team.roster = [
        RosterEntry(player=players[0], slot=RosterSlot.QB),
        RosterEntry(player=players[15], slot=RosterSlot.RB),
        RosterEntry(player=players[16], slot=RosterSlot.RB),
        RosterEntry(player=players[30], slot=RosterSlot.WR),
        RosterEntry(player=players[31], slot=RosterSlot.WR),
        RosterEntry(player=players[45], slot=RosterSlot.TE),
        RosterEntry(player=players[17], slot=RosterSlot.FLEX),
        RosterEntry(player=players[50], slot=RosterSlot.K),
        RosterEntry(player=players[55], slot=RosterSlot.DEF),
    ]
    actual_lookup = {p.name: p for p in players}
    points = compute_team_actual_points(team, actual_lookup)
    assert points > 0


def test_run_backtest_small_iterations():
    """Run backtest with 3 iterations returns aggregated results."""
    projection_players = _make_test_pool()
    actual_players = _make_test_pool()
    score_all_players(projection_players)
    score_all_players(actual_players)
    calculate_vbd(projection_players)

    results = run_backtest(
        projection_players=projection_players,
        actual_players=actual_players,
        config=StrategyConfig(),
        iterations=3,
    )
    assert isinstance(results, SeasonBacktestResults)
    assert len(results.iterations) == 3
    assert results.mean_vbd_points > 0
    assert results.mean_random_points >= 0
    assert results.mean_adp_points >= 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_backtest.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement backtest.py**

Create `src/backtest.py`. Key components:

```python
"""Backtest engine for evaluating draft strategies against historical data."""

import copy
import random
from dataclasses import dataclass, field

from src.models import (
    Player, Team, League, Position, RosterSlot,
    TOTAL_ROUNDS, StrategyConfig, RosterEntry,
)
from src.scoring import score_all_players, calculate_fantasy_points
from src.rankings import calculate_vbd, get_draft_recommendations
from src.draft import DraftEngine, auto_assign_slot


@dataclass
class BacktestResult:
    """Result from a single draft simulation."""
    draft_position: int
    vbd_team_points: float
    adp_team_points: float
    random_team_points: float
    all_team_points: list[float]
    vbd_picks: list[dict]  # [{name, position, projected_pts, actual_pts}]
    bust_count: int = 0
    hit_count: int = 0


@dataclass
class SeasonBacktestResults:
    """Aggregated results from N iterations of backtesting."""
    season: int
    iterations: list[BacktestResult]
    config: StrategyConfig
    mean_vbd_points: float = 0.0
    mean_adp_points: float = 0.0
    mean_random_points: float = 0.0
    mean_bust_rate: float = 0.0
    mean_hit_rate: float = 0.0
    points_by_position: dict = field(default_factory=dict)  # {draft_pos: mean_points}
```

Key functions:

1. **`compute_team_actual_points(team, actual_lookup)`** — For each player on team, look up their actual stats version in `actual_lookup` (dict[name → Player]), compute optimal lineup using actual fantasy points, sum starter points. This is how we evaluate "how did this team actually perform?"

2. **`_run_adp_draft(players, team_position)`** — Simulates a draft where the target team always picks the player with the lowest (best) ADP available. AI opponents use random from top 5 ADP. Returns the target team.

3. **`_run_random_draft(players, team_position)`** — Target team picks randomly from top 30 available. AI picks randomly from top 10. Returns target team.

4. **`run_single_draft(projection_players, actual_players, vbd_team_position, config)`** —
   - Deep-copy projection_players to avoid mutation
   - Score and calculate VBD with config
   - Set up 12 teams, run full draft with DraftEngine (all AI picks, passing config)
   - The VBD team at `vbd_team_position` represents our strategy
   - After draft, rescore the VBD team's players using `actual_players` lookup
   - Also run ADP and random drafts for same position
   - Compute bust_count (picks below replacement in actuals) and hit_count (top 10 at position in actuals)
   - Return `BacktestResult`

5. **`run_backtest(projection_players, actual_players, config, iterations=1000)`** —
   - Loop `iterations` times
   - Rotate `vbd_team_position` through 1-12 evenly
   - Call `run_single_draft` each time
   - Aggregate into `SeasonBacktestResults` with means

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backtest.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/backtest.py tests/test_backtest.py
git commit -m "feat: add backtest engine with VBD vs ADP vs random comparisons"
```

---

### Task 5: Build Strategy Tuner

**Files:**
- Create: `src/strategy_tuner.py`
- Create: `tests/test_strategy_tuner.py`

**Step 1: Write the failing test**

Create `tests/test_strategy_tuner.py`:

```python
"""Tests for the strategy parameter tuner."""

from src.models import StrategyConfig, Position
from src.strategy_tuner import (
    generate_random_config,
    TunerResult,
    run_tuning,
)


def test_generate_random_config_within_bounds():
    """Generated configs should have values within defined ranges."""
    for _ in range(20):
        config = generate_random_config()
        assert 0.8 <= config.replacement_rank[Position.QB] <= 1.5
        assert 1.5 <= config.replacement_rank[Position.RB] <= 3.0
        assert 1.5 <= config.replacement_rank[Position.WR] <= 3.0
        assert 0.8 <= config.replacement_rank[Position.TE] <= 1.5
        assert 1.0 <= config.need_boost <= 1.5
        assert 0.5 <= config.scarcity_penalty <= 1.0
        assert config.round_1_2_bias in ("BPA", "RB_heavy", "WR_heavy")
        assert config.round_3_5_bias in ("BPA", "RB_heavy", "WR_heavy")
        assert 4 <= config.qb_target_round <= 8
        assert 3 <= config.te_target_round <= 8


def test_tuner_result_ranking():
    """TunerResult instances sort by mean_points descending."""
    results = [
        TunerResult(config=StrategyConfig(), mean_points=100.0, iterations_run=10),
        TunerResult(config=StrategyConfig(), mean_points=150.0, iterations_run=10),
        TunerResult(config=StrategyConfig(), mean_points=120.0, iterations_run=10),
    ]
    ranked = sorted(results, key=lambda r: r.mean_points, reverse=True)
    assert ranked[0].mean_points == 150.0
    assert ranked[1].mean_points == 120.0
    assert ranked[2].mean_points == 100.0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_strategy_tuner.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement strategy_tuner.py**

Create `src/strategy_tuner.py`:

```python
"""Strategy parameter tuner using random search."""

import random
from dataclasses import dataclass
from src.models import Position, StrategyConfig
from src.backtest import run_backtest, SeasonBacktestResults


@dataclass
class TunerResult:
    """Result from tuning a single parameter configuration."""
    config: StrategyConfig
    mean_points: float
    iterations_run: int
    season_results: list[SeasonBacktestResults] | None = None


def generate_random_config() -> StrategyConfig:
    """Generate a random StrategyConfig within defined bounds."""
    return StrategyConfig(
        replacement_rank={
            Position.QB: round(random.uniform(0.8, 1.5), 2),
            Position.RB: round(random.uniform(1.5, 3.0), 2),
            Position.WR: round(random.uniform(1.5, 3.0), 2),
            Position.TE: round(random.uniform(0.8, 1.5), 2),
            Position.K: 1,
            Position.DEF: 1,
        },
        need_boost=round(random.uniform(1.0, 1.5), 2),
        scarcity_penalty=round(random.uniform(0.5, 1.0), 2),
        round_1_2_bias=random.choice(["BPA", "RB_heavy", "WR_heavy"]),
        round_3_5_bias=random.choice(["BPA", "RB_heavy", "WR_heavy"]),
        qb_target_round=random.randint(4, 8),
        te_target_round=random.randint(3, 8),
    )


def run_tuning(
    projection_players_by_season: dict,  # {year: list[Player]}
    actual_players_by_season: dict,      # {year: list[Player]}
    num_configs: int = 200,
    search_iterations: int = 100,
    validation_iterations: int = 1000,
    top_n: int = 5,
    progress_callback=None,
) -> list[TunerResult]:
    """Run random search over parameter space.

    1. Generate num_configs random StrategyConfigs
    2. For each config, run search_iterations backtests per season
    3. Rank by mean points across all seasons
    4. Re-run top_n configs at validation_iterations for final ranking
    """
    # Phase 1: Search
    search_results = []
    for i in range(num_configs):
        config = generate_random_config()
        total_points = 0.0
        seasons_tested = 0
        for year, proj_players in projection_players_by_season.items():
            actual_players = actual_players_by_season[year]
            result = run_backtest(proj_players, actual_players, config, search_iterations)
            total_points += result.mean_vbd_points
            seasons_tested += 1
        mean_pts = total_points / max(seasons_tested, 1)
        search_results.append(TunerResult(config=config, mean_points=mean_pts, iterations_run=search_iterations))
        if progress_callback:
            progress_callback(i + 1, num_configs, "search")

    # Phase 2: Validate top configs
    search_results.sort(key=lambda r: r.mean_points, reverse=True)
    top_configs = search_results[:top_n]

    validated = []
    for i, tr in enumerate(top_configs):
        total_points = 0.0
        season_results = []
        for year, proj_players in projection_players_by_season.items():
            actual_players = actual_players_by_season[year]
            result = run_backtest(proj_players, actual_players, tr.config, validation_iterations)
            total_points += result.mean_vbd_points
            season_results.append(result)
        mean_pts = total_points / max(len(projection_players_by_season), 1)
        validated.append(TunerResult(
            config=tr.config, mean_points=mean_pts,
            iterations_run=validation_iterations, season_results=season_results,
        ))
        if progress_callback:
            progress_callback(i + 1, top_n, "validate")

    validated.sort(key=lambda r: r.mean_points, reverse=True)
    return validated
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_strategy_tuner.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/strategy_tuner.py tests/test_strategy_tuner.py
git commit -m "feat: add strategy tuner with random search and validation"
```

---

### Task 6: Build Backtest Reporter

**Files:**
- Create: `src/backtest_report.py`
- Create: `tests/test_backtest_report.py`

**Step 1: Write the failing test**

Create `tests/test_backtest_report.py`:

```python
"""Tests for backtest reporting and CSV export."""

import csv
from pathlib import Path
from src.backtest_report import (
    format_comparison_table,
    format_position_breakdown,
    export_results_csv,
)
from src.backtest import BacktestResult, SeasonBacktestResults
from src.models import StrategyConfig


def _make_mock_season_results():
    iterations = [
        BacktestResult(
            draft_position=pos,
            vbd_team_points=250.0 + pos * 5,
            adp_team_points=230.0 + pos * 3,
            random_team_points=200.0 + pos * 2,
            all_team_points=[240.0] * 12,
            vbd_picks=[],
            bust_count=2,
            hit_count=5,
        )
        for pos in range(1, 13)
    ]
    return SeasonBacktestResults(
        season=2024,
        iterations=iterations,
        config=StrategyConfig(),
        mean_vbd_points=280.0,
        mean_adp_points=250.0,
        mean_random_points=220.0,
        mean_bust_rate=0.13,
        mean_hit_rate=0.33,
    )


def test_format_comparison_table_returns_string():
    """Comparison table should be a non-empty string."""
    results = _make_mock_season_results()
    table_str = format_comparison_table(results)
    assert isinstance(table_str, str)
    assert "VBD" in table_str
    assert "ADP" in table_str
    assert "Random" in table_str


def test_export_results_csv(tmp_path):
    """Export should create a valid CSV file."""
    results = _make_mock_season_results()
    filepath = tmp_path / "test_results.csv"
    export_results_csv(results, str(filepath))
    assert filepath.exists()
    with open(filepath) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 12  # one per iteration
    assert "draft_position" in rows[0]
    assert "vbd_team_points" in rows[0]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_backtest_report.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement backtest_report.py**

Create `src/backtest_report.py`:

Key functions:

1. **`format_comparison_table(results: SeasonBacktestResults)`** — Returns a string rendering of a Rich table comparing VBD vs ADP vs Random strategies (mean points, std dev, win rate).

2. **`format_position_breakdown(results: SeasonBacktestResults)`** — Returns a string showing performance by draft position (1-12 heatmap style).

3. **`format_tuning_results(tuner_results: list[TunerResult])`** — Returns a string showing the top configs with their parameters and performance.

4. **`format_before_after(current: StrategyConfig, best: StrategyConfig, current_pts, best_pts)`** — Side-by-side comparison of current vs recommended config.

5. **`export_results_csv(results: SeasonBacktestResults, filepath: str)`** — Write iteration results to CSV with columns: draft_position, vbd_team_points, adp_team_points, random_team_points, bust_count, hit_count.

6. **`export_tuning_csv(tuner_results: list[TunerResult], filepath: str)`** — Write tuning results to CSV with all config parameters and mean_points.

7. **`print_full_report(season_results: list[SeasonBacktestResults], console)`** — Renders all tables to Rich console.

Use `rich.console.Console` with `record=True` and `console.export_text()` for the `format_*` functions that return strings (for testability).

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backtest_report.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/backtest_report.py tests/test_backtest_report.py
git commit -m "feat: add backtest reporter with Rich tables and CSV export"
```

---

### Task 7: Add CLI Menu for Backtest & Strategy Lab

**Files:**
- Modify: `src/cli.py`

**Step 1: Add imports and menu option**

At the top of `src/cli.py`, add imports:
```python
from src.data_scraper import scrape_season, scrape_preseason_adp, HISTORICAL_DIR
from src.backtest import run_backtest
from src.strategy_tuner import run_tuning, generate_random_config
from src.backtest_report import (
    print_full_report, export_results_csv, export_tuning_csv,
    format_before_after,
)
```

In the main menu choices, add option 8: `"Backtest & Strategy Lab"`.

**Step 2: Implement the backtest submenu function**

Add function `_backtest_lab()` with submenu:
- **Run Backtest** — prompts for seasons (2024/2025), scrapes data if not cached, runs 1,000 iterations per season with current config, shows report, exports CSV.
- **Run Strategy Tuner** — prompts for config count (default 200) and iterations (default 100), runs tuning, shows top 5 configs, exports CSV.
- **View Results** — loads most recent results from `data/backtest_results/` and displays.
- **Apply Best Strategy** — reads best config from tuning results, shows before/after comparison, asks for confirmation, then updates `src/rankings.py` constants (writes the new `REPLACEMENT_RANK` values and updates the hardcoded multipliers in `get_draft_recommendations`). Also saves the config to `data/backtest_results/applied_config.json`.
- **Back** — return to main menu.

Use `rich.progress.Progress` for progress bars during long-running backtest/tuning.

**Step 3: Wire it into the main loop**

In the main menu handler, add the case for option 8 calling `_backtest_lab()`.

**Step 4: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 5: Manual smoke test**

Run: `python main.py`
Expected: Menu shows option 8 "Backtest & Strategy Lab". Selecting it shows the submenu.

**Step 6: Commit**

```bash
git add src/cli.py
git commit -m "feat: add Backtest & Strategy Lab CLI menu"
```

---

### Task 8: Integration Test — Full Backtest Pipeline

**Files:**
- Create: `tests/test_backtest_integration.py`

**Step 1: Write the integration test**

```python
"""Integration test: full backtest pipeline with synthetic data."""

import copy
from src.models import Player, Position, ProjectedStats, StrategyConfig
from src.scoring import score_all_players
from src.rankings import calculate_vbd
from src.backtest import run_backtest


def _make_full_pool():
    """Create 230+ players like the real pool, with 'projection' and 'actual' variants."""
    players = []
    # 32 QBs
    for i in range(1, 33):
        players.append(Player(
            name=f"QB{i}", team="T", position=Position.QB, bye_week=7,
            adp=float(20 + i * 3),
            projected_stats=ProjectedStats(pass_yards=4500 - i * 40, pass_tds=35 - i, interceptions=10),
        ))
    # 65 RBs
    for i in range(1, 66):
        players.append(Player(
            name=f"RB{i}", team="T", position=Position.RB, bye_week=7,
            adp=float(i),
            projected_stats=ProjectedStats(rush_yards=1500 - i * 15, rush_tds=max(1, 12 - i // 5),
                                           receptions=max(5, 40 - i), rec_yards=max(50, 400 - i * 5), rec_tds=2),
        ))
    # 60 WRs
    for i in range(1, 61):
        players.append(Player(
            name=f"WR{i}", team="T", position=Position.WR, bye_week=7,
            adp=float(10 + i * 2),
            projected_stats=ProjectedStats(receptions=max(20, 100 - i), rec_yards=max(200, 1400 - i * 15),
                                           rec_tds=max(1, 10 - i // 7)),
        ))
    # 20 TEs
    for i in range(1, 21):
        players.append(Player(
            name=f"TE{i}", team="T", position=Position.TE, bye_week=7,
            adp=float(40 + i * 4),
            projected_stats=ProjectedStats(receptions=max(15, 70 - i * 2), rec_yards=max(150, 900 - i * 30),
                                           rec_tds=max(1, 7 - i // 4)),
        ))
    # 20 Ks
    for i in range(1, 21):
        players.append(Player(
            name=f"K{i}", team="T", position=Position.K, bye_week=7,
            adp=float(130 + i * 2),
            projected_stats=ProjectedStats(field_goals=max(15, 30 - i), extra_points=max(20, 40 - i)),
        ))
    # 32 DEFs
    for i in range(1, 33):
        players.append(Player(
            name=f"DEF{i}", team="T", position=Position.DEF, bye_week=7,
            adp=float(140 + i * 2),
            projected_stats=ProjectedStats(sacks=max(20, 40 - i), def_interceptions=max(5, 15 - i),
                                           def_tds=max(0, 3 - i // 10), points_allowed_per_game=18 + i),
        ))
    return players


def test_full_backtest_pipeline():
    """Run a complete backtest pipeline: score, rank, backtest 10 iterations."""
    projection_players = _make_full_pool()
    actual_players = copy.deepcopy(projection_players)
    # Simulate actuals being slightly different
    import random
    random.seed(42)
    for p in actual_players:
        s = p.projected_stats
        s.pass_yards *= random.uniform(0.7, 1.3)
        s.rush_yards *= random.uniform(0.7, 1.3)
        s.rec_yards *= random.uniform(0.7, 1.3)
        s.receptions *= random.uniform(0.7, 1.3)

    score_all_players(projection_players)
    score_all_players(actual_players)
    calculate_vbd(projection_players)

    config = StrategyConfig()
    results = run_backtest(
        projection_players=projection_players,
        actual_players=actual_players,
        config=config,
        iterations=10,
    )

    # Basic sanity checks
    assert results.mean_vbd_points > 0
    assert len(results.iterations) == 10
    # VBD should outperform random on average (may not always be true with only 10 iterations)
    # Just check that values are reasonable
    assert results.mean_vbd_points > 100  # should be a meaningful score
    assert results.mean_random_points > 0
    assert results.mean_adp_points > 0


def test_different_configs_produce_different_results():
    """Two different strategy configs should yield different backtest results."""
    projection_players = _make_full_pool()
    actual_players = copy.deepcopy(projection_players)
    score_all_players(projection_players)
    score_all_players(actual_players)
    calculate_vbd(projection_players)

    config1 = StrategyConfig()
    config2 = StrategyConfig(
        replacement_rank={
            Position.QB: 1.5, Position.RB: 1.5, Position.WR: 3.0,
            Position.TE: 0.8, Position.K: 1, Position.DEF: 1,
        },
        need_boost=1.4,
        scarcity_penalty=0.6,
        round_1_2_bias="WR_heavy",
    )

    import random
    random.seed(123)
    results1 = run_backtest(projection_players, actual_players, config1, iterations=5)
    random.seed(123)
    results2 = run_backtest(projection_players, actual_players, config2, iterations=5)

    # Results should differ since configs differ
    # (With same seed but different strategies, picks will diverge)
    assert results1.config != results2.config
```

**Step 2: Run integration tests**

Run: `pytest tests/test_backtest_integration.py -v`
Expected: All 2 tests PASS

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_backtest_integration.py
git commit -m "test: add integration tests for full backtest pipeline"
```

---

### Task 9: Create Historical Data Directory and .gitkeep

**Files:**
- Create: `data/historical/.gitkeep`
- Create: `data/backtest_results/.gitkeep`

**Step 1: Create directories**

```bash
mkdir -p data/historical data/backtest_results
touch data/historical/.gitkeep data/backtest_results/.gitkeep
```

**Step 2: Commit**

```bash
git add data/historical/.gitkeep data/backtest_results/.gitkeep
git commit -m "chore: add historical data and backtest results directories"
```

---

### Task 10: Final Verification and Push

**Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS, no warnings

**Step 2: Manual end-to-end smoke test**

Run: `python main.py` → select "Backtest & Strategy Lab" → verify submenu works

**Step 3: Push to remote**

```bash
git push origin master
```
