"""Flask web frontend for Fantasy Football Draft Tool."""

import sys
from pathlib import Path

# Add project root to path so src/ imports work
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

from src.models import Position, StrategyConfig, Team, League, TOTAL_ROUNDS, RosterSlot, FLEX_ELIGIBLE
from src.scoring import score_all_players
from src.rankings import calculate_vbd, get_best_available_by_position, get_draft_recommendations
from src.persistence import load_players, save_players, list_saves, load_league, save_league
from src.draft import DraftEngine
from src.team_manager import optimize_lineup, evaluate_trade
from src.waiver import get_waiver_recommendations
from src.scoring import calculate_fantasy_points

app = Flask(__name__)
app.secret_key = "fantasy-football-local"
socketio = SocketIO(app)

_active_drafts = {}

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
    _active_drafts[sid] = {
        "engine": engine, "league": league,
        "user_team": team_name, "user_pos": draft_position
    }
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
            # User's turn
            recs = engine.get_recommendations(team, count=10)
            available = sorted(engine.league.available_players,
                             key=lambda p: p.vbd_score, reverse=True)[:50]
            emit("your_turn", {
                "round": engine.current_round + 1,
                "pick": engine.overall_pick + 1,
                "recommendations": [
                    {"name": p.name, "position": p.position.value,
                     "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1), "adp": p.adp}
                    for p in recs
                ],
                "available": [
                    {"name": p.name, "position": p.position.value,
                     "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1), "adp": p.adp}
                    for p in available
                ],
                "roster": [
                    {"player": e.player.name, "position": e.player.position.value, "slot": e.slot.value}
                    for e in team.roster
                ],
            })
            return
        else:
            pick = engine.ai_pick(team)
            emit("ai_pick", {
                "round": pick.round_num, "pick": pick.pick_num,
                "team": pick.team.name, "player": pick.player.name,
                "position": pick.player.position.value,
            })
            socketio.sleep(0.3)

    # Draft complete
    _emit_draft_complete(sid)


@socketio.on("user_pick")
def handle_user_pick(data):
    sid = request.sid
    draft = _active_drafts.get(sid)
    if not draft:
        return
    engine = draft["engine"]
    player_name = data.get("player_name", "")

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
        "round": pick.round_num, "pick": pick.pick_num,
        "player": pick.player.name, "position": pick.player.position.value,
    })
    _advance_draft(sid)


def _emit_draft_complete(sid):
    draft = _active_drafts.get(sid)
    if not draft:
        return
    league = draft["league"]
    teams = []
    for t in league.teams:
        total_pts = sum(e.player.fantasy_points for e in t.starters())
        teams.append({
            "name": t.name, "draft_position": t.draft_position,
            "total_points": round(total_pts, 1),
            "roster": [
                {"player": e.player.name, "position": e.player.position.value,
                 "slot": e.slot.value, "points": round(e.player.fantasy_points, 1)}
                for e in t.roster
            ],
        })
    teams.sort(key=lambda t: t["total_points"], reverse=True)
    emit("draft_complete", {"teams": teams})
    del _active_drafts[sid]


@socketio.on("disconnect")
def handle_disconnect():
    _active_drafts.pop(request.sid, None)


# --- Live Draft Assistant ---

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

    session_players = app.config.get("_live_draft_players")
    if session_players is None:
        session_players = _load_and_prepare()
        app.config["_live_draft_players"] = session_players

    session_players = [p for p in session_players if p.name != player_name]
    app.config["_live_draft_players"] = session_players

    needs = [RosterSlot.QB, RosterSlot.RB, RosterSlot.WR, RosterSlot.TE,
             RosterSlot.FLEX, RosterSlot.K, RosterSlot.DEF]
    recs = get_draft_recommendations(session_players, needs, num_recommendations=10)
    best_by_pos = {}
    for pos in Position:
        best = get_best_available_by_position(session_players, pos, count=3)
        best_by_pos[pos.value] = [
            {"name": p.name, "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1)}
            for p in best
        ]

    return jsonify({
        "recommendations": [
            {"name": p.name, "position": p.position.value,
             "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1)}
            for p in recs
        ],
        "best_by_position": best_by_pos,
        "available_count": len(session_players),
    })


@app.route("/api/live-draft/recommendations", methods=["GET"])
def api_live_draft_recommendations():
    """Get current recommendations without modifying player pool."""
    session_players = app.config.get("_live_draft_players")
    if session_players is None:
        session_players = _load_and_prepare()
        app.config["_live_draft_players"] = session_players

    needs = [RosterSlot.QB, RosterSlot.RB, RosterSlot.WR, RosterSlot.TE,
             RosterSlot.FLEX, RosterSlot.K, RosterSlot.DEF]
    recs = get_draft_recommendations(session_players, needs, num_recommendations=10)
    best_by_pos = {}
    for pos in Position:
        best = get_best_available_by_position(session_players, pos, count=3)
        best_by_pos[pos.value] = [
            {"name": p.name, "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1)}
            for p in best
        ]

    return jsonify({
        "recommendations": [
            {"name": p.name, "position": p.position.value,
             "points": round(p.fantasy_points, 1), "vbd": round(p.vbd_score, 1)}
            for p in recs
        ],
        "best_by_position": best_by_pos,
        "available_count": len(session_players),
    })


@app.route("/api/live-draft/reset", methods=["POST"])
def api_live_draft_reset():
    """Reset the live draft player pool."""
    app.config.pop("_live_draft_players", None)
    return jsonify({"status": "reset"})


# --- Team Manager ---

@app.route("/team")
def team():
    """Team manager page."""
    saves = list_saves()
    return render_template("team.html", saves=saves)


@app.route("/api/team/roster", methods=["POST"])
def api_team_roster():
    """Get a team's roster from a saved league."""
    data = request.get_json()
    league_file = data.get("league_file")
    team_name = data.get("team_name")
    league = load_league(league_file)
    # Score players
    for t in league.teams:
        for e in t.roster:
            calculate_fantasy_points(e.player)
    # If team_name is a placeholder, just return team list
    team_obj = next((t for t in league.teams if t.name == team_name), None)
    team_names = [t.name for t in league.teams]
    if not team_obj:
        return jsonify({"error": "Team not found", "teams": team_names}), 404
    starters = team_obj.starters()
    starter_pts = sum(e.player.fantasy_points for e in starters)
    return jsonify({
        "team_name": team_obj.name,
        "roster": [
            {"player": e.player.name, "team": e.player.team, "position": e.player.position.value,
             "slot": e.slot.value, "points": round(e.player.fantasy_points, 1),
             "vbd": round(e.player.vbd_score, 1)}
            for e in team_obj.roster
        ],
        "starter_points": round(starter_pts, 1),
        "teams": team_names,
    })


@app.route("/api/team/optimize", methods=["POST"])
def api_team_optimize():
    """Optimize a team's lineup."""
    data = request.get_json()
    league_file = data.get("league_file")
    team_name = data.get("team_name")
    league = load_league(league_file)
    for t in league.teams:
        for e in t.roster:
            calculate_fantasy_points(e.player)
    team_obj = next((t for t in league.teams if t.name == team_name), None)
    if not team_obj:
        return jsonify({"error": "Team not found"}), 404
    new_lineup = optimize_lineup(team_obj)
    team_obj.roster = new_lineup
    save_league(league, league_file)
    starters = team_obj.starters()
    starter_pts = sum(e.player.fantasy_points for e in starters)
    return jsonify({
        "roster": [
            {"player": e.player.name, "team": e.player.team, "position": e.player.position.value,
             "slot": e.slot.value, "points": round(e.player.fantasy_points, 1),
             "vbd": round(e.player.vbd_score, 1)}
            for e in team_obj.roster
        ],
        "starter_points": round(starter_pts, 1),
    })


@app.route("/api/team/waivers", methods=["POST"])
def api_team_waivers():
    """Get waiver recommendations for a team."""
    data = request.get_json()
    league_file = data.get("league_file")
    team_name = data.get("team_name")
    league = load_league(league_file)
    for t in league.teams:
        for e in t.roster:
            calculate_fantasy_points(e.player)
    # Also score free agents
    if league.available_players:
        score_all_players(league.available_players)
        calculate_vbd(league.available_players)
    team_obj = next((t for t in league.teams if t.name == team_name), None)
    if not team_obj:
        return jsonify({"error": "Team not found"}), 404
    recs = get_waiver_recommendations(league, team_obj)
    return jsonify({
        "recommendations": [
            {"add": r["add"].name, "add_pos": r["add"].position.value,
             "add_pts": round(r["add"].fantasy_points, 1),
             "drop": r["drop"].name, "drop_pos": r["drop"].position.value,
             "drop_pts": round(r["drop"].fantasy_points, 1),
             "reason": r["reason"]}
            for r in recs
        ]
    })


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
