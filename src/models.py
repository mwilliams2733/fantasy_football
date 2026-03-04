"""Data models for fantasy football."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Position(Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"


class RosterSlot(Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    FLEX = "FLEX"
    K = "K"
    DEF = "DEF"
    BENCH = "BENCH"


ROSTER_SLOTS = {
    RosterSlot.QB: 1,
    RosterSlot.RB: 2,
    RosterSlot.WR: 2,
    RosterSlot.TE: 1,
    RosterSlot.FLEX: 1,
    RosterSlot.K: 1,
    RosterSlot.DEF: 1,
    RosterSlot.BENCH: 6,
}

FLEX_ELIGIBLE = {Position.RB, Position.WR, Position.TE}

TOTAL_ROUNDS = 15


@dataclass
class ProjectedStats:
    """Season-long projected stats for a player."""
    pass_yards: float = 0.0
    pass_tds: float = 0.0
    interceptions: float = 0.0
    rush_yards: float = 0.0
    rush_tds: float = 0.0
    receptions: float = 0.0
    rec_yards: float = 0.0
    rec_tds: float = 0.0
    field_goals: float = 0.0
    extra_points: float = 0.0
    sacks: float = 0.0
    def_interceptions: float = 0.0
    def_tds: float = 0.0
    points_allowed_per_game: float = 0.0

    def to_dict(self) -> dict:
        return {
            "pass_yards": self.pass_yards,
            "pass_tds": self.pass_tds,
            "interceptions": self.interceptions,
            "rush_yards": self.rush_yards,
            "rush_tds": self.rush_tds,
            "receptions": self.receptions,
            "rec_yards": self.rec_yards,
            "rec_tds": self.rec_tds,
            "field_goals": self.field_goals,
            "extra_points": self.extra_points,
            "sacks": self.sacks,
            "def_interceptions": self.def_interceptions,
            "def_tds": self.def_tds,
            "points_allowed_per_game": self.points_allowed_per_game,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectedStats":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Player:
    """An NFL player with projected stats."""
    name: str
    team: str
    position: Position
    bye_week: int
    projected_stats: ProjectedStats = field(default_factory=ProjectedStats)
    adp: float = 200.0
    fantasy_points: float = 0.0
    vbd_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "team": self.team,
            "position": self.position.value,
            "bye_week": self.bye_week,
            "projected_stats": self.projected_stats.to_dict(),
            "adp": self.adp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        return cls(
            name=data["name"],
            team=data["team"],
            position=Position(data["position"]),
            bye_week=data["bye_week"],
            projected_stats=ProjectedStats.from_dict(data.get("projected_stats", {})),
            adp=data.get("adp", 200.0),
        )


@dataclass
class RosterEntry:
    """A player assigned to a roster slot."""
    player: Player
    slot: RosterSlot


@dataclass
class Team:
    """A fantasy team with roster."""
    name: str
    draft_position: int
    roster: list[RosterEntry] = field(default_factory=list)

    def players(self) -> list[Player]:
        return [entry.player for entry in self.roster]

    def starters(self) -> list[RosterEntry]:
        return [e for e in self.roster if e.slot != RosterSlot.BENCH]

    def bench(self) -> list[RosterEntry]:
        return [e for e in self.roster if e.slot == RosterSlot.BENCH]

    def position_count(self, pos: Position) -> int:
        return sum(1 for e in self.roster if e.player.position == pos)

    def starter_slots_filled(self) -> dict[RosterSlot, int]:
        counts: dict[RosterSlot, int] = {}
        for e in self.roster:
            if e.slot != RosterSlot.BENCH:
                counts[e.slot] = counts.get(e.slot, 0) + 1
        return counts

    def needs(self) -> list[RosterSlot]:
        """Return unfilled starter slots."""
        filled = self.starter_slots_filled()
        needed = []
        for slot, count in ROSTER_SLOTS.items():
            if slot == RosterSlot.BENCH:
                continue
            current = filled.get(slot, 0)
            for _ in range(count - current):
                needed.append(slot)
        return needed

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "draft_position": self.draft_position,
            "roster": [
                {"player_name": e.player.name, "slot": e.slot.value}
                for e in self.roster
            ],
        }


@dataclass
class DraftPick:
    """A single draft pick."""
    round_num: int
    pick_num: int
    team: Team
    player: Player


@dataclass
class League:
    """A fantasy league with teams and draft history."""
    name: str
    teams: list[Team] = field(default_factory=list)
    draft_picks: list[DraftPick] = field(default_factory=list)
    available_players: list[Player] = field(default_factory=list)

    def drafted_player_names(self) -> set[str]:
        return {pick.player.name for pick in self.draft_picks}

    def free_agents(self) -> list[Player]:
        """Players not on any team roster."""
        rostered = set()
        for team in self.teams:
            for entry in team.roster:
                rostered.add(entry.player.name)
        return [p for p in self.available_players if p.name not in rostered]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "teams": [t.to_dict() for t in self.teams],
            "draft_picks": [
                {
                    "round_num": dp.round_num,
                    "pick_num": dp.pick_num,
                    "team_name": dp.team.name,
                    "player_name": dp.player.name,
                }
                for dp in self.draft_picks
            ],
        }


@dataclass
class StrategyConfig:
    """Tunable parameters for the VBD draft strategy."""
    replacement_rank: dict = field(default_factory=lambda: {
        Position.QB: 1,
        Position.RB: 2.2,
        Position.WR: 2.2,
        Position.TE: 1.1,
        Position.K: 1,
        Position.DEF: 1,
    })
    need_boost: float = 1.15
    scarcity_penalty: float = 0.8
    round_1_2_bias: str = "BPA"
    round_3_5_bias: str = "BPA"
    qb_target_round: int = 6
    te_target_round: int = 5

    def to_dict(self) -> dict:
        return {
            "replacement_rank": {k.value: v for k, v in self.replacement_rank.items()},
            "need_boost": self.need_boost,
            "scarcity_penalty": self.scarcity_penalty,
            "round_1_2_bias": self.round_1_2_bias,
            "round_3_5_bias": self.round_3_5_bias,
            "qb_target_round": self.qb_target_round,
            "te_target_round": self.te_target_round,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyConfig":
        repl = {Position(k): v for k, v in data.get("replacement_rank", {}).items()}
        return cls(
            replacement_rank=repl if repl else cls().replacement_rank,
            need_boost=data.get("need_boost", 1.15),
            scarcity_penalty=data.get("scarcity_penalty", 0.8),
            round_1_2_bias=data.get("round_1_2_bias", "BPA"),
            round_3_5_bias=data.get("round_3_5_bias", "BPA"),
            qb_target_round=data.get("qb_target_round", 6),
            te_target_round=data.get("te_target_round", 5),
        )
