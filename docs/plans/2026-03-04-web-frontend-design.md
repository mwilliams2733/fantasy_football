# Web Frontend Design

**Date:** 2026-03-04
**Goal:** Add a local Flask web frontend exposing all features with a dark sports theme, interactive draft room, and Plotly charts for backtest results.

## Overview

Flask app at `http://localhost:5000` with sidebar navigation, dark sports theme, and all existing CLI features ported to the browser. Reuses existing `src/` modules directly — no API duplication.

## Tech Stack

- **Backend:** Flask (Python), Flask-SocketIO (WebSocket for draft)
- **Frontend:** Jinja2 templates, vanilla CSS/JS, Plotly via CDN
- **No build step:** No npm, no bundler. Just `python web/app.py`

## Project Structure

```
web/
├── app.py              # Flask app with all routes
├── static/
│   ├── css/
│   │   └── style.css   # Dark sports theme
│   └── js/
│       ├── draft.js    # Draft room interactivity + WebSocket
│       ├── backtest.js # Backtest controls + Plotly charts
│       └── common.js   # Shared utilities (fetch, table sorting)
└── templates/
    ├── base.html       # Layout: sidebar nav + content area
    ├── index.html      # Dashboard home
    ├── draft.html      # Mock draft (interactive + auto-sim)
    ├── live_draft.html # Live draft assistant
    ├── rankings.html   # Player rankings with sortable tables
    ├── team.html       # Team manager (roster, trades, waivers)
    ├── backtest.html   # Backtest & Strategy Lab with Plotly
    └── players.html    # Player data management
```

## UI Layout

- **Sidebar** (left, always visible): Navigation links to all pages
- **Main content** (right): Page-specific content
- **Desktop-first:** Sidebar collapses on narrow screens

## Dark Sports Theme

- Background: `#1a1a2e` (deep navy)
- Cards/panels: `#16213e`
- Borders/hover: `#0f3460`
- Text: `#e0e0e0`
- Position colors: QB=red, RB=green, WR=blue, TE=yellow, K=magenta, DEF=cyan

## Pages

### Dashboard (index.html)
- Quick stats: total players in DB, saved leagues count
- Recent activity / quick links to key actions

### Mock Draft (draft.html)
Two modes toggled by tabs:
- **Interactive:** Pick-by-pick with WebSocket. User sees available players, recommendations, clicks to pick. AI picks animate between user turns. Draft board shows all picks in snake order grid.
- **Auto-Sim:** Configure team name, position, click "Run Draft", see full results with team grades.

### Live Draft Assistant (live_draft.html)
- Configure league size, position
- Input opponent picks as they happen
- Shows real-time recommendations, best available by position, value alerts

### Player Rankings (rankings.html)
- Sortable table: rank, name, team, position, projected points, VBD score, ADP
- Filter by position (tabs or dropdown)
- Search by player name

### Team Manager (team.html)
- Select a team from saved leagues
- View roster with starter/bench designation
- Trade evaluator, add/drop, lineup optimizer, waiver recommendations

### Backtest & Strategy Lab (backtest.html)
- Run Backtest: select seasons, start run, show progress bar, display results
- Plotly charts: VBD vs ADP vs Random bar chart, draft position heatmap, positional breakdown
- Run Tuner: configure params, show progress, display top 5 configs
- Apply Best Strategy button with before/after comparison
- Export to CSV button

### Player Data (players.html)
- Editable table of all players
- Add/remove/update players
- Auto-saves to players.json

### Save/Load
- Integrated into team manager and draft pages (save after draft, load existing leagues)

## Data Flow

```
Browser (HTML/JS) --HTTP/WebSocket--> Flask (web/app.py) --direct import--> src/ modules
                                                                              |
                                                                     data/players.json
                                                                     data/historical/
                                                                     data/backtest_results/
                                                                     saves/
```

## WebSocket (Draft)

Flask-SocketIO for real-time draft:
- Client connects when entering interactive draft
- Server emits `ai_pick` events as AI teams draft
- Client emits `user_pick` when user selects a player
- Server responds with updated state

## Dependencies

New packages:
- `flask>=3.0`
- `flask-socketio>=5.3`

Plotly loaded via CDN (no pip install needed).
