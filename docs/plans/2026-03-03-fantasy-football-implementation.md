# Fantasy Football Draft Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI fantasy football draft tool with VBD-based rankings, mock/live draft modes, and full team management with waiver recommendations.

**Architecture:** Modular Python package — data models, scoring engine, VBD rankings, draft engine, team manager, and Rich CLI. JSON for player data and persistence. No database.

**Tech Stack:** Python 3.10+, `rich` (terminal UI), `questionary` (interactive prompts), `dataclasses` (models), `json` (persistence)

---

### Task 1: Project Scaffolding & Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `main.py`
- Create: `data/` (directory)
- Create: `saves/` (directory)

**Step 1: Create requirements.txt**

```
rich>=13.0
questionary>=2.0
```

**Step 2: Create empty src package**

```python
# src/__init__.py
```

**Step 3: Create placeholder main.py**

```python
"""Fantasy Football Draft Tool & Team Manager."""


def main():
    print("Fantasy Football Draft Tool — starting...")


if __name__ == "__main__":
    main()
```

**Step 4: Create data/ and saves/ directories**

```bash
mkdir -p data saves
```

**Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 6: Verify main.py runs**

```bash
python main.py
```

Expected: prints "Fantasy Football Draft Tool — starting..."

**Step 7: Commit**

```bash
git init
git add .
git commit -m "feat: project scaffolding with dependencies"
```

---

### Task 2: Data Models

**Files:**
- Create: `src/models.py`

**Step 1: Build Player, Team, League dataclasses**

```python
"""Data models for fantasy football."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Position(Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"


# Roster slot types (includes FLEX and BENCH)
class RosterSlot(Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    FLEX = "FLEX"
    K = "K"
    DEF = "DEF"
    BENCH = "BENCH"


# Default roster configuration
ROSTER_SLOTS = {
    RosterSlot.QB: 1,
    RosterSlot.RB: 2,
    RosterSlot.WR: 2,
    RosterSlot.TE: 1,
    RosterSlot.FLEX: 1,
    RosterSlot.K: 1,
    RosterSlot.DEF: 1,
    RosterSlot.BENCH: 6,
}

FLEX_ELIGIBLE = {Position.RB, Position.WR, Position.TE}

TOTAL_ROUNDS = 15  # sum of all roster slots


@dataclass
class ProjectedStats:
    """Season-long projected stats for a player."""
    pass_yards: float = 0.0
    pass_tds: float = 0.0
    interceptions: float = 0.0
    rush_yards: float = 0.0
    rush_tds: float = 0.0
    receptions: float = 0.0
    rec_yards: float = 0.0
    rec_tds: float = 0.0
    field_goals: float = 0.0
    extra_points: float = 0.0
    # Defense stats
    sacks: float = 0.0
    def_interceptions: float = 0.0
    def_tds: float = 0.0
    points_allowed_per_game: float = 0.0

    def to_dict(self) -> dict:
        return {
            "pass_yards": self.pass_yards,
            "pass_tds": self.pass_tds,
            "interceptions": self.interceptions,
            "rush_yards": self.rush_yards,
            "rush_tds": self.rush_tds,
            "receptions": self.receptions,
            "rec_yards": self.rec_yards,
            "rec_tds": self.rec_tds,
            "field_goals": self.field_goals,
            "extra_points": self.extra_points,
            "sacks": self.sacks,
            "def_interceptions": self.def_interceptions,
            "def_tds": self.def_tds,
            "points_allowed_per_game": self.points_allowed_per_game,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectedStats":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Player:
    """An NFL player with projected stats."""
    name: str
    team: str
    position: Position
    bye_week: int
    projected_stats: ProjectedStats = field(default_factory=ProjectedStats)
    adp: float = 200.0  # average draft position
    fantasy_points: float = 0.0  # calculated by scoring engine
    vbd_score: float = 0.0  # calculated by rankings engine

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "team": self.team,
            "position": self.position.value,
            "bye_week": self.bye_week,
            "projected_stats": self.projected_stats.to_dict(),
            "adp": self.adp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        return cls(
            name=data["name"],
            team=data["team"],
            position=Position(data["position"]),
            bye_week=data["bye_week"],
            projected_stats=ProjectedStats.from_dict(data.get("projected_stats", {})),
            adp=data.get("adp", 200.0),
        )


@dataclass
class RosterEntry:
    """A player assigned to a roster slot."""
    player: Player
    slot: RosterSlot


@dataclass
class Team:
    """A fantasy team with roster."""
    name: str
    draft_position: int  # 1-12
    roster: list[RosterEntry] = field(default_factory=list)

    def players(self) -> list[Player]:
        return [entry.player for entry in self.roster]

    def starters(self) -> list[RosterEntry]:
        return [e for e in self.roster if e.slot != RosterSlot.BENCH]

    def bench(self) -> list[RosterEntry]:
        return [e for e in self.roster if e.slot == RosterSlot.BENCH]

    def position_count(self, pos: Position) -> int:
        return sum(1 for e in self.roster if e.player.position == pos)

    def starter_slots_filled(self) -> dict[RosterSlot, int]:
        counts: dict[RosterSlot, int] = {}
        for e in self.roster:
            if e.slot != RosterSlot.BENCH:
                counts[e.slot] = counts.get(e.slot, 0) + 1
        return counts

    def needs(self) -> list[RosterSlot]:
        """Return unfilled starter slots."""
        filled = self.starter_slots_filled()
        needed = []
        for slot, count in ROSTER_SLOTS.items():
            if slot == RosterSlot.BENCH:
                continue
            current = filled.get(slot, 0)
            for _ in range(count - current):
                needed.append(slot)
        return needed

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "draft_position": self.draft_position,
            "roster": [
                {"player_name": e.player.name, "slot": e.slot.value}
                for e in self.roster
            ],
        }


@dataclass
class DraftPick:
    """A single draft pick."""
    round_num: int
    pick_num: int  # overall pick (1-180)
    team: Team
    player: Player


@dataclass
class League:
    """A fantasy league with teams and draft history."""
    name: str
    teams: list[Team] = field(default_factory=list)
    draft_picks: list[DraftPick] = field(default_factory=list)
    available_players: list[Player] = field(default_factory=list)

    def drafted_player_names(self) -> set[str]:
        return {pick.player.name for pick in self.draft_picks}

    def free_agents(self) -> list[Player]:
        """Players not on any team roster."""
        rostered = set()
        for team in self.teams:
            for entry in team.roster:
                rostered.add(entry.player.name)
        return [p for p in self.available_players if p.name not in rostered]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "teams": [t.to_dict() for t in self.teams],
            "draft_picks": [
                {
                    "round_num": dp.round_num,
                    "pick_num": dp.pick_num,
                    "team_name": dp.team.name,
                    "player_name": dp.player.name,
                }
                for dp in self.draft_picks
            ],
        }
```

**Step 2: Verify models import cleanly**

```bash
python -c "from src.models import Player, Team, League, Position; print('Models OK')"
```

Expected: "Models OK"

**Step 3: Commit**

```bash
git add src/models.py
git commit -m "feat: add data models (Player, Team, League, DraftPick)"
```

---

### Task 3: Player Database

**Files:**
- Create: `data/players.json`

**Step 1: Build the full NFL player database**

Create `data/players.json` with current NFL players. Include at minimum:
- Top 32 QBs (all starters + key backups)
- Top 60 RBs
- Top 60 WRs
- Top 24 TEs
- Top 20 Kickers
- All 32 NFL Defenses

Each player needs: name, team, position, bye_week, projected_stats (realistic 2025 season projections), adp.

Use realistic projected stats based on recent NFL seasons. Projected stats must match each player's actual role — e.g., Patrick Mahomes should have ~4800 pass yards, ~35 pass TDs; a backup RB should have fewer rush yards than a starter.

Bye weeks should reflect actual 2025 NFL schedule (use 2024 bye weeks as reasonable estimates if 2025 not finalized).

**Important:** This is a large file (~230 players). Take care to make projections reasonable and internally consistent.

**Step 2: Verify JSON is valid and loadable**

```bash
python -c "
import json
from src.models import Player
with open('data/players.json') as f:
    data = json.load(f)
players = [Player.from_dict(p) for p in data['players']]
print(f'Loaded {len(players)} players')
positions = {}
for p in players:
    positions[p.position.value] = positions.get(p.position.value, 0) + 1
for pos, count in sorted(positions.items()):
    print(f'  {pos}: {count}')
"
```

Expected: Loads all players with correct position counts.

**Step 3: Commit**

```bash
git add data/players.json
git commit -m "feat: add NFL player database with projected stats"
```

---

### Task 4: Scoring Engine

**Files:**
- Create: `src/scoring.py`
- Create: `tests/test_scoring.py`

**Step 1: Write failing tests for scoring**

```python
"""Tests for the scoring engine."""

from src.models import Player, Position, ProjectedStats
from src.scoring import calculate_fantasy_points


def test_qb_scoring():
    """Verify QB scoring: pass yards/25 + 6*pass_td - 2*int + rush yards/10 + 6*rush_td."""
    stats = ProjectedStats(pass_yards=4000, pass_tds=30, interceptions=10, rush_yards=200, rush_tds=2)
    player = Player(name="Test QB", team="TST", position=Position.QB, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    # 4000/25 + 30*6 - 10*2 + 200/10 + 2*6 = 160 + 180 - 20 + 20 + 12 = 352
    assert pts == 352.0


def test_rb_scoring_half_ppr():
    """Verify RB scoring with half PPR: rush yards/10 + 6*rush_td + rec_yards/10 + 6*rec_td + 0.5*rec."""
    stats = ProjectedStats(rush_yards=1200, rush_tds=10, receptions=40, rec_yards=300, rec_tds=2)
    player = Player(name="Test RB", team="TST", position=Position.RB, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    # 1200/10 + 10*6 + 300/10 + 2*6 + 40*0.5 = 120 + 60 + 30 + 12 + 20 = 242
    assert pts == 242.0


def test_wr_scoring_half_ppr():
    """Verify WR scoring with half PPR."""
    stats = ProjectedStats(receptions=100, rec_yards=1400, rec_tds=10, rush_yards=50, rush_tds=0)
    player = Player(name="Test WR", team="TST", position=Position.WR, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    # 100*0.5 + 1400/10 + 10*6 + 50/10 + 0 = 50 + 140 + 60 + 5 = 255
    assert pts == 255.0


def test_kicker_scoring():
    """Verify kicker scoring: 3*FG + 1*XP."""
    stats = ProjectedStats(field_goals=30, extra_points=35)
    player = Player(name="Test K", team="TST", position=Position.K, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    # 30*3 + 35*1 = 90 + 35 = 125
    assert pts == 125.0


def test_defense_scoring():
    """Verify defense scoring."""
    stats = ProjectedStats(sacks=40, def_interceptions=15, def_tds=3, points_allowed_per_game=20)
    player = Player(name="Test DEF", team="TST", position=Position.DEF, bye_week=7, projected_stats=stats)
    pts = calculate_fantasy_points(player)
    # sacks*1 + def_int*2 + def_td*6 + points_allowed adjustment
    # 40 + 30 + 18 + pa_adjustment(20ppg)
    # 20ppg -> 17 games -> 340 total -> tier gives some base points
    assert isinstance(pts, float)
    assert pts > 0
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_scoring.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.scoring'`

**Step 3: Implement scoring engine**

```python
"""Scoring engine for half PPR, 6pt TD fantasy football."""

from src.models import Player, Position


# Scoring constants
PASS_YARD_POINTS = 1.0 / 25.0   # 1 point per 25 yards
PASS_TD_POINTS = 6.0
INT_POINTS = -2.0
RUSH_YARD_POINTS = 1.0 / 10.0   # 1 point per 10 yards
RUSH_TD_POINTS = 6.0
REC_YARD_POINTS = 1.0 / 10.0    # 1 point per 10 yards
REC_TD_POINTS = 6.0
RECEPTION_POINTS = 0.5          # half PPR
FG_POINTS = 3.0
XP_POINTS = 1.0
SACK_POINTS = 1.0
DEF_INT_POINTS = 2.0
DEF_TD_POINTS = 6.0


def _defense_points_allowed_bonus(points_allowed_per_game: float) -> float:
    """Calculate bonus/penalty based on points allowed per game."""
    total_pa = points_allowed_per_game * 17  # 17-game season
    ppg = points_allowed_per_game
    if ppg < 10:
        return 80.0   # elite defense
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
    """Calculate total projected fantasy points for a player."""
    s = player.projected_stats
    points = 0.0

    # Passing
    points += s.pass_yards * PASS_YARD_POINTS
    points += s.pass_tds * PASS_TD_POINTS
    points += s.interceptions * INT_POINTS

    # Rushing
    points += s.rush_yards * RUSH_YARD_POINTS
    points += s.rush_tds * RUSH_TD_POINTS

    # Receiving (half PPR)
    points += s.receptions * RECEPTION_POINTS
    points += s.rec_yards * REC_YARD_POINTS
    points += s.rec_tds * REC_TD_POINTS

    # Kicking
    points += s.field_goals * FG_POINTS
    points += s.extra_points * XP_POINTS

    # Defense
    points += s.sacks * SACK_POINTS
    points += s.def_interceptions * DEF_INT_POINTS
    points += s.def_tds * DEF_TD_POINTS
    if player.position == Position.DEF:
        points += _defense_points_allowed_bonus(s.points_allowed_per_game)

    player.fantasy_points = points
    return points


def score_all_players(players: list[Player]) -> list[Player]:
    """Calculate fantasy points for all players and return sorted by points desc."""
    for player in players:
        calculate_fantasy_points(player)
    return sorted(players, key=lambda p: p.fantasy_points, reverse=True)
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scoring.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/scoring.py tests/test_scoring.py
git commit -m "feat: add scoring engine with half PPR, 6pt TD rules"
```

---

### Task 5: VBD Rankings Engine

**Files:**
- Create: `src/rankings.py`
- Create: `tests/test_rankings.py`

**Step 1: Write failing tests**

```python
"""Tests for VBD rankings engine."""

from src.models import Player, Position, ProjectedStats
from src.scoring import calculate_fantasy_points
from src.rankings import calculate_vbd, get_replacement_level


def _make_player(name: str, pos: Position, pts: float) -> Player:
    """Helper to create a player with pre-set fantasy points."""
    p = Player(name=name, team="TST", position=pos, bye_week=7)
    p.fantasy_points = pts
    return p


def test_replacement_level():
    """QB replacement is QB13 in a 12-team league."""
    players = [_make_player(f"QB{i}", Position.QB, 300 - i * 10) for i in range(1, 20)]
    replacement = get_replacement_level(players, Position.QB, num_teams=12)
    # QB13 is the replacement level — QB13 has 300 - 13*10 = 170 points
    assert replacement == 170.0


def test_vbd_scores():
    """VBD = player points - replacement level at their position."""
    qbs = [_make_player(f"QB{i}", Position.QB, 400 - i * 10) for i in range(1, 20)]
    rbs = [_make_player(f"RB{i}", Position.RB, 300 - i * 5) for i in range(1, 40)]
    all_players = qbs + rbs
    ranked = calculate_vbd(all_players, num_teams=12)
    # QB1 (390 pts) VBD = 390 - QB13_pts(400-130=270) = 120
    qb1 = next(p for p in ranked if p.name == "QB1")
    assert qb1.vbd_score == 120.0


def test_vbd_ranking_order():
    """Players should be ranked by VBD score descending."""
    qbs = [_make_player(f"QB{i}", Position.QB, 400 - i * 10) for i in range(1, 20)]
    rbs = [_make_player(f"RB{i}", Position.RB, 300 - i * 5) for i in range(1, 40)]
    ranked = calculate_vbd(qbs + rbs, num_teams=12)
    for i in range(len(ranked) - 1):
        assert ranked[i].vbd_score >= ranked[i + 1].vbd_score
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_rankings.py -v
```

**Step 3: Implement VBD rankings**

```python
"""Value-Based Drafting (VBD) rankings engine."""

from src.models import Player, Position, ROSTER_SLOTS, RosterSlot, FLEX_ELIGIBLE


# Map positions to starter slots for replacement level calc
# RB/WR get extra for flex usage
REPLACEMENT_RANK = {
    Position.QB: 1,   # 1 starter per team
    Position.RB: 2.2, # 2 starters + ~0.2 flex share
    Position.WR: 2.2, # 2 starters + ~0.2 flex share
    Position.TE: 1.1, # 1 starter + ~0.1 flex share
    Position.K: 1,
    Position.DEF: 1,
}


def get_replacement_level(players: list[Player], position: Position, num_teams: int = 12) -> float:
    """Get the fantasy points of the replacement-level player at a position."""
    pos_players = sorted(
        [p for p in players if p.position == position],
        key=lambda p: p.fantasy_points,
        reverse=True,
    )
    replacement_index = int(num_teams * REPLACEMENT_RANK[position])
    if replacement_index >= len(pos_players):
        replacement_index = len(pos_players) - 1
    return pos_players[replacement_index].fantasy_points


def calculate_vbd(players: list[Player], num_teams: int = 12) -> list[Player]:
    """Calculate VBD scores for all players and return ranked list."""
    # Get replacement levels for each position
    replacement_levels: dict[Position, float] = {}
    for pos in Position:
        pos_players = [p for p in players if p.position == pos]
        if pos_players:
            replacement_levels[pos] = get_replacement_level(players, pos, num_teams)
        else:
            replacement_levels[pos] = 0.0

    # Calculate VBD for each player
    for player in players:
        baseline = replacement_levels.get(player.position, 0.0)
        player.vbd_score = player.fantasy_points - baseline

    # Sort by VBD descending
    return sorted(players, key=lambda p: p.vbd_score, reverse=True)


def get_draft_recommendations(
    available: list[Player],
    team_needs: list[RosterSlot],
    num_recommendations: int = 5,
) -> list[Player]:
    """Get top draft picks considering VBD and team needs.

    Boosts players who fill a team need; penalizes positions already filled.
    """
    scored: list[tuple[float, Player]] = []

    need_positions = set()
    for slot in team_needs:
        if slot == RosterSlot.FLEX:
            need_positions.update(FLEX_ELIGIBLE)
        elif slot != RosterSlot.BENCH:
            need_positions.add(Position(slot.value))

    for player in available:
        adj_score = player.vbd_score
        if player.position in need_positions:
            adj_score *= 1.15  # 15% boost for filling a need
        else:
            adj_score *= 0.8   # 20% penalty for non-need
        scored.append((adj_score, player))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [player for _, player in scored[:num_recommendations]]


def get_best_available_by_position(
    available: list[Player], position: Position, count: int = 5
) -> list[Player]:
    """Get top available players at a specific position."""
    pos_players = [p for p in available if p.position == position]
    pos_players.sort(key=lambda p: p.vbd_score, reverse=True)
    return pos_players[:count]


def get_value_picks(available: list[Player], current_pick: int, count: int = 5) -> list[Player]:
    """Find players falling past their ADP (value picks)."""
    value_players = [
        p for p in available
        if p.adp < current_pick and p.vbd_score > 0
    ]
    value_players.sort(key=lambda p: (current_pick - p.adp) * p.vbd_score, reverse=True)
    return value_players[:count]
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_rankings.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/rankings.py tests/test_rankings.py
git commit -m "feat: add VBD rankings engine with draft recommendations"
```

---

### Task 6: Draft Engine

**Files:**
- Create: `src/draft.py`
- Create: `tests/test_draft.py`

**Step 1: Write failing tests**

```python
"""Tests for the draft engine."""

from src.models import Player, Team, League, Position, ProjectedStats, TOTAL_ROUNDS
from src.draft import (
    generate_snake_order,
    DraftEngine,
)


def test_snake_order_round1():
    """Round 1 goes 1-12."""
    order = generate_snake_order(12, 15)
    assert order[0] == list(range(1, 13))


def test_snake_order_round2():
    """Round 2 goes 12-1 (reversed)."""
    order = generate_snake_order(12, 15)
    assert order[1] == list(range(12, 0, -1))


def test_snake_order_total_picks():
    """15 rounds × 12 teams = 180 picks."""
    order = generate_snake_order(12, 15)
    total = sum(len(r) for r in order)
    assert total == 180


def test_draft_engine_pick_removes_player():
    """Making a pick removes the player from available pool."""
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
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_draft.py -v
```

**Step 3: Implement draft engine**

```python
"""Snake draft engine for mock drafts and live draft assistance."""

import random
from src.models import (
    Player, Team, League, DraftPick, Position,
    RosterSlot, ROSTER_SLOTS, FLEX_ELIGIBLE, TOTAL_ROUNDS,
)
from src.rankings import (
    calculate_vbd, get_draft_recommendations,
    get_best_available_by_position, get_value_picks,
)


def generate_snake_order(num_teams: int, num_rounds: int) -> list[list[int]]:
    """Generate snake draft order. Returns list of rounds, each a list of team positions (1-indexed)."""
    order = []
    for round_num in range(num_rounds):
        if round_num % 2 == 0:
            order.append(list(range(1, num_teams + 1)))
        else:
            order.append(list(range(num_teams, 0, -1)))
    return order


def auto_assign_slot(player: Player, team: Team) -> RosterSlot:
    """Determine the best roster slot for a drafted player."""
    filled = team.starter_slots_filled()

    # Try the player's natural position slot first
    pos_to_slot = {
        Position.QB: RosterSlot.QB,
        Position.RB: RosterSlot.RB,
        Position.WR: RosterSlot.WR,
        Position.TE: RosterSlot.TE,
        Position.K: RosterSlot.K,
        Position.DEF: RosterSlot.DEF,
    }
    natural_slot = pos_to_slot[player.position]
    if filled.get(natural_slot, 0) < ROSTER_SLOTS.get(natural_slot, 0):
        return natural_slot

    # Try FLEX for eligible positions
    if player.position in FLEX_ELIGIBLE:
        if filled.get(RosterSlot.FLEX, 0) < ROSTER_SLOTS[RosterSlot.FLEX]:
            return RosterSlot.FLEX

    # Bench
    return RosterSlot.BENCH


class DraftEngine:
    """Manages the draft process for both mock and live modes."""

    def __init__(self, league: League):
        self.league = league
        self.snake_order = generate_snake_order(len(league.teams), TOTAL_ROUNDS)
        self.current_round = 0
        self.current_pick_in_round = 0
        self.overall_pick = 0

    @property
    def is_draft_complete(self) -> bool:
        return self.current_round >= TOTAL_ROUNDS

    def current_drafter(self) -> Team | None:
        if self.is_draft_complete:
            return None
        pos = self.snake_order[self.current_round][self.current_pick_in_round]
        return next(t for t in self.league.teams if t.draft_position == pos)

    def make_pick(self, team: Team, player: Player) -> DraftPick:
        """Record a draft pick."""
        from src.models import RosterEntry
        self.overall_pick += 1
        slot = auto_assign_slot(player, team)
        team.roster.append(RosterEntry(player=player, slot=slot))

        if player in self.league.available_players:
            self.league.available_players.remove(player)

        pick = DraftPick(
            round_num=self.current_round + 1,
            pick_num=self.overall_pick,
            team=team,
            player=player,
        )
        self.league.draft_picks.append(pick)

        # Advance to next pick
        self.current_pick_in_round += 1
        if self.current_pick_in_round >= len(self.league.teams):
            self.current_pick_in_round = 0
            self.current_round += 1

        return pick

    def ai_pick(self, team: Team) -> DraftPick:
        """Have AI make a pick for a team (used in mock drafts)."""
        needs = team.needs()
        recommendations = get_draft_recommendations(
            self.league.available_players, needs, num_recommendations=10
        )

        if not recommendations:
            # Fallback: pick best available
            available_sorted = sorted(
                self.league.available_players,
                key=lambda p: p.vbd_score,
                reverse=True,
            )
            pick_player = available_sorted[0] if available_sorted else None
        else:
            # Add some randomness: pick from top 3 with weighting
            top = recommendations[:3]
            weights = [3, 2, 1][:len(top)]
            pick_player = random.choices(top, weights=weights, k=1)[0]

        if pick_player:
            return self.make_pick(team, pick_player)
        raise ValueError("No players available to draft")

    def get_recommendations(self, team: Team, count: int = 5) -> list[Player]:
        """Get draft recommendations for a team."""
        needs = team.needs()
        return get_draft_recommendations(self.league.available_players, needs, count)

    def get_position_best(self, position: Position, count: int = 5) -> list[Player]:
        """Get best available at a position."""
        return get_best_available_by_position(self.league.available_players, position, count)

    def get_value_alerts(self, count: int = 5) -> list[Player]:
        """Get players falling past their ADP."""
        return get_value_picks(self.league.available_players, self.overall_pick, count)
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_draft.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/draft.py tests/test_draft.py
git commit -m "feat: add snake draft engine with mock and live draft support"
```

---

### Task 7: Team Manager

**Files:**
- Create: `src/team_manager.py`
- Create: `tests/test_team_manager.py`

**Step 1: Write failing tests**

```python
"""Tests for team management."""

from src.models import (
    Player, Team, League, Position, ProjectedStats,
    RosterEntry, RosterSlot,
)
from src.team_manager import (
    add_player, drop_player, trade_players, optimize_lineup,
)


def _make_league_with_player():
    p1 = Player(name="RB1", team="TST", position=Position.RB, bye_week=7)
    p1.fantasy_points = 200.0
    p1.vbd_score = 50.0
    p2 = Player(name="FA1", team="TST", position=Position.RB, bye_week=7)
    p2.fantasy_points = 150.0
    p2.vbd_score = 30.0
    team = Team(name="Team 1", draft_position=1)
    team.roster.append(RosterEntry(player=p1, slot=RosterSlot.RB))
    league = League(name="Test", teams=[team], available_players=[p2])
    return league, team, p1, p2


def test_add_player():
    league, team, p1, p2 = _make_league_with_player()
    add_player(league, team, p2)
    assert p2 in [e.player for e in team.roster]
    assert p2 not in league.available_players


def test_drop_player():
    league, team, p1, p2 = _make_league_with_player()
    drop_player(league, team, p1)
    assert p1 not in [e.player for e in team.roster]


def test_trade_players():
    p1 = Player(name="P1", team="A", position=Position.WR, bye_week=7)
    p1.fantasy_points = 200.0
    p2 = Player(name="P2", team="B", position=Position.WR, bye_week=7)
    p2.fantasy_points = 180.0
    t1 = Team(name="T1", draft_position=1)
    t1.roster.append(RosterEntry(player=p1, slot=RosterSlot.WR))
    t2 = Team(name="T2", draft_position=2)
    t2.roster.append(RosterEntry(player=p2, slot=RosterSlot.WR))
    league = League(name="Test", teams=[t1, t2])
    trade_players(league, t1, [p1], t2, [p2])
    assert p2 in [e.player for e in t1.roster]
    assert p1 in [e.player for e in t2.roster]
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_team_manager.py -v
```

**Step 3: Implement team manager**

```python
"""Team management: roster moves, trades, free agency, lineup optimization."""

from src.models import (
    Player, Team, League, Position,
    RosterEntry, RosterSlot, ROSTER_SLOTS, FLEX_ELIGIBLE,
)


def add_player(league: League, team: Team, player: Player, slot: RosterSlot | None = None) -> None:
    """Add a free agent to a team's roster."""
    if slot is None:
        slot = _find_best_slot(player, team)
    team.roster.append(RosterEntry(player=player, slot=slot))
    if player in league.available_players:
        league.available_players.remove(player)


def drop_player(league: League, team: Team, player: Player) -> None:
    """Drop a player from a team back to free agency."""
    team.roster = [e for e in team.roster if e.player.name != player.name]
    league.available_players.append(player)


def trade_players(
    league: League,
    team1: Team, players_from_team1: list[Player],
    team2: Team, players_from_team2: list[Player],
) -> None:
    """Execute a trade between two teams."""
    # Remove players from each team
    for p in players_from_team1:
        team1.roster = [e for e in team1.roster if e.player.name != p.name]
    for p in players_from_team2:
        team2.roster = [e for e in team2.roster if e.player.name != p.name]

    # Add to new teams
    for p in players_from_team1:
        slot = _find_best_slot(p, team2)
        team2.roster.append(RosterEntry(player=p, slot=slot))
    for p in players_from_team2:
        slot = _find_best_slot(p, team1)
        team1.roster.append(RosterEntry(player=p, slot=slot))


def evaluate_trade(
    team1: Team, players_from_team1: list[Player],
    team2: Team, players_from_team2: list[Player],
) -> dict:
    """Evaluate a trade's fairness based on VBD values."""
    team1_giving = sum(p.vbd_score for p in players_from_team1)
    team1_getting = sum(p.vbd_score for p in players_from_team2)
    team2_giving = sum(p.vbd_score for p in players_from_team2)
    team2_getting = sum(p.vbd_score for p in players_from_team1)

    return {
        "team1_net": team1_getting - team1_giving,
        "team2_net": team2_getting - team2_giving,
        "team1_before": sum(p.fantasy_points for p in team1.players()),
        "team1_after": sum(p.fantasy_points for p in team1.players()) - sum(p.fantasy_points for p in players_from_team1) + sum(p.fantasy_points for p in players_from_team2),
        "team2_before": sum(p.fantasy_points for p in team2.players()),
        "team2_after": sum(p.fantasy_points for p in team2.players()) - sum(p.fantasy_points for p in players_from_team2) + sum(p.fantasy_points for p in players_from_team1),
    }


def optimize_lineup(team: Team, bye_week: int | None = None) -> list[RosterEntry]:
    """Set the optimal starting lineup for a team, considering bye weeks."""
    # Separate players by position, exclude those on bye
    available = [
        e for e in team.roster
        if bye_week is None or e.player.bye_week != bye_week
    ]

    best_lineup: list[RosterEntry] = []
    used_players: set[str] = set()

    # Fill each starter slot with the best available player
    for slot in [RosterSlot.QB, RosterSlot.RB, RosterSlot.WR, RosterSlot.TE, RosterSlot.K, RosterSlot.DEF]:
        needed = ROSTER_SLOTS[slot]
        candidates = [
            e for e in available
            if e.player.position == Position(slot.value) and e.player.name not in used_players
        ]
        candidates.sort(key=lambda e: e.player.fantasy_points, reverse=True)
        for c in candidates[:needed]:
            best_lineup.append(RosterEntry(player=c.player, slot=slot))
            used_players.add(c.player.name)

    # Fill FLEX with best remaining RB/WR/TE
    flex_candidates = [
        e for e in available
        if e.player.position in FLEX_ELIGIBLE and e.player.name not in used_players
    ]
    flex_candidates.sort(key=lambda e: e.player.fantasy_points, reverse=True)
    if flex_candidates:
        best_lineup.append(RosterEntry(player=flex_candidates[0].player, slot=RosterSlot.FLEX))
        used_players.add(flex_candidates[0].player.name)

    # Rest go to bench
    for e in team.roster:
        if e.player.name not in used_players:
            best_lineup.append(RosterEntry(player=e.player, slot=RosterSlot.BENCH))

    return best_lineup


def update_player_team(players: list[Player], player_name: str, new_team: str) -> bool:
    """Update a player's NFL team (for real-world trades/free agency)."""
    for p in players:
        if p.name.lower() == player_name.lower():
            p.team = new_team
            return True
    return False


def _find_best_slot(player: Player, team: Team) -> RosterSlot:
    """Find the best available roster slot for a player."""
    from src.draft import auto_assign_slot
    return auto_assign_slot(player, team)
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_team_manager.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/team_manager.py tests/test_team_manager.py
git commit -m "feat: add team manager with trades, free agency, lineup optimizer"
```

---

### Task 8: Waiver Wire Recommendations

**Files:**
- Create: `src/waiver.py`
- Create: `tests/test_waiver.py`

**Step 1: Write failing tests**

```python
"""Tests for waiver wire recommendations."""

from src.models import (
    Player, Team, League, Position,
    RosterEntry, RosterSlot, ProjectedStats,
)
from src.waiver import get_waiver_recommendations


def test_waiver_recommends_upgrade():
    """Should recommend a free agent who is better than a current starter."""
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
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_waiver.py -v
```

**Step 3: Implement waiver recommendations**

```python
"""Waiver wire recommendation engine."""

from src.models import (
    Player, Team, League, Position,
    RosterSlot, FLEX_ELIGIBLE,
)


def get_waiver_recommendations(
    league: League,
    team: Team,
    max_recommendations: int = 10,
) -> list[dict]:
    """Analyze team weaknesses and recommend free agent pickups.

    Returns list of dicts with keys: add, drop, upgrade_score, reason.
    """
    free_agents = league.free_agents()
    if not free_agents:
        return []

    recommendations = []

    # For each position, find the weakest starter
    position_weakest: dict[Position, tuple[Player, RosterSlot]] = {}
    for entry in team.roster:
        if entry.slot == RosterSlot.BENCH:
            continue
        pos = entry.player.position
        if pos not in position_weakest or entry.player.fantasy_points < position_weakest[pos][0].fantasy_points:
            position_weakest[pos] = (entry.player, entry.slot)

    # Also check bench for worst players (drop candidates)
    bench_players = sorted(
        [e.player for e in team.roster if e.slot == RosterSlot.BENCH],
        key=lambda p: p.fantasy_points,
    )

    # Find upgrades from free agents
    for fa in sorted(free_agents, key=lambda p: p.vbd_score, reverse=True):
        # Check if FA is better than weakest starter at their position
        if fa.position in position_weakest:
            weakest, slot = position_weakest[fa.position]
            upgrade = fa.fantasy_points - weakest.fantasy_points
            if upgrade > 10:  # meaningful upgrade threshold
                drop_candidate = bench_players[0] if bench_players else weakest
                recommendations.append({
                    "add": fa,
                    "drop": drop_candidate,
                    "upgrade_score": upgrade,
                    "reason": f"Upgrades {fa.position.value}: {fa.name} ({fa.fantasy_points:.0f} pts) over {weakest.name} ({weakest.fantasy_points:.0f} pts)",
                })

        # Check if FA is better than worst bench player
        if bench_players:
            worst_bench = bench_players[0]
            if fa.fantasy_points > worst_bench.fantasy_points + 15:
                recommendations.append({
                    "add": fa,
                    "drop": worst_bench,
                    "upgrade_score": fa.fantasy_points - worst_bench.fantasy_points,
                    "reason": f"Bench upgrade: {fa.name} ({fa.fantasy_points:.0f} pts) over {worst_bench.name} ({worst_bench.fantasy_points:.0f} pts)",
                })

    # Deduplicate by add player, keep highest upgrade score
    seen = set()
    unique_recs = []
    for rec in sorted(recommendations, key=lambda r: r["upgrade_score"], reverse=True):
        if rec["add"].name not in seen:
            seen.add(rec["add"].name)
            unique_recs.append(rec)

    return unique_recs[:max_recommendations]
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_waiver.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/waiver.py tests/test_waiver.py
git commit -m "feat: add waiver wire recommendation engine"
```

---

### Task 9: Persistence (Save/Load)

**Files:**
- Create: `src/persistence.py`

**Step 1: Implement save/load**

```python
"""Save and load league state as JSON."""

import json
import os
from pathlib import Path
from src.models import Player, Team, League, RosterEntry, RosterSlot, DraftPick


SAVES_DIR = Path(__file__).parent.parent / "saves"
DATA_DIR = Path(__file__).parent.parent / "data"


def load_players(filepath: str | None = None) -> list[Player]:
    """Load player database from JSON."""
    if filepath is None:
        filepath = str(DATA_DIR / "players.json")
    with open(filepath) as f:
        data = json.load(f)
    return [Player.from_dict(p) for p in data["players"]]


def save_players(players: list[Player], filepath: str | None = None) -> None:
    """Save player database to JSON."""
    if filepath is None:
        filepath = str(DATA_DIR / "players.json")
    data = {"players": [p.to_dict() for p in players]}
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def save_league(league: League, filename: str | None = None) -> str:
    """Save league state to JSON. Returns the filepath."""
    SAVES_DIR.mkdir(exist_ok=True)
    if filename is None:
        filename = f"{league.name.lower().replace(' ', '_')}.json"
    filepath = SAVES_DIR / filename

    data = league.to_dict()
    # Also save the full player list for reconstruction
    all_players = set()
    for team in league.teams:
        for entry in team.roster:
            all_players.add(entry.player.name)
    for p in league.available_players:
        all_players.add(p.name)

    data["all_players"] = [p.to_dict() for p in league.available_players]
    for team_data in data["teams"]:
        team_obj = next(t for t in league.teams if t.name == team_data["name"])
        team_data["roster_full"] = [
            {"player": e.player.to_dict(), "slot": e.slot.value}
            for e in team_obj.roster
        ]

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return str(filepath)


def load_league(filename: str) -> League:
    """Load league state from JSON."""
    filepath = SAVES_DIR / filename
    with open(filepath) as f:
        data = json.load(f)

    # Rebuild players
    available = [Player.from_dict(p) for p in data.get("all_players", [])]

    # Rebuild teams
    teams = []
    for team_data in data["teams"]:
        team = Team(
            name=team_data["name"],
            draft_position=team_data["draft_position"],
        )
        for entry_data in team_data.get("roster_full", []):
            player = Player.from_dict(entry_data["player"])
            slot = RosterSlot(entry_data["slot"])
            team.roster.append(RosterEntry(player=player, slot=slot))
        teams.append(team)

    league = League(
        name=data["name"],
        teams=teams,
        available_players=available,
    )

    # Rebuild draft picks
    for pick_data in data.get("draft_picks", []):
        team = next((t for t in teams if t.name == pick_data["team_name"]), None)
        player_name = pick_data["player_name"]
        # Find the player on the team's roster
        player = None
        for t in teams:
            for e in t.roster:
                if e.player.name == player_name:
                    player = e.player
                    break
            if player:
                break
        if team and player:
            league.draft_picks.append(DraftPick(
                round_num=pick_data["round_num"],
                pick_num=pick_data["pick_num"],
                team=team,
                player=player,
            ))

    return league


def list_saves() -> list[str]:
    """List available save files."""
    SAVES_DIR.mkdir(exist_ok=True)
    return [f.name for f in SAVES_DIR.glob("*.json")]
```

**Step 2: Verify it imports**

```bash
python -c "from src.persistence import load_players, save_league; print('Persistence OK')"
```

**Step 3: Commit**

```bash
git add src/persistence.py
git commit -m "feat: add save/load persistence for league state"
```

---

### Task 10: CLI Interface

**Files:**
- Create: `src/cli.py`
- Modify: `main.py`

This is the largest task. The CLI ties everything together with Rich tables, menus, and interactive prompts.

**Step 1: Implement the full CLI**

Build `src/cli.py` with these menu functions:
- `main_menu()` — top-level menu (Mock Draft, Live Draft, Team Manager, Rankings, Update Players, Save/Load, Exit)
- `mock_draft_menu()` — set up and run a mock draft with the user picking for their team
- `live_draft_menu()` — track picks and show recommendations during a live draft
- `team_manager_menu()` — view rosters, trades, add/drop, lineup optimizer, waiver recommendations
- `rankings_menu()` — view VBD rankings with position filters
- `update_players_menu()` — update a player's team, add/remove players
- `save_load_menu()` — save or load league state

Use `rich` for:
- Color-coded position labels (QB=red, RB=green, WR=blue, TE=yellow, K=magenta, DEF=cyan)
- Tables for player listings, rosters, draft boards
- Panels for recommendations and alerts
- Progress bars during mock draft AI picks

Use `questionary` for:
- Menu selection
- Player name input with autocomplete where possible
- Confirmation prompts for trades/drops

**Step 2: Update main.py to launch CLI**

```python
"""Fantasy Football Draft Tool & Team Manager."""

from src.cli import main_menu


def main():
    main_menu()


if __name__ == "__main__":
    main()
```

**Step 3: Manual test — run the app**

```bash
python main.py
```

Verify: main menu appears with all options, can navigate to each submenu.

**Step 4: Commit**

```bash
git add src/cli.py main.py
git commit -m "feat: add Rich CLI interface with all menus"
```

---

### Task 11: Integration Testing & Polish

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

```python
"""Integration test: full mock draft flow."""

from src.models import Player, Team, League, Position, ProjectedStats, TOTAL_ROUNDS
from src.scoring import score_all_players
from src.rankings import calculate_vbd
from src.draft import DraftEngine


def test_full_mock_draft():
    """Run a complete 15-round mock draft with 12 teams."""
    # Create minimal player pool
    players = []
    for i in range(1, 40):
        players.append(Player(
            name=f"QB{i}", team="TST", position=Position.QB, bye_week=7,
            projected_stats=ProjectedStats(pass_yards=4500-i*50, pass_tds=35-i, interceptions=10),
        ))
    for i in range(1, 70):
        players.append(Player(
            name=f"RB{i}", team="TST", position=Position.RB, bye_week=7,
            projected_stats=ProjectedStats(rush_yards=1500-i*15, rush_tds=12-i//5, receptions=40-i//2, rec_yards=400-i*5, rec_tds=2),
        ))
    for i in range(1, 70):
        players.append(Player(
            name=f"WR{i}", team="TST", position=Position.WR, bye_week=7,
            projected_stats=ProjectedStats(receptions=100-i, rec_yards=1400-i*15, rec_tds=10-i//7, rush_yards=20, rush_tds=0),
        ))
    for i in range(1, 25):
        players.append(Player(
            name=f"TE{i}", team="TST", position=Position.TE, bye_week=7,
            projected_stats=ProjectedStats(receptions=70-i*2, rec_yards=900-i*30, rec_tds=7-i//4),
        ))
    for i in range(1, 20):
        players.append(Player(
            name=f"K{i}", team="TST", position=Position.K, bye_week=7,
            projected_stats=ProjectedStats(field_goals=30-i//2, extra_points=40-i),
        ))
    for i in range(1, 33):
        players.append(Player(
            name=f"DEF{i}", team="TST", position=Position.DEF, bye_week=7,
            projected_stats=ProjectedStats(sacks=40-i, def_interceptions=15-i//3, def_tds=3, points_allowed_per_game=18+i//3),
        ))

    score_all_players(players)
    calculate_vbd(players)

    teams = [Team(name=f"Team {i}", draft_position=i) for i in range(1, 13)]
    league = League(name="Test League", teams=teams, available_players=players.copy())
    engine = DraftEngine(league)

    # Run full draft — all AI picks
    while not engine.is_draft_complete:
        team = engine.current_drafter()
        engine.ai_pick(team)

    # Verify each team has 15 players
    for team in teams:
        assert len(team.roster) == TOTAL_ROUNDS, f"{team.name} has {len(team.roster)} players"

    # Verify no player drafted twice
    all_drafted = []
    for team in teams:
        all_drafted.extend([e.player.name for e in team.roster])
    assert len(all_drafted) == len(set(all_drafted)), "Duplicate draft picks detected"
```

**Step 2: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS

**Step 3: Run the full app manually**

```bash
python main.py
```

Test: mock draft, live draft, team manager, all menu flows.

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for full mock draft flow"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Project scaffolding | `requirements.txt`, `main.py` |
| 2 | Data models | `src/models.py` |
| 3 | Player database | `data/players.json` |
| 4 | Scoring engine | `src/scoring.py` |
| 5 | VBD rankings | `src/rankings.py` |
| 6 | Draft engine | `src/draft.py` |
| 7 | Team manager | `src/team_manager.py` |
| 8 | Waiver wire | `src/waiver.py` |
| 9 | Persistence | `src/persistence.py` |
| 10 | CLI interface | `src/cli.py`, `main.py` |
| 11 | Integration tests | `tests/test_integration.py` |
