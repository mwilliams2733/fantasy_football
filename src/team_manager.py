"""Team management: roster moves, trades, free agency, lineup optimization."""

from src.models import (
    Player, Team, League, Position,
    RosterEntry, RosterSlot, ROSTER_SLOTS, FLEX_ELIGIBLE,
)
from src.draft import auto_assign_slot


def add_player(league: League, team: Team, player: Player, slot: RosterSlot | None = None) -> None:
    if slot is None:
        slot = auto_assign_slot(player, team)
    team.roster.append(RosterEntry(player=player, slot=slot))
    if player in league.available_players:
        league.available_players.remove(player)


def drop_player(league: League, team: Team, player: Player) -> None:
    team.roster = [e for e in team.roster if e.player.name != player.name]
    league.available_players.append(player)


def trade_players(
    league: League,
    team1: Team, players_from_team1: list[Player],
    team2: Team, players_from_team2: list[Player],
) -> None:
    for p in players_from_team1:
        team1.roster = [e for e in team1.roster if e.player.name != p.name]
    for p in players_from_team2:
        team2.roster = [e for e in team2.roster if e.player.name != p.name]
    for p in players_from_team1:
        slot = auto_assign_slot(p, team2)
        team2.roster.append(RosterEntry(player=p, slot=slot))
    for p in players_from_team2:
        slot = auto_assign_slot(p, team1)
        team1.roster.append(RosterEntry(player=p, slot=slot))


def evaluate_trade(
    team1: Team, players_from_team1: list[Player],
    team2: Team, players_from_team2: list[Player],
) -> dict:
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
    available = [
        e for e in team.roster
        if bye_week is None or e.player.bye_week != bye_week
    ]
    best_lineup: list[RosterEntry] = []
    used_players: set[str] = set()
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
    flex_candidates = [
        e for e in available
        if e.player.position in FLEX_ELIGIBLE and e.player.name not in used_players
    ]
    flex_candidates.sort(key=lambda e: e.player.fantasy_points, reverse=True)
    if flex_candidates:
        best_lineup.append(RosterEntry(player=flex_candidates[0].player, slot=RosterSlot.FLEX))
        used_players.add(flex_candidates[0].player.name)
    for e in team.roster:
        if e.player.name not in used_players:
            best_lineup.append(RosterEntry(player=e.player, slot=RosterSlot.BENCH))
    return best_lineup


def update_player_team(players: list[Player], player_name: str, new_team: str) -> bool:
    for p in players:
        if p.name.lower() == player_name.lower():
            p.team = new_team
            return True
    return False
