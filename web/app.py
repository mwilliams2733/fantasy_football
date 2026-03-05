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


@app.context_processor
def inject_pos_colors():
    return {"pos_colors": POS_COLORS}


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
