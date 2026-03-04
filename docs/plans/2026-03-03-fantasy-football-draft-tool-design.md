# Fantasy Football Draft Tool & Team Manager — Design

## Overview

A Python CLI application for fantasy football draft strategy, mock drafting, live draft assistance, and full season team management. Built with modular architecture using Rich for terminal UI.

## League Settings

- Scoring: Half PPR, 6 pts per TD
- Roster: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE), 1 K, 1 DEF/ST + bench (6 spots)
- Draft: Snake draft, 12 teams, 15 rounds
- User's draft position: configurable at runtime (1-12)

## Project Structure

```
fantasy_football/
├── data/
│   └── players.json          # Full NFL player database
├── saves/                    # Saved league/draft state (JSON)
├── src/
│   ├── __init__.py
│   ├── models.py             # Player, Team, League dataclasses
│   ├── scoring.py            # ½ PPR scoring engine & projections
│   ├── rankings.py           # VBD player rankings & draft strategy
│   ├── draft.py              # Snake draft engine (mock + live assist)
│   ├── team_manager.py       # Roster, trades, free agency, lineups
│   ├── waiver.py             # Waiver wire recommendations
│   └── cli.py                # Rich CLI interface & menus
├── main.py                   # Entry point
└── requirements.txt          # rich, questionary
```

## Scoring Engine

| Category | Rule |
|----------|------|
| Passing yards | 1 pt per 25 yards |
| Passing TD | 6 pts |
| Interception | -2 pts |
| Rushing yards | 1 pt per 10 yards |
| Rushing TD | 6 pts |
| Receiving yards | 1 pt per 10 yards |
| Receiving TD | 6 pts |
| Reception | 0.5 pts (half PPR) |
| Field goal | 3 pts |
| Extra point | 1 pt |
| Defense | Base points adjusted by sacks, INTs, TDs, points allowed |

## Ranking Strategy — Value-Based Drafting (VBD)

Each player's value = their projected fantasy points minus the replacement-level player at their position.

Replacement levels for 12-team league:
- QB: QB13 (12 teams × 1 starter)
- RB: ~RB25 (12 teams × 2 starters + flex usage)
- WR: ~WR25 (12 teams × 2 starters + flex usage)
- TE: TE13 (12 teams × 1 starter)
- K: K13
- DEF: DEF13

Players ranked by VBD score across all positions. Draft recommendations adjust for:
- Roster needs (don't stack one position)
- ADP value (players falling past expected draft spot)
- Positional runs (bump value when a position is being drafted heavily)
- FLEX considerations (RB/WR/TE flex value)

## Draft Engine

### Mock Draft Simulator
- All 12 teams draft using VBD-based AI with randomization
- AI teams have varied tendencies (some reach, some follow ADP)
- User picks for their team; AI handles the rest
- Snake order: Round 1 picks 1→12, Round 2 picks 12→1, etc.
- 15 rounds to fill starters + bench
- Post-draft team grades and summary

### Live Draft Assistant
- User inputs picks as they happen on their platform
- Tracks all picks, updates available player pool
- Before each user pick shows:
  - Top 5 recommended picks (VBD + roster needs)
  - Best available by position
  - Value alerts (players falling past ADP)
- After each round shows team roster and remaining needs

## Team Manager

### Roster Management
- View any team's roster with projected points
- Weekly lineup optimizer (best lineup considering bye weeks)
- Roster warnings (empty slots, bye conflicts)

### Trades
- Propose trades between any two teams
- Trade analyzer: compares team value before/after
- Process trades by moving players between rosters

### Free Agency
- View free agents sorted by VBD
- Add/drop players (must drop if roster full)
- Free agent pool updates automatically

### Waiver Wire Recommendations
- Scans roster for weaknesses
- Compares free agents to current players by position
- Recommends pickups with upgrade score
- Suggests who to drop for each add

### Real-World Updates
- Edit players.json to update teams after NFL moves
- CLI command to update a player's team
- Add new players or remove retired ones

## CLI Interface

Main menu with options for mock draft, live draft, team manager, rankings, player data updates, save/load.

Rich library for:
- Color-coded position tables
- Draft board grid
- Interactive menus (questionary)
- Roster and ranking tables

## Persistence

- League state saved as JSON in saves/
- Multiple saves supported
- Auto-save after draft picks and roster moves

## Dependencies

- `rich` — terminal formatting and tables
- `questionary` — interactive menus and prompts
