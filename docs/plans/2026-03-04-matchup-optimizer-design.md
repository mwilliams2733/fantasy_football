# Matchup-Based Lineup Optimizer Design

**Date:** 2026-03-04
**Goal:** Add a matchup-aware lineup optimizer to the team manager that suggests optimal starting lineups based on weekly opponent matchups and current season stats, then backtests lineup variants using permutation search + Monte Carlo simulation.

## Overview

New module `src/matchup_optimizer.py` that adjusts player projections by weekly matchup strength, finds the optimal starter lineup through permutation search, and validates confidence via Monte Carlo simulation. Integrates into the existing team manager page.

## Data Layer

Extend `src/data_scraper.py` with two new scraping functions:

### Schedule Scraping
- `scrape_schedule(year) -> dict[str, list[str]]` — PFR `/years/{year}/games.htm`
- Returns `{team_abbrev: [week1_opponent, week2_opponent, ...]}`
- Cached to `data/historical/{year}_schedule.json`

### Defense Rankings
- `scrape_defense_rankings(year) -> dict[str, dict[str, int]]` — PFR `/years/{year}/opp.htm`
- Ranks each team 1-32 by fantasy points allowed per position (vs_QB, vs_RB, vs_WR, vs_TE)
- Cached to `data/historical/{year}_defense_rankings.json`

### Matchup Multiplier
```
multiplier = 1.0 + (17 - rank) * 0.01
# Rank 1 (best D):  0.84 (16% reduction)
# Rank 16 (avg D):  1.01 (neutral)
# Rank 32 (worst D): 1.16 (16% boost)
```

## Core Engine — `src/matchup_optimizer.py`

### Functions

- **`get_matchup_adjusted_points(player, opponent, defense_rankings)`** — Applies defense rank multiplier to player's base fantasy_points. Returns adjusted float.

- **`generate_lineup_permutations(roster)`** — Generates all valid starter combinations. Fixed slots (1 QB, 2 RB, 2 WR, 1 TE, 1 K, 1 DEF) filled by best at each position. FLEX spot is the variable — tries every eligible bench RB/WR/TE. Typically 5-15 unique lineups.

- **`evaluate_lineup(lineup, opponent_map, defense_rankings)`** — Scores a lineup using matchup-adjusted points. Returns `{total_points, players: [{name, slot, base_pts, adjusted_pts, opponent, matchup_grade}]}`.

- **`monte_carlo_lineup(lineup, opponent_map, defense_rankings, simulations=500)`** — Adds random variance (normal distribution, stddev ~15% of base points) to matchup-adjusted projections. Returns `{mean, floor (10th pctl), ceiling (90th pctl), consistency}`.

- **`optimize_with_matchups(team, week, schedule, defense_rankings)`** — Main entry point. Runs permutation search, Monte Carlo on top 3, returns `{recommended_lineup, alternatives, analysis}`.

- **`validate_roster_rules(team)`** — Enforces max 2 QB, 1 K, 1 DEF. Returns list of violations.

## Draft Rules

Enforced across the app:
- **Max 2 QBs** on a roster
- **Max 1 K** on a roster
- **Max 1 DEF** on a roster
- Validated in draft engine `ai_pick()`, team manager add operations, and web API endpoints

## Web Integration

### New Route
- `POST /api/team/matchup-optimize` — Accepts `{league_file, team_name, week, year}`, returns recommended lineup + alternatives with Monte Carlo stats

### Team Manager UI Additions
- "Matchup Optimizer" panel with week selector (1-18) and year input
- "Optimize for Matchups" button
- Recommended lineup table: Slot, Player, Opponent, Base Pts, Adj Pts, Matchup Grade
- Alternative lineups (collapsible) showing top 2-3 variants
- Monte Carlo summary: expected, floor, ceiling, consistency %
- Color-coded matchup grades: green (favorable), yellow (neutral), red (tough)
- Roster rule violation warnings

## Data Flow

```
User selects week/year → Flask route
  → scrape_schedule(year) [cached]
  → scrape_defense_rankings(year) [cached]
  → optimize_with_matchups(team, week, schedule, rankings)
    → generate_lineup_permutations(roster)
    → evaluate_lineup() for each permutation
    → monte_carlo_lineup() for top 3
  → return JSON results to browser
  → render recommended + alternatives with charts
```
