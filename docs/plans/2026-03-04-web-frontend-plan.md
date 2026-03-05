# Web Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local Flask web app with dark sports theme, interactive draft room, Plotly charts, exposing all existing CLI features in the browser.

**Architecture:** Flask backend serves Jinja2 templates and exposes JSON endpoints for AJAX. Flask-SocketIO handles real-time WebSocket events for interactive draft. All game logic reuses existing `src/` modules directly — zero duplication. Static CSS/JS files handle theming and interactivity. Plotly loaded via CDN.

**Tech Stack:** Flask, Flask-SocketIO, Jinja2, vanilla JS, CSS custom properties, Plotly.js CDN

---

### Task 1: Add Flask Dependencies and Create App Skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `web/__init__.py`
- Create: `web/app.py`
- Create: `web/templates/base.html`
- Create: `web/static/css/style.css`
- Create: `web/static/js/common.js`

**Step 1: Update requirements.txt**

Append to `requirements.txt`:
```
flask>=3.0
flask-socketio>=5.3
```

**Step 2: Install dependencies**

Run: `pip install -r requirements.txt`

**Step 3: Create web/__init__.py**

Empty file.

**Step 4: Create web/app.py — minimal Flask app**

```python
"""Flask web frontend for Fantasy Football Draft Tool."""

import sys
from pathlib import Path

# Add project root to path so src/ imports work
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from src.models import Position, StrategyConfig
from src.scoring import score_all_players
from src.rankings import calculate_vbd, get_best_available_by_position
from src.persistence import load_players, save_players, list_saves, load_league, save_league

app = Flask(__name__)
app.secret_key = "fantasy-football-local"
socketio = SocketIO(app)

# Position color map (matches CLI)
POS_COLORS = {
    "QB": "#e74c3c",
    "RB": "#2ecc71",
    "WR": "#3498db",
    "TE": "#f1c40f",
    "K": "#e91e9b",
    "DEF": "#00bcd4",
}


def _load_and_prepare():
    """Load players, score, and calculate VBD."""
    players = load_players()
    score_all_players(players)
    calculate_vbd(players)
    return players


@app.route("/")
def index():
    """Dashboard home page."""
    players = _load_and_prepare()
    saves = list_saves()
    return render_template("index.html",
                           player_count=len(players),
                           save_count=len(saves))


# Context processor to make POS_COLORS available in all templates
@app.context_processor
def inject_pos_colors():
    return {"pos_colors": POS_COLORS}


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
```

**Step 5: Create web/templates/base.html — layout with sidebar**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Fantasy Football{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <script src="https://cdn.plot.ly/plotly-2.35.0.min.js" charset="utf-8"></script>
    {% block head %}{% endblock %}
</head>
<body>
    <nav class="sidebar">
        <div class="sidebar-header">
            <h2>Fantasy Football</h2>
        </div>
        <ul class="nav-links">
            <li><a href="/" class="{% if active_page == 'dashboard' %}active{% endif %}">Dashboard</a></li>
            <li><a href="/draft" class="{% if active_page == 'draft' %}active{% endif %}">Mock Draft</a></li>
            <li><a href="/live-draft" class="{% if active_page == 'live_draft' %}active{% endif %}">Live Draft</a></li>
            <li><a href="/rankings" class="{% if active_page == 'rankings' %}active{% endif %}">Player Rankings</a></li>
            <li><a href="/team" class="{% if active_page == 'team' %}active{% endif %}">Team Manager</a></li>
            <li><a href="/backtest" class="{% if active_page == 'backtest' %}active{% endif %}">Backtest Lab</a></li>
            <li><a href="/players" class="{% if active_page == 'players' %}active{% endif %}">Player Data</a></li>
        </ul>
    </nav>
    <main class="content">
        {% block content %}{% endblock %}
    </main>
    <script src="{{ url_for('static', filename='js/common.js') }}"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

**Step 6: Create web/static/css/style.css — dark sports theme**

Full dark theme CSS with:
- CSS custom properties for all colors
- Sidebar: fixed left, 240px wide, dark background
- Content area: margin-left 240px, padding
- Cards: `.card` class with dark panel background, border-radius, subtle border
- Tables: `.data-table` with striped rows, hover highlight, position-colored badges
- Buttons: `.btn-primary`, `.btn-secondary` with accent colors
- Forms: dark inputs matching theme
- Position badge: `.pos-badge` with per-position background colors
- Progress bar: `.progress-bar` for backtest/tuner
- Tabs: `.tab-group` for draft mode switching
- Responsive: sidebar collapses at 768px

**Step 7: Create web/static/js/common.js**

```javascript
/**
 * Common utilities for Fantasy Football web app.
 */

/** Make a table sortable by clicking column headers. */
function makeSortable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const headers = table.querySelectorAll("th[data-sort]");
    headers.forEach(header => {
        header.style.cursor = "pointer";
        header.addEventListener("click", () => {
            const col = header.dataset.sort;
            const tbody = table.querySelector("tbody");
            const rows = Array.from(tbody.querySelectorAll("tr"));
            const isNum = header.dataset.type === "number";
            const asc = header.dataset.dir !== "asc";
            rows.sort((a, b) => {
                const aVal = a.querySelector(`td[data-col="${col}"]`)?.textContent || "";
                const bVal = b.querySelector(`td[data-col="${col}"]`)?.textContent || "";
                if (isNum) return asc ? parseFloat(aVal) - parseFloat(bVal) : parseFloat(bVal) - parseFloat(aVal);
                return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            });
            header.dataset.dir = asc ? "asc" : "desc";
            rows.forEach(row => tbody.appendChild(row));
        });
    });
}

/** Filter table rows by search text. */
function filterTable(tableId, searchText) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const rows = table.querySelectorAll("tbody tr");
    const lower = searchText.toLowerCase();
    rows.forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(lower) ? "" : "none";
    });
}

/** POST JSON to a route and return parsed response. */
async function postJSON(url, data) {
    const res = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data),
    });
    return res.json();
}
```

**Step 8: Create web/templates/index.html — dashboard**

```html
{% extends "base.html" %}
{% set active_page = "dashboard" %}
{% block title %}Dashboard - Fantasy Football{% endblock %}
{% block content %}
<h1>Fantasy Football Draft Tool</h1>
<div class="card-grid">
    <div class="card">
        <h3>Players</h3>
        <p class="big-number">{{ player_count }}</p>
        <a href="/rankings" class="btn-primary">View Rankings</a>
    </div>
    <div class="card">
        <h3>Saved Leagues</h3>
        <p class="big-number">{{ save_count }}</p>
        <a href="/team" class="btn-primary">Manage Teams</a>
    </div>
    <div class="card">
        <h3>Mock Draft</h3>
        <p>Simulate a full draft</p>
        <a href="/draft" class="btn-primary">Start Draft</a>
    </div>
    <div class="card">
        <h3>Backtest Lab</h3>
        <p>Test your strategy</p>
        <a href="/backtest" class="btn-primary">Open Lab</a>
    </div>
</div>
{% endblock %}
```

**Step 9: Test manually**

Run: `python web/app.py`
Open: `http://localhost:5000`
Expected: Dashboard page renders with dark theme, sidebar nav, 4 cards with correct counts.

**Step 10: Commit**

```bash
git add requirements.txt web/
git commit -m "feat: add Flask app skeleton with dark sports theme and dashboard"
```

---

### Task 2: Player Rankings Page

**Files:**
- Modify: `web/app.py` (add route)
- Create: `web/templates/rankings.html`

**Step 1: Add route to app.py**

```python
@app.route("/rankings")
def rankings():
    """Player rankings with sortable, filterable table."""
    players = _load_and_prepare()
    position_filter = request.args.get("position", "ALL")
    if position_filter != "ALL":
        players = [p for p in players if p.position.value == position_filter]
    players.sort(key=lambda p: p.vbd_score, reverse=True)
    return render_template("rankings.html",
                           players=players,
                           active_filter=position_filter,
                           positions=["ALL", "QB", "RB", "WR", "TE", "K", "DEF"])
```

**Step 2: Create rankings.html**

Template with:
- Position filter tabs (ALL, QB, RB, WR, TE, K, DEF) as links to `?position=XX`
- Search input that calls `filterTable()` on keyup
- Sortable table with columns: Rank, Name, Team, Pos (colored badge), Projected Pts, VBD Score, ADP
- Each `<th>` has `data-sort` and `data-type` attributes
- Each `<td>` has `data-col` attribute matching the header
- Call `makeSortable("rankings-table")` in script block

**Step 3: Test manually**

Run app, navigate to `/rankings`. Verify: table renders, position filter works, sorting works, search filters.

**Step 4: Commit**

```bash
git add web/
git commit -m "feat: add player rankings page with sortable filterable table"
```

---

### Task 3: Mock Draft Page — Auto-Sim Mode

**Files:**
- Modify: `web/app.py` (add routes)
- Create: `web/templates/draft.html`
- Create: `web/static/js/draft.js`

**Step 1: Add routes to app.py**

```python
from src.draft import DraftEngine
from src.models import Team, League, TOTAL_ROUNDS

@app.route("/draft")
def draft():
    """Mock draft page."""
    return render_template("draft.html")


@app.route("/api/draft/auto-sim", methods=["POST"])
def api_draft_auto_sim():
    """Run a full auto-simulated draft and return results."""
    data = request.get_json()
    team_name = data.get("team_name", "My Team")
    draft_position = int(data.get("draft_position", 1))

    players = _load_and_prepare()

    # Create teams
    ai_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo",
                "Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo"]
    teams = []
    for i in range(1, 13):
        if i == draft_position:
            teams.append(Team(name=team_name, draft_position=i))
        else:
            name = ai_names.pop(0) if ai_names else f"Team {i}"
            teams.append(Team(name=name, draft_position=i))

    league = League(name="Mock Draft", teams=teams, available_players=players.copy())
    engine = DraftEngine(league)

    picks = []
    while not engine.is_draft_complete:
        team = engine.current_drafter()
        pick = engine.ai_pick(team)
        picks.append({
            "round": pick.round_num,
            "pick": pick.pick_num,
            "team": pick.team.name,
            "player": pick.player.name,
            "position": pick.player.position.value,
            "points": round(pick.player.fantasy_points, 1),
            "vbd": round(pick.player.vbd_score, 1),
        })

    # Build team results
    team_results = []
    for t in teams:
        total_pts = sum(e.player.fantasy_points for e in t.starters())
        team_results.append({
            "name": t.name,
            "draft_position": t.draft_position,
            "total_points": round(total_pts, 1),
            "roster": [
                {"player": e.player.name, "position": e.player.position.value,
                 "slot": e.slot.value, "points": round(e.player.fantasy_points, 1)}
                for e in t.roster
            ],
        })
    team_results.sort(key=lambda t: t["total_points"], reverse=True)

    # Save league for later use in team manager
    app.config["_last_league"] = league

    return jsonify({"picks": picks, "teams": team_results})
```

**Step 2: Create draft.html**

Template with two tabs: "Interactive" and "Auto-Sim".

Auto-Sim tab contains:
- Form: team name input, draft position dropdown (1-12), "Run Draft" button
- Results area (hidden until draft runs): draft board grid (15 rows x 12 cols showing picks), team roster cards
- Each team card shows roster entries with position badges and points

**Step 3: Create draft.js**

```javascript
/**
 * Draft page interactivity.
 */

async function runAutoSimDraft() {
    const teamName = document.getElementById("team-name").value || "My Team";
    const draftPos = document.getElementById("draft-position").value;
    const btn = document.getElementById("run-draft-btn");
    const resultsDiv = document.getElementById("draft-results");

    btn.disabled = true;
    btn.textContent = "Drafting...";

    const data = await postJSON("/api/draft/auto-sim", {
        team_name: teamName,
        draft_position: parseInt(draftPos),
    });

    // Render draft board
    renderDraftBoard(data.picks);

    // Render team results
    renderTeamResults(data.teams, teamName);

    resultsDiv.style.display = "block";
    btn.disabled = false;
    btn.textContent = "Run Draft";
}

function renderDraftBoard(picks) {
    const board = document.getElementById("draft-board");
    board.innerHTML = "";
    // Create 15x12 grid
    const table = document.createElement("table");
    table.className = "data-table draft-board-table";
    // Header row: team names
    const headerRow = document.createElement("tr");
    const teams = [...new Set(picks.filter(p => p.round === 1).map(p => p.team))];
    headerRow.innerHTML = "<th>Rd</th>" + teams.map(t => `<th>${t}</th>`).join("");
    table.appendChild(headerRow);

    for (let round = 1; round <= 15; round++) {
        const row = document.createElement("tr");
        row.innerHTML = `<td>${round}</td>`;
        const roundPicks = picks.filter(p => p.round === round);
        // Snake order: even rounds are reversed
        if (round % 2 === 0) roundPicks.reverse();
        roundPicks.forEach(pick => {
            const color = document.body.dataset[`pos${pick.position}`] || "#888";
            row.innerHTML += `<td><span class="pos-badge" style="background:var(--pos-${pick.position.toLowerCase()})">${pick.position}</span> ${pick.player}</td>`;
        });
        table.appendChild(row);
    }
    board.appendChild(table);
}

function renderTeamResults(teams, userTeamName) {
    const container = document.getElementById("team-results");
    container.innerHTML = "";
    teams.forEach((team, i) => {
        const isUser = team.name === userTeamName;
        const card = document.createElement("div");
        card.className = `card team-card ${isUser ? "user-team" : ""}`;
        let rosterHTML = team.roster.map(e =>
            `<tr><td><span class="pos-badge pos-${e.position.toLowerCase()}">${e.position}</span></td>
             <td>${e.player}</td><td>${e.slot}</td><td>${e.points}</td></tr>`
        ).join("");
        card.innerHTML = `
            <h3>${isUser ? "⭐ " : ""}#${i + 1} ${team.name} (Pick ${team.draft_position})</h3>
            <p class="team-total">${team.total_points} pts</p>
            <table class="data-table compact">
                <thead><tr><th>Pos</th><th>Player</th><th>Slot</th><th>Pts</th></tr></thead>
                <tbody>${rosterHTML}</tbody>
            </table>`;
        container.appendChild(card);
    });
}
```

**Step 4: Test manually**

Run app, go to `/draft`, fill form, click "Run Draft". Verify draft board and team results render.

**Step 5: Commit**

```bash
git add web/
git commit -m "feat: add mock draft page with auto-sim mode"
```

---

### Task 4: Mock Draft — Interactive Mode with WebSocket

**Files:**
- Modify: `web/app.py` (add SocketIO events)
- Modify: `web/templates/draft.html` (add interactive tab content)
- Modify: `web/static/js/draft.js` (add WebSocket logic)

**Step 1: Add SocketIO events to app.py**

```python
from flask_socketio import emit
import time

# Store active draft sessions
_active_drafts = {}

@socketio.on("start_draft")
def handle_start_draft(data):
    """Start an interactive draft session."""
    team_name = data.get("team_name", "My Team")
    draft_position = int(data.get("draft_position", 1))

    players = _load_and_prepare()
    ai_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo",
                "Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo"]
    teams = []
    for i in range(1, 13):
        if i == draft_position:
            teams.append(Team(name=team_name, draft_position=i))
        else:
            name = ai_names.pop(0) if ai_names else f"Team {i}"
            teams.append(Team(name=name, draft_position=i))

    league = League(name="Interactive Draft", teams=teams, available_players=players.copy())
    engine = DraftEngine(league)
    sid = request.sid
    _active_drafts[sid] = {"engine": engine, "league": league, "user_team": team_name, "user_pos": draft_position}

    # Run AI picks until it's the user's turn (or draft is over)
    _advance_draft(sid)


def _advance_draft(sid):
    """Run AI picks until it's the user's turn or draft ends."""
    draft = _active_drafts.get(sid)
    if not draft:
        return
    engine = draft["engine"]

    while not engine.is_draft_complete:
        team = engine.current_drafter()
        if team.name == draft["user_team"]:
            # User's turn — send recommendations and wait
            recs = engine.get_recommendations(team, count=10)
            available = sorted(engine.league.available_players, key=lambda p: p.vbd_score, reverse=True)[:50]
            emit("your_turn", {
                "round": engine.current_round + 1,
                "pick": engine.overall_pick + 1,
                "recommendations": [
                    {"name": p.name, "position": p.position.value, "points": round(p.fantasy_points, 1),
                     "vbd": round(p.vbd_score, 1), "adp": p.adp}
                    for p in recs
                ],
                "available": [
                    {"name": p.name, "position": p.position.value, "points": round(p.fantasy_points, 1),
                     "vbd": round(p.vbd_score, 1), "adp": p.adp}
                    for p in available
                ],
                "roster": [
                    {"player": e.player.name, "position": e.player.position.value, "slot": e.slot.value}
                    for e in team.roster
                ],
            })
            return
        else:
            # AI pick
            pick = engine.ai_pick(team)
            emit("ai_pick", {
                "round": pick.round_num,
                "pick": pick.pick_num,
                "team": pick.team.name,
                "player": pick.player.name,
                "position": pick.player.position.value,
            })
            socketio.sleep(0.3)  # Brief pause for animation

    # Draft complete
    _emit_draft_complete(sid)


@socketio.on("user_pick")
def handle_user_pick(data):
    """Handle when user picks a player."""
    sid = request.sid
    draft = _active_drafts.get(sid)
    if not draft:
        return
    engine = draft["engine"]
    player_name = data.get("player_name", "")

    # Find player in available
    player = None
    for p in engine.league.available_players:
        if p.name == player_name:
            player = p
            break
    if not player:
        emit("error", {"message": f"Player '{player_name}' not available"})
        return

    team = engine.current_drafter()
    pick = engine.make_pick(team, player)
    emit("pick_confirmed", {
        "round": pick.round_num,
        "pick": pick.pick_num,
        "player": pick.player.name,
        "position": pick.player.position.value,
    })

    # Continue with AI picks
    _advance_draft(sid)


def _emit_draft_complete(sid):
    """Emit final draft results."""
    draft = _active_drafts.get(sid)
    if not draft:
        return
    league = draft["league"]
    teams = []
    for t in league.teams:
        total_pts = sum(e.player.fantasy_points for e in t.starters())
        teams.append({
            "name": t.name,
            "draft_position": t.draft_position,
            "total_points": round(total_pts, 1),
            "roster": [
                {"player": e.player.name, "position": e.player.position.value,
                 "slot": e.slot.value, "points": round(e.player.fantasy_points, 1)}
                for e in t.roster
            ],
        })
    teams.sort(key=lambda t: t["total_points"], reverse=True)
    app.config["_last_league"] = league
    emit("draft_complete", {"teams": teams})
    del _active_drafts[sid]
```

**Step 2: Update draft.html interactive tab**

Add the interactive tab content:
- Draft status bar (round, pick number, "Your turn!" indicator)
- Two-column layout: left = available players (filterable table with pick buttons), right = your current roster
- Recommendations panel at top highlighting top 5 picks
- Draft log at bottom showing all picks so far

**Step 3: Update draft.js for WebSocket**

Add SocketIO client connection:
```javascript
// Interactive draft
let socket = null;

function startInteractiveDraft() {
    socket = io();
    const teamName = document.getElementById("team-name").value || "My Team";
    const draftPos = document.getElementById("draft-position").value;

    socket.emit("start_draft", {team_name: teamName, draft_position: parseInt(draftPos)});

    socket.on("ai_pick", (data) => {
        addToDraftLog(data);
    });

    socket.on("your_turn", (data) => {
        showYourTurn(data);
    });

    socket.on("pick_confirmed", (data) => {
        addToDraftLog(data);
    });

    socket.on("draft_complete", (data) => {
        showDraftResults(data);
    });

    socket.on("error", (data) => {
        alert(data.message);
    });
}

function pickPlayer(playerName) {
    socket.emit("user_pick", {player_name: playerName});
    document.getElementById("pick-status").textContent = "Waiting for other teams...";
}
```

Include SocketIO client script in the template: `<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>`

**Step 4: Test manually**

Run app, go to `/draft`, switch to Interactive tab, start draft. Verify: AI picks stream in, your turn shows recommendations, clicking a player makes the pick, draft completes.

**Step 5: Commit**

```bash
git add web/
git commit -m "feat: add interactive draft mode with WebSocket"
```

---

### Task 5: Live Draft Assistant Page

**Files:**
- Modify: `web/app.py` (add routes)
- Create: `web/templates/live_draft.html`

**Step 1: Add routes**

```python
@app.route("/live-draft")
def live_draft():
    """Live draft assistant page."""
    players = _load_and_prepare()
    return render_template("live_draft.html", players=players)


@app.route("/api/live-draft/pick", methods=["POST"])
def api_live_draft_pick():
    """Record an opponent's pick and return updated recommendations."""
    data = request.get_json()
    player_name = data.get("player_name")
    # Remove from session player pool
    session_players = app.config.get("_live_draft_players")
    if session_players is None:
        session_players = _load_and_prepare()
        app.config["_live_draft_players"] = session_players
    session_players = [p for p in session_players if p.name != player_name]
    app.config["_live_draft_players"] = session_players

    # Get recommendations
    from src.rankings import get_draft_recommendations, get_value_picks
    from src.models import RosterSlot
    needs = [RosterSlot.QB, RosterSlot.RB, RosterSlot.WR, RosterSlot.TE, RosterSlot.FLEX, RosterSlot.K, RosterSlot.DEF]
    recs = get_draft_recommendations(session_players, needs, num_recommendations=10)
    best_by_pos = {}
    for pos in Position:
        best = get_best_available_by_position(session_players, pos, count=3)
        best_by_pos[pos.value] = [{"name": p.name, "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1)} for p in best]

    return jsonify({
        "recommendations": [{"name": p.name, "position": p.position.value, "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1)} for p in recs],
        "best_by_position": best_by_pos,
        "available_count": len(session_players),
    })


@app.route("/api/live-draft/reset", methods=["POST"])
def api_live_draft_reset():
    """Reset the live draft player pool."""
    app.config.pop("_live_draft_players", None)
    return jsonify({"status": "reset"})
```

**Step 2: Create live_draft.html**

- Configuration panel: league size, your draft position
- Two-column layout: left = record opponent picks (search + click), right = recommendations
- Best available by position tables
- "Reset Draft" button

**Step 3: Test manually, then commit**

```bash
git add web/
git commit -m "feat: add live draft assistant page"
```

---

### Task 6: Team Manager Page

**Files:**
- Modify: `web/app.py` (add routes)
- Create: `web/templates/team.html`

**Step 1: Add routes**

Routes needed:
- `GET /team` — list saved leagues, select a team to manage
- `GET /api/team/<league_name>/<team_name>` — return team roster as JSON
- `POST /api/team/optimize` — optimize lineup for a team
- `POST /api/team/trade-eval` — evaluate a trade
- `GET /api/team/waivers/<league_name>/<team_name>` — get waiver recommendations

Use existing functions: `load_league()`, `optimize_lineup()`, `evaluate_trade()`, `get_waiver_recommendations()`.

**Step 2: Create team.html**

- League/team selector dropdowns (populated from `list_saves()`)
- Roster table with position badges, slot, points
- "Optimize Lineup" button → AJAX call → re-renders roster
- Waiver recommendations panel
- Trade evaluator: select players from two teams, see VBD analysis

**Step 3: Test manually, then commit**

```bash
git add web/
git commit -m "feat: add team manager page with roster, waivers, trades"
```

---

### Task 7: Backtest & Strategy Lab Page

**Files:**
- Modify: `web/app.py` (add routes + SocketIO events for progress)
- Create: `web/templates/backtest.html`
- Create: `web/static/js/backtest.js`

**Step 1: Add routes and SocketIO events**

```python
from src.backtest import run_backtest
from src.strategy_tuner import run_tuning, TunerResult
from src.backtest_report import export_results_csv, export_tuning_csv
from src.data_scraper import scrape_season
import json as json_lib

@app.route("/backtest")
def backtest():
    """Backtest & Strategy Lab page."""
    return render_template("backtest.html")


@socketio.on("run_backtest")
def handle_run_backtest(data):
    """Run backtest with progress updates via WebSocket."""
    seasons = data.get("seasons", [2024])
    iterations = int(data.get("iterations", 100))  # Default lower for web UX

    projection_players = _load_and_prepare()
    results_list = []

    for year in seasons:
        emit("backtest_status", {"message": f"Scraping {year} data..."})
        try:
            actual_players = scrape_season(year)
            score_all_players(actual_players)
        except Exception as e:
            emit("backtest_status", {"message": f"Error scraping {year}: {str(e)}. Using projections as actuals."})
            import copy
            actual_players = copy.deepcopy(projection_players)
            score_all_players(actual_players)

        emit("backtest_status", {"message": f"Running {iterations} drafts for {year}..."})
        config = StrategyConfig()
        result = run_backtest(projection_players, actual_players, config, iterations=iterations, season=year)
        results_list.append(result)

        # Save results
        results_dir = PROJECT_ROOT / "data" / "backtest_results"
        results_dir.mkdir(exist_ok=True)
        export_results_csv(result, str(results_dir / f"{year}_results.csv"))

    # Build chart data
    chart_data = {
        "seasons": [],
    }
    for r in results_list:
        chart_data["seasons"].append({
            "year": r.season,
            "vbd_mean": round(r.mean_vbd_points, 1),
            "adp_mean": round(r.mean_adp_points, 1),
            "random_mean": round(r.mean_random_points, 1),
            "bust_rate": round(r.mean_bust_rate * 100, 1),
            "hit_rate": round(r.mean_hit_rate * 100, 1),
            "by_position": {str(k): round(v, 1) for k, v in r.points_by_position.items()},
        })

    emit("backtest_complete", chart_data)


@socketio.on("run_tuner")
def handle_run_tuner(data):
    """Run strategy tuner with progress updates."""
    num_configs = int(data.get("num_configs", 50))  # Lower default for web
    search_iters = int(data.get("search_iterations", 50))
    seasons = data.get("seasons", [2024])

    projection_players = _load_and_prepare()
    proj_by_season = {}
    actual_by_season = {}

    for year in seasons:
        emit("tuner_status", {"message": f"Loading {year} data..."})
        proj_by_season[year] = projection_players
        try:
            actual = scrape_season(year)
            score_all_players(actual)
            actual_by_season[year] = actual
        except Exception:
            import copy
            actual_by_season[year] = copy.deepcopy(projection_players)
            score_all_players(actual_by_season[year])

    def progress_cb(current, total, phase):
        emit("tuner_status", {"message": f"{phase.title()}: {current}/{total}", "progress": current / total})

    emit("tuner_status", {"message": "Starting tuner..."})
    results = run_tuning(
        proj_by_season, actual_by_season,
        num_configs=num_configs,
        search_iterations=search_iters,
        validation_iterations=search_iters * 2,
        top_n=5,
        progress_callback=progress_cb,
    )

    # Save results
    results_dir = PROJECT_ROOT / "data" / "backtest_results"
    results_dir.mkdir(exist_ok=True)
    tuning_data = [{"config": r.config.to_dict(), "mean_points": r.mean_points, "iterations": r.iterations_run} for r in results]
    with open(results_dir / "tuning_results.json", "w") as f:
        json_lib.dump(tuning_data, f, indent=2)

    emit("tuner_complete", {
        "results": [
            {"rank": i + 1, "mean_points": round(r.mean_points, 1), "config": r.config.to_dict()}
            for i, r in enumerate(results)
        ]
    })
```

**Step 2: Create backtest.html**

- Tabs: "Run Backtest", "Run Tuner", "Results"
- Backtest tab: season checkboxes, iteration count input, "Run" button, progress bar, Plotly chart area
- Tuner tab: config count, iterations, "Run Tuner" button, progress bar, results table
- Results tab: list existing CSV/JSON files, download links

**Step 3: Create backtest.js**

Plotly chart rendering functions:
- `renderStrategyComparison(data)` — grouped bar chart: VBD vs ADP vs Random per season
- `renderDraftPositionHeatmap(data)` — heatmap: draft position (1-12) vs mean points
- `renderTunerResults(data)` — table of top 5 configs with parameters

WebSocket event handlers for progress updates and results rendering.

**Step 4: Test manually, then commit**

```bash
git add web/
git commit -m "feat: add backtest lab page with Plotly charts and strategy tuner"
```

---

### Task 8: Player Data Management Page

**Files:**
- Modify: `web/app.py` (add routes)
- Create: `web/templates/players.html`

**Step 1: Add routes**

```python
@app.route("/players")
def players_page():
    """Player data management page."""
    players = _load_and_prepare()
    return render_template("players.html", players=players)


@app.route("/api/players/update", methods=["POST"])
def api_update_player():
    """Update a player's stats."""
    data = request.get_json()
    players = load_players()
    for p in players:
        if p.name == data["name"]:
            if "team" in data:
                p.team = data["team"]
            if "projected_stats" in data:
                for k, v in data["projected_stats"].items():
                    if hasattr(p.projected_stats, k):
                        setattr(p.projected_stats, k, float(v))
            break
    save_players(players)
    return jsonify({"status": "updated"})


@app.route("/api/players/add", methods=["POST"])
def api_add_player():
    """Add a new player."""
    data = request.get_json()
    players = load_players()
    from src.models import ProjectedStats
    new_player = Player(
        name=data["name"],
        team=data["team"],
        position=Position(data["position"]),
        bye_week=int(data.get("bye_week", 0)),
        projected_stats=ProjectedStats(**{k: float(v) for k, v in data.get("projected_stats", {}).items()}),
        adp=float(data.get("adp", 200)),
    )
    players.append(new_player)
    save_players(players)
    return jsonify({"status": "added"})


@app.route("/api/players/delete", methods=["POST"])
def api_delete_player():
    """Remove a player."""
    data = request.get_json()
    players = load_players()
    players = [p for p in players if p.name != data["name"]]
    save_players(players)
    return jsonify({"status": "deleted"})
```

**Step 2: Create players.html**

- Searchable/sortable player table
- "Add Player" button → modal form
- Each row has "Edit" and "Delete" buttons
- Edit opens inline editing or a modal with stat fields

**Step 3: Test manually, then commit**

```bash
git add web/
git commit -m "feat: add player data management page"
```

---

### Task 9: Polish and Cross-Page Integration

**Files:**
- Modify: `web/static/css/style.css` (responsive refinements)
- Modify: `web/app.py` (save/load integration)
- Modify: `web/templates/base.html` (active page highlighting)

**Step 1: Add save/load functionality**

Add routes for saving/loading leagues that integrate with team manager and draft:
- `GET /api/saves` — list saved leagues
- `POST /api/saves` — save current league
- After draft completion, auto-prompt to save

**Step 2: Polish CSS**

- Ensure consistent spacing across all pages
- Mobile sidebar collapse at 768px
- Smooth transitions on tab switches and card reveals
- Loading spinners for AJAX calls

**Step 3: Add favicon and page titles**

Simple favicon (football emoji as SVG or similar). Each page has a specific `<title>`.

**Step 4: Full manual test pass**

Visit every page, test every feature:
- Dashboard: cards show correct counts
- Rankings: sort, filter, search all work
- Draft auto-sim: runs and displays results
- Draft interactive: WebSocket picks work
- Live draft: recording picks and recommendations work
- Team manager: roster displays, optimizer works
- Backtest lab: runs, charts render
- Player data: add, edit, delete work

**Step 5: Commit**

```bash
git add web/
git commit -m "feat: polish UI, add save/load integration, responsive fixes"
```

---

### Task 10: Final Verification and Push

**Step 1: Run all existing Python tests**

Run: `pytest tests/ -v`
Expected: All 54 tests still pass (web frontend doesn't affect backend logic)

**Step 2: Start app and smoke test**

Run: `python web/app.py`
Navigate through all pages, verify no errors in browser console.

**Step 3: Push**

```bash
git push origin master
```
