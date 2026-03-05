"""Matchup-based lineup optimizer with permutation search and Monte Carlo simulation."""

import random
from itertools import combinations
from dataclasses import dataclass, field
from src.models import (
    Player, Team, Position, RosterEntry, RosterSlot,
    ROSTER_SLOTS, FLEX_ELIGIBLE,
)


# --- Roster Rules ---

MAX_ROSTER = {Position.QB: 2, Position.K: 1, Position.DEF: 1}


def validate_roster_rules(team: Team) -> list[str]:
    """Check roster composition rules. Returns list of violation messages."""
    violations = []
    for pos, max_count in MAX_ROSTER.items():
        count = team.position_count(pos)
        if count > max_count:
            violations.append(f"Too many {pos.value}s: {count} (max {max_count})")
    return violations


# --- Matchup Adjustment ---

def get_matchup_multiplier(defense_rank: int) -> float:
    """Convert defense rank (1-32) to a projection multiplier.

    Rank 1 (best D): 0.84, Rank 16: 1.01, Rank 32 (worst D): 1.16
    """
    return 1.0 + (defense_rank - 17) * 0.01


def get_matchup_adjusted_points(
    player: Player, opponent: str, defense_rankings: dict[str, dict[str, int]]
) -> float:
    """Adjust a player's fantasy points based on opponent defense ranking."""
    pos_key = f"vs_{player.position.value}"
    opp_rankings = defense_rankings.get(opponent, {})
    rank = opp_rankings.get(pos_key, 16)  # Default to average if unknown
    multiplier = get_matchup_multiplier(rank)
    return player.fantasy_points * multiplier


# --- Lineup Permutations ---

def generate_lineup_permutations(team: Team) -> list[list[RosterEntry]]:
    """Generate all valid starter lineup permutations.

    Fixed slots filled by best at each position. FLEX is the variable —
    tries every eligible RB/WR/TE not already starting.
    Returns list of complete rosters (starters + bench).
    """
    roster = team.roster
    players_by_pos: dict[Position, list[RosterEntry]] = {}
    for e in roster:
        players_by_pos.setdefault(e.player.position, []).append(e)

    # Sort each position group by points descending
    for pos in players_by_pos:
        players_by_pos[pos].sort(key=lambda e: e.player.fantasy_points, reverse=True)

    # Fixed starters: best at each required slot
    fixed_starters: list[RosterEntry] = []
    used_names: set[str] = set()

    slot_positions = [
        (RosterSlot.QB, Position.QB, ROSTER_SLOTS[RosterSlot.QB]),
        (RosterSlot.RB, Position.RB, ROSTER_SLOTS[RosterSlot.RB]),
        (RosterSlot.WR, Position.WR, ROSTER_SLOTS[RosterSlot.WR]),
        (RosterSlot.TE, Position.TE, ROSTER_SLOTS[RosterSlot.TE]),
        (RosterSlot.K, Position.K, ROSTER_SLOTS[RosterSlot.K]),
        (RosterSlot.DEF, Position.DEF, ROSTER_SLOTS[RosterSlot.DEF]),
    ]

    for slot, pos, count in slot_positions:
        candidates = [e for e in players_by_pos.get(pos, []) if e.player.name not in used_names]
        for c in candidates[:count]:
            fixed_starters.append(RosterEntry(player=c.player, slot=slot))
            used_names.add(c.player.name)

    # FLEX candidates: eligible players not already starting
    flex_candidates = [
        e for e in roster
        if e.player.position in FLEX_ELIGIBLE and e.player.name not in used_names
    ]

    if not flex_candidates:
        # Only one lineup possible
        bench = [
            RosterEntry(player=e.player, slot=RosterSlot.BENCH)
            for e in roster if e.player.name not in used_names
        ]
        return [fixed_starters + bench]

    # Generate one permutation per FLEX candidate
    permutations = []
    for flex_entry in flex_candidates:
        lineup = list(fixed_starters)
        lineup.append(RosterEntry(player=flex_entry.player, slot=RosterSlot.FLEX))
        flex_used = used_names | {flex_entry.player.name}
        bench = [
            RosterEntry(player=e.player, slot=RosterSlot.BENCH)
            for e in roster if e.player.name not in flex_used
        ]
        permutations.append(lineup + bench)

    return permutations


# --- Lineup Evaluation ---

@dataclass
class LineupEvaluation:
    """Result of evaluating a single lineup variant."""
    total_points: float
    players: list[dict]  # [{name, slot, base_pts, adjusted_pts, opponent, matchup_grade}]


@dataclass
class MonteCarloResult:
    """Result of Monte Carlo simulation on a lineup."""
    mean: float
    floor: float  # 10th percentile
    ceiling: float  # 90th percentile
    consistency: float  # % of sims above league average


@dataclass
class LineupRecommendation:
    """A recommended lineup with evaluation and Monte Carlo stats."""
    lineup: list[RosterEntry]
    evaluation: LineupEvaluation
    monte_carlo: MonteCarloResult


def evaluate_lineup(
    lineup: list[RosterEntry],
    opponent_map: dict[str, str],  # {player_team: opponent_team}
    defense_rankings: dict[str, dict[str, int]],
) -> LineupEvaluation:
    """Score a lineup using matchup-adjusted projections."""
    total = 0.0
    players = []
    for entry in lineup:
        if entry.slot == RosterSlot.BENCH:
            continue
        p = entry.player
        opponent = opponent_map.get(p.team, "")
        base_pts = p.fantasy_points
        adj_pts = get_matchup_adjusted_points(p, opponent, defense_rankings) if opponent else base_pts

        # Matchup grade
        pos_key = f"vs_{p.position.value}"
        rank = defense_rankings.get(opponent, {}).get(pos_key, 16) if opponent else 16
        if rank <= 8:
            grade = "tough"
        elif rank <= 24:
            grade = "neutral"
        else:
            grade = "favorable"

        total += adj_pts
        players.append({
            "name": p.name,
            "slot": entry.slot.value,
            "position": p.position.value,
            "base_pts": round(base_pts, 1),
            "adjusted_pts": round(adj_pts, 1),
            "opponent": opponent or "BYE",
            "matchup_grade": grade,
        })

    return LineupEvaluation(total_points=round(total, 1), players=players)


def monte_carlo_lineup(
    lineup: list[RosterEntry],
    opponent_map: dict[str, str],
    defense_rankings: dict[str, dict[str, int]],
    simulations: int = 500,
) -> MonteCarloResult:
    """Run Monte Carlo simulation on a lineup with random variance."""
    sim_totals = []
    for _ in range(simulations):
        total = 0.0
        for entry in lineup:
            if entry.slot == RosterSlot.BENCH:
                continue
            p = entry.player
            opponent = opponent_map.get(p.team, "")
            base = get_matchup_adjusted_points(p, opponent, defense_rankings) if opponent else p.fantasy_points
            # Add variance: normal distribution with 15% stddev
            varied = max(0, random.gauss(base, base * 0.15))
            total += varied
        sim_totals.append(total)

    sim_totals.sort()
    n = len(sim_totals)
    floor_idx = max(0, int(n * 0.10) - 1)
    ceiling_idx = min(n - 1, int(n * 0.90))
    mean = sum(sim_totals) / n
    # League average: ~110 pts/week for a 9-starter lineup
    league_avg = 110.0
    consistency = sum(1 for t in sim_totals if t >= league_avg) / n * 100

    return MonteCarloResult(
        mean=round(mean, 1),
        floor=round(sim_totals[floor_idx], 1),
        ceiling=round(sim_totals[ceiling_idx], 1),
        consistency=round(consistency, 1),
    )


def optimize_with_matchups(
    team: Team,
    week: int,
    schedule: dict[str, list[str | None]],
    defense_rankings: dict[str, dict[str, int]],
) -> dict:
    """Main entry point: find optimal lineup for a given week.

    Returns dict with recommended_lineup, alternatives, and analysis.
    """
    # Build opponent map for this week
    opponent_map: dict[str, str] = {}
    for team_abbrev, opponents in schedule.items():
        week_idx = week - 1
        if week_idx < len(opponents) and opponents[week_idx] is not None:
            opponent_map[team_abbrev] = opponents[week_idx]

    # Generate all valid lineup permutations
    permutations = generate_lineup_permutations(team)

    # Evaluate each permutation
    evaluations: list[tuple[list[RosterEntry], LineupEvaluation]] = []
    for lineup in permutations:
        ev = evaluate_lineup(lineup, opponent_map, defense_rankings)
        evaluations.append((lineup, ev))

    # Sort by total matchup-adjusted points descending
    evaluations.sort(key=lambda x: x[1].total_points, reverse=True)

    # Take top 3 and run Monte Carlo
    recommendations: list[LineupRecommendation] = []
    for lineup, ev in evaluations[:3]:
        mc = monte_carlo_lineup(lineup, opponent_map, defense_rankings)
        recommendations.append(LineupRecommendation(lineup=lineup, evaluation=ev, monte_carlo=mc))

    # Sort final recommendations by Monte Carlo mean
    recommendations.sort(key=lambda r: r.monte_carlo.mean, reverse=True)

    recommended = recommendations[0] if recommendations else None
    alternatives = recommendations[1:] if len(recommendations) > 1 else []

    return {
        "recommended": _recommendation_to_dict(recommended) if recommended else None,
        "alternatives": [_recommendation_to_dict(a) for a in alternatives],
        "week": week,
        "roster_violations": validate_roster_rules(team),
    }


def _recommendation_to_dict(rec: LineupRecommendation) -> dict:
    """Convert a LineupRecommendation to a JSON-serializable dict."""
    return {
        "total_points": rec.evaluation.total_points,
        "players": rec.evaluation.players,
        "monte_carlo": {
            "mean": rec.monte_carlo.mean,
            "floor": rec.monte_carlo.floor,
            "ceiling": rec.monte_carlo.ceiling,
            "consistency": rec.monte_carlo.consistency,
        },
    }
