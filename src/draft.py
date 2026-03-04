"""Snake draft engine for mock drafts and live draft assistance."""

import random
from src.models import (
    Player, Team, League, DraftPick, Position,
    RosterSlot, ROSTER_SLOTS, FLEX_ELIGIBLE, TOTAL_ROUNDS, RosterEntry,
)
from src.rankings import (
    calculate_vbd, get_draft_recommendations,
    get_best_available_by_position, get_value_picks,
)


def generate_snake_order(num_teams: int, num_rounds: int) -> list[list[int]]:
    order = []
    for round_num in range(num_rounds):
        if round_num % 2 == 0:
            order.append(list(range(1, num_teams + 1)))
        else:
            order.append(list(range(num_teams, 0, -1)))
    return order


def auto_assign_slot(player: Player, team: Team) -> RosterSlot:
    filled = team.starter_slots_filled()
    pos_to_slot = {
        Position.QB: RosterSlot.QB,
        Position.RB: RosterSlot.RB,
        Position.WR: RosterSlot.WR,
        Position.TE: RosterSlot.TE,
        Position.K: RosterSlot.K,
        Position.DEF: RosterSlot.DEF,
    }
    natural_slot = pos_to_slot[player.position]
    if filled.get(natural_slot, 0) < ROSTER_SLOTS.get(natural_slot, 0):
        return natural_slot
    if player.position in FLEX_ELIGIBLE:
        if filled.get(RosterSlot.FLEX, 0) < ROSTER_SLOTS[RosterSlot.FLEX]:
            return RosterSlot.FLEX
    return RosterSlot.BENCH


class DraftEngine:
    def __init__(self, league: League):
        self.league = league
        self.snake_order = generate_snake_order(len(league.teams), TOTAL_ROUNDS)
        self.current_round = 0
        self.current_pick_in_round = 0
        self.overall_pick = 0

    @property
    def is_draft_complete(self) -> bool:
        return self.current_round >= TOTAL_ROUNDS

    def current_drafter(self) -> Team | None:
        if self.is_draft_complete:
            return None
        pos = self.snake_order[self.current_round][self.current_pick_in_round]
        return next(t for t in self.league.teams if t.draft_position == pos)

    def make_pick(self, team: Team, player: Player) -> DraftPick:
        self.overall_pick += 1
        slot = auto_assign_slot(player, team)
        team.roster.append(RosterEntry(player=player, slot=slot))
        if player in self.league.available_players:
            self.league.available_players.remove(player)
        pick = DraftPick(
            round_num=self.current_round + 1,
            pick_num=self.overall_pick,
            team=team,
            player=player,
        )
        self.league.draft_picks.append(pick)
        self.current_pick_in_round += 1
        if self.current_pick_in_round >= len(self.league.teams):
            self.current_pick_in_round = 0
            self.current_round += 1
        return pick

    def ai_pick(self, team: Team) -> DraftPick:
        needs = team.needs()
        recommendations = get_draft_recommendations(
            self.league.available_players, needs, num_recommendations=10
        )
        if not recommendations:
            available_sorted = sorted(
                self.league.available_players,
                key=lambda p: p.vbd_score,
                reverse=True,
            )
            pick_player = available_sorted[0] if available_sorted else None
        else:
            top = recommendations[:3]
            weights = [3, 2, 1][:len(top)]
            pick_player = random.choices(top, weights=weights, k=1)[0]
        if pick_player:
            return self.make_pick(team, pick_player)
        raise ValueError("No players available to draft")

    def get_recommendations(self, team: Team, count: int = 5) -> list[Player]:
        needs = team.needs()
        return get_draft_recommendations(self.league.available_players, needs, count)

    def get_position_best(self, position: Position, count: int = 5) -> list[Player]:
        return get_best_available_by_position(self.league.available_players, position, count)

    def get_value_alerts(self, count: int = 5) -> list[Player]:
        return get_value_picks(self.league.available_players, self.overall_pick, count)
