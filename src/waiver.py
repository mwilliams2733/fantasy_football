"""Waiver wire recommendation engine."""

from src.models import (
    Player, Team, League, Position,
    RosterSlot, FLEX_ELIGIBLE,
)


def get_waiver_recommendations(
    league: League,
    team: Team,
    max_recommendations: int = 10,
) -> list[dict]:
    free_agents = league.free_agents()
    if not free_agents:
        return []
    recommendations = []
    position_weakest: dict[Position, tuple[Player, RosterSlot]] = {}
    for entry in team.roster:
        if entry.slot == RosterSlot.BENCH:
            continue
        pos = entry.player.position
        if pos not in position_weakest or entry.player.fantasy_points < position_weakest[pos][0].fantasy_points:
            position_weakest[pos] = (entry.player, entry.slot)
    bench_players = sorted(
        [e.player for e in team.roster if e.slot == RosterSlot.BENCH],
        key=lambda p: p.fantasy_points,
    )
    for fa in sorted(free_agents, key=lambda p: p.vbd_score, reverse=True):
        if fa.position in position_weakest:
            weakest, slot = position_weakest[fa.position]
            upgrade = fa.fantasy_points - weakest.fantasy_points
            if upgrade > 10:
                drop_candidate = bench_players[0] if bench_players else weakest
                recommendations.append({
                    "add": fa,
                    "drop": drop_candidate,
                    "upgrade_score": upgrade,
                    "reason": f"Upgrades {fa.position.value}: {fa.name} ({fa.fantasy_points:.0f} pts) over {weakest.name} ({weakest.fantasy_points:.0f} pts)",
                })
        if bench_players:
            worst_bench = bench_players[0]
            if fa.fantasy_points > worst_bench.fantasy_points + 15:
                recommendations.append({
                    "add": fa,
                    "drop": worst_bench,
                    "upgrade_score": fa.fantasy_points - worst_bench.fantasy_points,
                    "reason": f"Bench upgrade: {fa.name} ({fa.fantasy_points:.0f} pts) over {worst_bench.name} ({worst_bench.fantasy_points:.0f} pts)",
                })
    seen = set()
    unique_recs = []
    for rec in sorted(recommendations, key=lambda r: r["upgrade_score"], reverse=True):
        if rec["add"].name not in seen:
            seen.add(rec["add"].name)
            unique_recs.append(rec)
    return unique_recs[:max_recommendations]
