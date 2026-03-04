"""Save and load league state as JSON."""

import json
import os
from pathlib import Path
from src.models import Player, Team, League, RosterEntry, RosterSlot, DraftPick


SAVES_DIR = Path(__file__).parent.parent / "saves"
DATA_DIR = Path(__file__).parent.parent / "data"


def load_players(filepath: str | None = None) -> list[Player]:
    if filepath is None:
        filepath = str(DATA_DIR / "players.json")
    with open(filepath) as f:
        data = json.load(f)
    return [Player.from_dict(p) for p in data["players"]]


def save_players(players: list[Player], filepath: str | None = None) -> None:
    if filepath is None:
        filepath = str(DATA_DIR / "players.json")
    data = {"players": [p.to_dict() for p in players]}
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def save_league(league: League, filename: str | None = None) -> str:
    SAVES_DIR.mkdir(exist_ok=True)
    if filename is None:
        filename = f"{league.name.lower().replace(' ', '_')}.json"
    filepath = SAVES_DIR / filename
    data = league.to_dict()
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
    filepath = SAVES_DIR / filename
    with open(filepath) as f:
        data = json.load(f)
    available = [Player.from_dict(p) for p in data.get("all_players", [])]
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
    for pick_data in data.get("draft_picks", []):
        team = next((t for t in teams if t.name == pick_data["team_name"]), None)
        player_name = pick_data["player_name"]
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
    SAVES_DIR.mkdir(exist_ok=True)
    return [f.name for f in SAVES_DIR.glob("*.json")]
