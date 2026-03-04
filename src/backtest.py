"""Backtest engine for evaluating draft strategies against historical data."""

import copy
import random
from dataclasses import dataclass, field

from src.models import (
    Player, Team, League, Position, RosterSlot, RosterEntry,
    TOTAL_ROUNDS, StrategyConfig, ROSTER_SLOTS, FLEX_ELIGIBLE,
)
from src.scoring import score_all_players, calculate_fantasy_points
from src.rankings import calculate_vbd, get_draft_recommendations
from src.draft import DraftEngine, auto_assign_slot


@dataclass
class BacktestResult:
    """Result from a single draft simulation."""
    draft_position: int
    vbd_team_points: float
    adp_team_points: float
    random_team_points: float
    all_team_points: list[float]
    vbd_picks: list[dict]  # [{name, position, projected_pts, actual_pts}]
    bust_count: int = 0
    hit_count: int = 0


@dataclass
class SeasonBacktestResults:
    """Aggregated results from N iterations of backtesting."""
    season: int
    iterations: list[BacktestResult]
    config: StrategyConfig
    mean_vbd_points: float = 0.0
    mean_adp_points: float = 0.0
    mean_random_points: float = 0.0
    mean_bust_rate: float = 0.0
    mean_hit_rate: float = 0.0
    points_by_position: dict = field(default_factory=dict)


def compute_team_actual_points(team: Team, actual_lookup: dict[str, Player]) -> float:
    """Rescore a team using actual stats, finding optimal starter lineup.

    For each rostered player, look up their actual-stats version and calculate
    fantasy points. Then find the optimal starter lineup by actual points:
    1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (best remaining RB/WR/TE), 1 K, 1 DEF.
    Returns sum of the 9 starters' actual points.
    """
    # Calculate actual points for each rostered player
    player_actuals: list[tuple[Player, float]] = []
    for entry in team.roster:
        actual_player = actual_lookup.get(entry.player.name)
        if actual_player is not None:
            pts = calculate_fantasy_points(actual_player)
            player_actuals.append((actual_player, pts))

    # Group by position
    by_pos: dict[Position, list[tuple[Player, float]]] = {}
    for player, pts in player_actuals:
        by_pos.setdefault(player.position, []).append((player, pts))

    # Sort each position group by points descending
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: x[1], reverse=True)

    total = 0.0
    used: set[str] = set()

    # Pick optimal starters: 1 QB, 2 RB, 2 WR, 1 TE, 1 K, 1 DEF
    slot_needs = [
        (Position.QB, 1),
        (Position.RB, 2),
        (Position.WR, 2),
        (Position.TE, 1),
        (Position.K, 1),
        (Position.DEF, 1),
    ]

    for pos, count in slot_needs:
        candidates = by_pos.get(pos, [])
        picked = 0
        for player, pts in candidates:
            if picked >= count:
                break
            if player.name not in used:
                total += pts
                used.add(player.name)
                picked += 1

    # FLEX: best remaining RB/WR/TE not already starting
    flex_candidates = []
    for pos in FLEX_ELIGIBLE:
        for player, pts in by_pos.get(pos, []):
            if player.name not in used:
                flex_candidates.append((player, pts))
    flex_candidates.sort(key=lambda x: x[1], reverse=True)
    if flex_candidates:
        total += flex_candidates[0][1]

    return total


def _run_adp_draft(projection_players: list[Player], team_position: int) -> Team:
    """Run a draft where the target team always picks lowest ADP available.

    AI opponents use normal ai_pick. Returns the target team.
    """
    players = copy.deepcopy(projection_players)
    score_all_players(players)
    calculate_vbd(players)

    teams = [Team(name=f"Team{i}", draft_position=i) for i in range(1, 13)]
    league = League(name="ADP Draft", teams=teams, available_players=list(players))
    engine = DraftEngine(league, config=None)

    target_team = next(t for t in teams if t.draft_position == team_position)

    while not engine.is_draft_complete:
        current = engine.current_drafter()
        if current is None:
            break
        if current.draft_position == team_position:
            # Pick the player with the lowest (best) ADP
            available = sorted(league.available_players, key=lambda p: p.adp)
            if available:
                engine.make_pick(current, available[0])
            else:
                break
        else:
            engine.ai_pick(current)

    return target_team


def _run_random_draft(projection_players: list[Player], team_position: int) -> Team:
    """Run a draft where the target team picks randomly from top 30 by VBD.

    AI opponents use normal ai_pick. Returns the target team.
    """
    players = copy.deepcopy(projection_players)
    score_all_players(players)
    calculate_vbd(players)

    teams = [Team(name=f"Team{i}", draft_position=i) for i in range(1, 13)]
    league = League(name="Random Draft", teams=teams, available_players=list(players))
    engine = DraftEngine(league, config=None)

    target_team = next(t for t in teams if t.draft_position == team_position)

    while not engine.is_draft_complete:
        current = engine.current_drafter()
        if current is None:
            break
        if current.draft_position == team_position:
            # Pick randomly from top 30 available by VBD
            available = sorted(league.available_players, key=lambda p: p.vbd_score, reverse=True)
            top_30 = available[:min(30, len(available))]
            if top_30:
                pick = random.choice(top_30)
                engine.make_pick(current, pick)
            else:
                break
        else:
            engine.ai_pick(current)

    return target_team


def _get_replacement_points(actual_players: list[Player], position: Position) -> float:
    """Get the replacement-level actual points for a position."""
    pos_players = [p for p in actual_players if p.position == position]
    pos_players.sort(key=lambda p: p.fantasy_points, reverse=True)
    # Replacement level: roughly starter count * 12 teams
    starter_counts = {
        Position.QB: 12,
        Position.RB: 24,
        Position.WR: 24,
        Position.TE: 12,
        Position.K: 12,
        Position.DEF: 12,
    }
    idx = starter_counts.get(position, 12)
    if idx >= len(pos_players):
        idx = len(pos_players) - 1
    if idx < 0:
        return 0.0
    return pos_players[idx].fantasy_points


def run_single_draft(
    projection_players: list[Player],
    actual_players: list[Player],
    vbd_team_position: int,
    config: StrategyConfig,
) -> BacktestResult:
    """Run a single draft simulation comparing VBD, ADP, and random strategies.

    1. Deep-copy projection players, score/VBD them
    2. Run full VBD draft (all 12 AI teams using ai_pick with config)
    3. Rescore VBD team with actual stats
    4. Run ADP and random drafts for the same position, rescore both
    5. Compute bust/hit counts for VBD team picks
    """
    # VBD draft
    vbd_players = copy.deepcopy(projection_players)
    score_all_players(vbd_players)
    calculate_vbd(vbd_players, config=config)

    teams = [Team(name=f"Team{i}", draft_position=i) for i in range(1, 13)]
    league = League(name="VBD Draft", teams=teams, available_players=list(vbd_players))
    engine = DraftEngine(league, config=config)

    while not engine.is_draft_complete:
        current = engine.current_drafter()
        if current is None:
            break
        engine.ai_pick(current)

    vbd_team = next(t for t in teams if t.draft_position == vbd_team_position)

    # Build actual lookup
    actual_scored = copy.deepcopy(actual_players)
    score_all_players(actual_scored)
    actual_lookup = {p.name: p for p in actual_scored}

    # Rescore all teams with actuals
    all_team_points = []
    for t in teams:
        pts = compute_team_actual_points(t, actual_lookup)
        all_team_points.append(pts)

    vbd_team_points = compute_team_actual_points(vbd_team, actual_lookup)

    # Run ADP and random drafts
    adp_team = _run_adp_draft(projection_players, vbd_team_position)
    adp_team_points = compute_team_actual_points(adp_team, actual_lookup)

    random_team = _run_random_draft(projection_players, vbd_team_position)
    random_team_points = compute_team_actual_points(random_team, actual_lookup)

    # Compute bust/hit for VBD team picks
    # Precompute replacement levels and top-10 thresholds by position
    replacement_pts: dict[Position, float] = {}
    top_10_threshold: dict[Position, float] = {}
    for pos in Position:
        pos_actuals = sorted(
            [p for p in actual_scored if p.position == pos],
            key=lambda p: p.fantasy_points,
            reverse=True,
        )
        replacement_pts[pos] = _get_replacement_points(actual_scored, pos)
        if len(pos_actuals) >= 10:
            top_10_threshold[pos] = pos_actuals[9].fantasy_points
        elif pos_actuals:
            top_10_threshold[pos] = pos_actuals[-1].fantasy_points
        else:
            top_10_threshold[pos] = 0.0

    bust_count = 0
    hit_count = 0
    vbd_picks = []

    for entry in vbd_team.roster:
        player = entry.player
        actual = actual_lookup.get(player.name)
        actual_pts = actual.fantasy_points if actual else 0.0
        projected_pts = player.fantasy_points

        vbd_picks.append({
            "name": player.name,
            "position": player.position.value,
            "projected_pts": projected_pts,
            "actual_pts": actual_pts,
        })

        repl = replacement_pts.get(player.position, 0.0)
        if actual_pts < repl:
            bust_count += 1

        threshold = top_10_threshold.get(player.position, float("inf"))
        if actual_pts >= threshold:
            hit_count += 1

    return BacktestResult(
        draft_position=vbd_team_position,
        vbd_team_points=vbd_team_points,
        adp_team_points=adp_team_points,
        random_team_points=random_team_points,
        all_team_points=all_team_points,
        vbd_picks=vbd_picks,
        bust_count=bust_count,
        hit_count=hit_count,
    )


def run_backtest(
    projection_players: list[Player],
    actual_players: list[Player],
    config: StrategyConfig,
    iterations: int = 1000,
    season: int = 0,
) -> SeasonBacktestResults:
    """Run multiple draft simulations and aggregate results.

    Rotates draft position through 1-12 across iterations.
    Computes mean points, bust/hit rates, and points by draft position.
    """
    results_list: list[BacktestResult] = []
    position_points: dict[int, list[float]] = {i: [] for i in range(1, 13)}

    for i in range(iterations):
        team_pos = (i % 12) + 1
        result = run_single_draft(
            projection_players=projection_players,
            actual_players=actual_players,
            vbd_team_position=team_pos,
            config=config,
        )
        results_list.append(result)
        position_points[team_pos].append(result.vbd_team_points)

    # Aggregate
    n = len(results_list)
    mean_vbd = sum(r.vbd_team_points for r in results_list) / n if n else 0.0
    mean_adp = sum(r.adp_team_points for r in results_list) / n if n else 0.0
    mean_random = sum(r.random_team_points for r in results_list) / n if n else 0.0

    total_picks = sum(len(r.vbd_picks) for r in results_list)
    mean_bust = sum(r.bust_count for r in results_list) / total_picks if total_picks else 0.0
    mean_hit = sum(r.hit_count for r in results_list) / total_picks if total_picks else 0.0

    points_by_position = {}
    for pos in range(1, 13):
        pts_list = position_points[pos]
        points_by_position[pos] = sum(pts_list) / len(pts_list) if pts_list else 0.0

    return SeasonBacktestResults(
        season=season,
        iterations=results_list,
        config=config,
        mean_vbd_points=mean_vbd,
        mean_adp_points=mean_adp,
        mean_random_points=mean_random,
        mean_bust_rate=mean_bust,
        mean_hit_rate=mean_hit,
        points_by_position=points_by_position,
    )
