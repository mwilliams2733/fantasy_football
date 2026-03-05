"""Snake draft engine for mock drafts and live draft assistance."""

import random
from typing import Optional
from src.models import (
    Player, Team, League, DraftPick, Position,
    RosterSlot, ROSTER_SLOTS, FLEX_ELIGIBLE, TOTAL_ROUNDS, RosterEntry,
    StrategyConfig,
)
from src.rankings import (
    calculate_vbd, get_draft_recommendations,
    get_best_available_by_position, get_value_picks,
)
from src.matchup_optimizer import MAX_ROSTER


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
    def __init__(self, league: League, config: Optional[StrategyConfig] = None):
        self.league = league
        self.config = config
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

    def _apply_round_bias(self, recommendations: list[Player], team: Team) -> list[Player]:
        """Apply round-based positional biases from config."""
        if self.config is None:
            return recommendations

        current_round = self.current_round + 1  # 1-indexed

        # Determine bias for current round
        bias = "BPA"
        if current_round <= 2:
            bias = self.config.round_1_2_bias
        elif current_round <= 5:
            bias = self.config.round_3_5_bias

        # Apply positional bias multipliers
        scored = []
        for player in recommendations:
            adj = player.vbd_score
            if bias == "RB_heavy" and player.position == Position.RB:
                adj *= 1.2
            elif bias == "WR_heavy" and player.position == Position.WR:
                adj *= 1.2
            scored.append((adj, player))

        # QB target round: if haven't drafted QB by target round, boost QB
        if current_round >= self.config.qb_target_round:
            has_qb = any(e.player.position == Position.QB for e in team.roster)
            if not has_qb:
                scored = [(s * 1.3 if p.position == Position.QB else s, p) for s, p in scored]

        # TE target round: if haven't drafted TE by target round, boost TE
        if current_round >= self.config.te_target_round:
            has_te = any(e.player.position == Position.TE for e in team.roster)
            if not has_te:
                scored = [(s * 1.3 if p.position == Position.TE else s, p) for s, p in scored]

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    def _filter_roster_limits(self, players: list[Player], team: Team) -> list[Player]:
        """Filter out players that would exceed roster composition limits."""
        filtered = []
        for p in players:
            max_allowed = MAX_ROSTER.get(p.position)
            if max_allowed is not None and team.position_count(p.position) >= max_allowed:
                continue
            filtered.append(p)
        return filtered

    def ai_pick(self, team: Team) -> DraftPick:
        needs = team.needs()
        recommendations = get_draft_recommendations(
            self.league.available_players, needs, num_recommendations=10,
            config=self.config,
        )
        if not recommendations:
            available_sorted = sorted(
                self.league.available_players,
                key=lambda p: p.vbd_score,
                reverse=True,
            )
            recommendations = available_sorted[:10] if available_sorted else []
        else:
            recommendations = self._apply_round_bias(recommendations, team)

        # Filter out players that would violate roster limits
        filtered = self._filter_roster_limits(recommendations, team)

        if not filtered:
            # Fallback: pick any available player not violating limits
            fallback = self._filter_roster_limits(
                sorted(self.league.available_players, key=lambda p: p.vbd_score, reverse=True),
                team,
            )
            if fallback:
                filtered = fallback[:1]

        if not filtered:
            # Last resort: pick best available ignoring roster limits
            any_available = sorted(
                self.league.available_players,
                key=lambda p: p.vbd_score,
                reverse=True,
            )
            if not any_available:
                raise ValueError("No players available to draft")
            filtered = any_available[:1]

        top = filtered[:3]
        weights = [3, 2, 1][:len(top)]
        pick_player = random.choices(top, weights=weights, k=1)[0]
        return self.make_pick(team, pick_player)

    def get_recommendations(self, team: Team, count: int = 5) -> list[Player]:
        needs = team.needs()
        return get_draft_recommendations(
            self.league.available_players, needs, count, config=self.config,
        )

    def get_position_best(self, position: Position, count: int = 5) -> list[Player]:
        return get_best_available_by_position(self.league.available_players, position, count)

    def get_value_alerts(self, count: int = 5) -> list[Player]:
        return get_value_picks(self.league.available_players, self.overall_pick, count)
