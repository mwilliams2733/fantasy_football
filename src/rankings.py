"""Value-Based Drafting (VBD) rankings engine."""

from src.models import Player, Position, ROSTER_SLOTS, RosterSlot, FLEX_ELIGIBLE


REPLACEMENT_RANK = {
    Position.QB: 1,
    Position.RB: 2.2,
    Position.WR: 2.2,
    Position.TE: 1.1,
    Position.K: 1,
    Position.DEF: 1,
}


def get_replacement_level(players: list[Player], position: Position, num_teams: int = 12) -> float:
    pos_players = sorted(
        [p for p in players if p.position == position],
        key=lambda p: p.fantasy_points,
        reverse=True,
    )
    replacement_index = int(num_teams * REPLACEMENT_RANK[position])
    if replacement_index >= len(pos_players):
        replacement_index = len(pos_players) - 1
    return pos_players[replacement_index].fantasy_points


def calculate_vbd(players: list[Player], num_teams: int = 12) -> list[Player]:
    replacement_levels: dict[Position, float] = {}
    for pos in Position:
        pos_players = [p for p in players if p.position == pos]
        if pos_players:
            replacement_levels[pos] = get_replacement_level(players, pos, num_teams)
        else:
            replacement_levels[pos] = 0.0
    for player in players:
        baseline = replacement_levels.get(player.position, 0.0)
        player.vbd_score = player.fantasy_points - baseline
    return sorted(players, key=lambda p: p.vbd_score, reverse=True)


def get_draft_recommendations(
    available: list[Player],
    team_needs: list[RosterSlot],
    num_recommendations: int = 5,
) -> list[Player]:
    scored: list[tuple[float, Player]] = []
    need_positions = set()
    for slot in team_needs:
        if slot == RosterSlot.FLEX:
            need_positions.update(FLEX_ELIGIBLE)
        elif slot != RosterSlot.BENCH:
            need_positions.add(Position(slot.value))
    for player in available:
        adj_score = player.vbd_score
        if player.position in need_positions:
            adj_score *= 1.15
        else:
            adj_score *= 0.8
        scored.append((adj_score, player))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [player for _, player in scored[:num_recommendations]]


def get_best_available_by_position(
    available: list[Player], position: Position, count: int = 5
) -> list[Player]:
    pos_players = [p for p in available if p.position == position]
    pos_players.sort(key=lambda p: p.vbd_score, reverse=True)
    return pos_players[:count]


def get_value_picks(available: list[Player], current_pick: int, count: int = 5) -> list[Player]:
    value_players = [
        p for p in available
        if p.adp < current_pick and p.vbd_score > 0
    ]
    value_players.sort(key=lambda p: (current_pick - p.adp) * p.vbd_score, reverse=True)
    return value_players[:count]
