"""Flask web frontend for Fantasy Football Draft Tool."""

import sys
from pathlib import Path

# Add project root to path so src/ imports work
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from src.models import Position, StrategyConfig, Team, League, TOTAL_ROUNDS
from src.scoring import score_all_players
from src.rankings import calculate_vbd, get_best_available_by_position
from src.persistence import load_players, save_players, list_saves, load_league, save_league
from src.draft import DraftEngine

app = Flask(__name__)
app.secret_key = "fantasy-football-local"
socketio = SocketIO(app)

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
    players = _load_and_prepare()
    saves = list_saves()
    return render_template("index.html", player_count=len(players), save_count=len(saves))


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


@app.context_processor
def inject_pos_colors():
    return {"pos_colors": POS_COLORS}


@app.route("/draft")
def draft():
    return render_template("draft.html")


@app.route("/api/draft/auto-sim", methods=["POST"])
def api_draft_auto_sim():
    data = request.get_json()
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
    return jsonify({"picks": picks, "teams": team_results})


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
