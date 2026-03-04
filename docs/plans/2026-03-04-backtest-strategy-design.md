# Backtest & Strategy Improvement Design

**Date:** 2026-03-04
**Goal:** Backtest the VBD draft strategy against 2024 and 2025 actual NFL stats, auto-tune parameters, and improve the draft strategy based on results.

## Overview

Add a backtesting pipeline that simulates 1,000 drafts per season using pre-season projections, rescores using actual end-of-season stats, compares against baseline strategies, and automatically tunes VBD parameters for optimal performance.

## Architecture

Four new modules plugging into the existing codebase:

```
src/data_scraper.py    -> data/historical/{year}_actual_stats.json
src/backtest.py        -> data/backtest_results/{year}_results.json
src/strategy_tuner.py  -> data/backtest_results/tuning_results.json
src/backtest_report.py -> Rich console output + CSV export
```

## Module 1: Data Scraper (`src/data_scraper.py`)

### Purpose
Scrape actual season stats and pre-season ADP for historical seasons.

### Data Sources (priority order)
1. **Pro Football Reference** (primary) — HTML table scraping
2. **ESPN API** (fallback)
3. **Sleeper API** (fallback)

### Two datasets per season
1. **Pre-season projections/ADP** — what the draft strategy uses to make picks
2. **Actual end-of-season stats** — to score drafted teams after the fact

### Stats scraped
- Passing: yards, TDs, INTs
- Rushing: yards, TDs
- Receiving: receptions, yards, TDs
- Kicking: FGs made, XPs made
- Defense: sacks, INTs, TDs, points allowed per game

### Output format
Same schema as `data/players.json` saved to `data/historical/{year}_actual_stats.json` and `data/historical/{year}_preseason_adp.json`.

### Caching
Downloaded data cached locally. Rate-limited requests with delays between pages.

## Module 2: Backtest Engine (`src/backtest.py`)

### Core loop (per season, 1,000 iterations)
1. Load pre-season projections for the target year
2. Score & rank players using VBD (existing `scoring.py` + `rankings.py`)
3. Run full 12-team snake draft using existing `draft.py`
4. VBD strategy team rotates draft position (1-12) across runs
5. AI opponents use standard VBD + randomization
6. Rescore all drafted players using actual stats
7. Compute optimal lineup from each team's 15-player roster
8. Record metrics

### Baseline strategies (run in parallel)
- **Pure ADP** — always pick best ADP remaining (no VBD calculation)
- **Random** — pick randomly from top 30 available (noise floor)
- **VBD** — current algorithm under test

### Metrics captured per iteration
| Metric | Description |
|--------|-------------|
| Total team points (actual) | Optimal lineup total using real stats |
| Points per pick | Efficiency: total points / 15 picks |
| Positional actual VBD | Each position's performance vs. replacement |
| Draft position advantage | Performance by draft slot (1st vs 12th) |
| Bust rate | % of picks scoring below replacement level |
| Hit rate | % of picks finishing top 10 at position |

### Output
Results saved to `data/backtest_results/{year}_results.json` and `data/backtest_results/{year}_results.csv`.

## Module 3: Strategy Tuner (`src/strategy_tuner.py`)

### Parameter space

#### VBD parameters
| Parameter | Current | Search Range |
|-----------|---------|-------------|
| `REPLACEMENT_RANK[QB]` | 1.0 | 0.8–1.5 |
| `REPLACEMENT_RANK[RB]` | 2.2 | 1.5–3.0 |
| `REPLACEMENT_RANK[WR]` | 2.2 | 1.5–3.0 |
| `REPLACEMENT_RANK[TE]` | 1.1 | 0.8–1.5 |
| `need_boost` | 1.15 | 1.0–1.5 |
| `scarcity_penalty` | 0.8 | 0.5–1.0 |

#### Round-based positional targeting (new)
| Parameter | Search Range | Description |
|-----------|-------------|-------------|
| `round_1_2_position_pref` | RB-heavy / WR-heavy / BPA | Rounds 1-2 bias |
| `round_3_5_position_pref` | RB-heavy / WR-heavy / BPA | Rounds 3-5 bias |
| `qb_target_round` | 4–8 | Ideal round for first QB |
| `te_target_round` | 3–8 | Ideal round for first TE |

### Tuning approach
1. **Random search:** 200 parameter configurations, each run at 100 iterations per season
2. **Validation:** Top 5 configs re-run at full 1,000 iterations per season
3. **Output:** Ranked configs with performance stats

### Output
Saved to `data/backtest_results/tuning_results.json` and `data/backtest_results/tuning_results.csv`. Presented for manual review before applying.

## Module 4: Reporting (`src/backtest_report.py`)

### Rich console reports
- Summary table: VBD vs ADP-only vs Random comparison
- Per-draft-position performance heatmap
- Positional breakdown (which positions contributed most)
- Best/worst draft archetypes discovered
- Tuning results: top 5 configs ranked
- Before/after comparison: current params vs best-found params

### Export formats
- JSON: `data/backtest_results/*.json`
- CSV: `data/backtest_results/*.csv`

## CLI Integration

New menu item in `src/cli.py`:

```
8. Backtest & Strategy Lab
   ├── Run Backtest (current strategy)
   ├── Run Strategy Tuner
   ├── View Results
   └── Apply Best Strategy
```

"Apply Best Strategy" updates VBD constants in `src/rankings.py` with tuner-recommended values.

## Dependencies

New Python packages needed:
- `requests` — HTTP requests for scraping
- `beautifulsoup4` — HTML parsing for PFR
- `lxml` — Fast HTML parser backend

## Testing

- Unit tests for scraper parsing logic (mock HTML responses)
- Unit tests for backtest scoring against known outcomes
- Unit tests for tuner parameter generation and selection
- Integration test: full backtest run with small iteration count

## Success Criteria

1. VBD strategy consistently outperforms pure-ADP and random baselines
2. Tuned parameters improve average total team points by measurable margin
3. Results reproducible across both 2024 and 2025 seasons
4. Round-based targeting provides actionable draft guidance (e.g., "take RB in rounds 1-2")
