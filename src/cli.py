"""Rich CLI interface for Fantasy Football Draft Tool & Team Manager."""

import sys
from pathlib import Path

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models import (
    Player,
    Team,
    League,
    Position,
    RosterSlot,
    ProjectedStats,
    StrategyConfig,
    TOTAL_ROUNDS,
)
from src.scoring import score_all_players
from src.rankings import (
    calculate_vbd,
    get_best_available_by_position,
)
from src.draft import DraftEngine
from src.team_manager import (
    add_player,
    drop_player,
    trade_players,
    evaluate_trade,
    optimize_lineup,
    update_player_team,
)
from src.waiver import get_waiver_recommendations
from src.persistence import load_players, save_players, save_league, load_league, list_saves
from src.data_scraper import scrape_season, scrape_preseason_adp, HISTORICAL_DIR
from src.backtest import run_backtest, SeasonBacktestResults
from src.strategy_tuner import run_tuning, generate_random_config, TunerResult
from src.backtest_report import (
    print_full_report, export_results_csv, export_tuning_csv,
    format_before_after, format_tuning_results,
)

console = Console()

# ── Position colour map ────────────────────────────────────────────────
POS_COLORS = {
    Position.QB: "red",
    Position.RB: "green",
    Position.WR: "blue",
    Position.TE: "yellow",
    Position.K: "magenta",
    Position.DEF: "cyan",
}


def pos_text(position: Position) -> Text:
    """Return a Rich Text object coloured by position."""
    return Text(position.value, style=POS_COLORS.get(position, "white"))


# ── Shared state ───────────────────────────────────────────────────────
_current_league: League | None = None
_all_players: list[Player] = []


def _load_and_prepare_players() -> list[Player]:
    """Load players, score them and calculate VBD."""
    players = load_players()
    score_all_players(players)
    calculate_vbd(players)
    return players


def _find_player_by_name(name: str, pool: list[Player]) -> Player | None:
    """Case-insensitive player lookup; supports partial match."""
    lower = name.strip().lower()
    # Exact match first
    for p in pool:
        if p.name.lower() == lower:
            return p
    # Partial / substring match
    matches = [p for p in pool if lower in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        console.print(f"[yellow]Multiple matches for '{name}':[/yellow]")
        for m in matches[:10]:
            console.print(f"  - {m.name} ({m.position.value}, {m.team})")
        return None
    return None


# ── Roster / draft-board display helpers ───────────────────────────────

def _show_roster_table(team: Team) -> None:
    table = Table(title=f"{team.name} Roster", show_lines=True)
    table.add_column("Slot", style="bold")
    table.add_column("Player")
    table.add_column("Pos")
    table.add_column("Team")
    table.add_column("Pts", justify="right")

    slot_order = [
        RosterSlot.QB, RosterSlot.RB, RosterSlot.WR, RosterSlot.TE,
        RosterSlot.FLEX, RosterSlot.K, RosterSlot.DEF, RosterSlot.BENCH,
    ]
    ordered = sorted(team.roster, key=lambda e: slot_order.index(e.slot))
    for entry in ordered:
        p = entry.player
        table.add_row(
            entry.slot.value,
            p.name,
            pos_text(p.position),
            p.team,
            f"{p.fantasy_points:.1f}",
        )
    console.print(table)


def _show_draft_board(league: League, last_n: int = 0) -> None:
    """Show the draft board (all picks, or only the last *last_n*)."""
    picks = league.draft_picks if last_n == 0 else league.draft_picks[-last_n:]
    table = Table(title="Draft Board", show_lines=True)
    table.add_column("Pick", justify="right")
    table.add_column("Round", justify="right")
    table.add_column("Team")
    table.add_column("Player")
    table.add_column("Pos")

    for dp in picks:
        table.add_row(
            str(dp.pick_num),
            str(dp.round_num),
            dp.team.name,
            dp.player.name,
            pos_text(dp.player.position),
        )
    console.print(table)


def _show_recommendations(engine: DraftEngine, team: Team) -> None:
    """Display draft recommendations for the user."""
    recs = engine.get_recommendations(team, count=5)
    table = Table(title="Top Recommendations", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Player")
    table.add_column("Pos")
    table.add_column("Team")
    table.add_column("Pts", justify="right")
    table.add_column("VBD", justify="right")
    table.add_column("ADP", justify="right")

    for i, p in enumerate(recs, 1):
        table.add_row(
            str(i), p.name, pos_text(p.position), p.team,
            f"{p.fantasy_points:.1f}", f"{p.vbd_score:.1f}", f"{p.adp:.0f}",
        )
    console.print(table)

    # Best available by position
    for position in Position:
        best = engine.get_position_best(position, count=3)
        if best:
            names = ", ".join(f"{p.name} ({p.fantasy_points:.0f})" for p in best)
            console.print(f"  Best {pos_text(position)}: {names}")

    # Value alerts
    alerts = engine.get_value_alerts(count=3)
    if alerts:
        console.print("\n[bold yellow]Value Alerts:[/bold yellow]")
        for p in alerts:
            console.print(
                f"  {p.name} ({p.position.value}) — ADP {p.adp:.0f}, "
                f"VBD {p.vbd_score:.1f}"
            )


def _grade_team(team: Team) -> str:
    total_vbd = sum(e.player.vbd_score for e in team.roster)
    if total_vbd > 80:
        return "A+"
    elif total_vbd > 60:
        return "A"
    elif total_vbd > 40:
        return "B+"
    elif total_vbd > 20:
        return "B"
    elif total_vbd > 0:
        return "C"
    else:
        return "D"


# ═══════════════════════════════════════════════════════════════════════
#  1. Mock Draft Simulator
# ═══════════════════════════════════════════════════════════════════════

def mock_draft() -> None:
    global _current_league, _all_players
    console.print(Panel("[bold]Mock Draft Simulator[/bold]", style="blue"))

    team_name = questionary.text("Your team name:", default="My Team").ask()
    if team_name is None:
        return
    draft_pos = questionary.text(
        "Your draft position (1-12):", default="1",
        validate=lambda v: v.isdigit() and 1 <= int(v) <= 12,
    ).ask()
    if draft_pos is None:
        return
    draft_pos = int(draft_pos)

    console.print("[dim]Loading players...[/dim]")
    players = _load_and_prepare_players()
    _all_players = list(players)

    ai_names = [
        "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot",
        "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima",
    ]
    teams: list[Team] = []
    for i in range(1, 13):
        if i == draft_pos:
            teams.append(Team(name=team_name, draft_position=i))
        else:
            teams.append(Team(name=f"Team {ai_names[i - 1]}", draft_position=i))

    league = League(name="Mock Draft", teams=teams, available_players=list(players))
    _current_league = league
    engine = DraftEngine(league)
    user_team = next(t for t in teams if t.draft_position == draft_pos)

    console.print(f"\n[green]Draft starting! You are picking #{draft_pos}.[/green]\n")

    while not engine.is_draft_complete:
        drafter = engine.current_drafter()
        if drafter is None:
            break

        round_num = engine.current_round + 1

        if drafter.name == user_team.name:
            # User's pick
            console.print(Panel(
                f"[bold green]Round {round_num} — Your Pick![/bold green]",
                style="green",
            ))
            _show_recommendations(engine, user_team)

            while True:
                pick_name = questionary.text(
                    "Enter player name to draft (or 'list <pos>' to browse):"
                ).ask()
                if pick_name is None:
                    return

                if pick_name.lower().startswith("list"):
                    parts = pick_name.split()
                    if len(parts) == 2:
                        try:
                            pos = Position(parts[1].upper())
                            best = engine.get_position_best(pos, count=10)
                            for p in best:
                                console.print(
                                    f"  {p.name} ({p.team}) — "
                                    f"Pts: {p.fantasy_points:.1f}, VBD: {p.vbd_score:.1f}"
                                )
                        except ValueError:
                            console.print("[red]Invalid position. Use QB, RB, WR, TE, K, DEF.[/red]")
                    else:
                        console.print("[yellow]Usage: list QB / list RB / ...[/yellow]")
                    continue

                player = _find_player_by_name(pick_name, league.available_players)
                if player is None:
                    console.print(f"[red]Player '{pick_name}' not found among available players.[/red]")
                    continue

                pick = engine.make_pick(user_team, player)
                console.print(
                    f"[bold green]You drafted {player.name} "
                    f"({player.position.value}, {player.team}) "
                    f"in round {pick.round_num}![/bold green]"
                )
                break
        else:
            # AI pick
            pick = engine.ai_pick(drafter)
            console.print(
                f"  Rd {round_num} — {drafter.name} picks "
                f"{pick.player.name} ({pick.player.position.value})"
            )

        # Show board after each complete round
        if engine.current_pick_in_round == 0 or engine.is_draft_complete:
            _show_draft_board(league, last_n=len(teams))

    # Final results
    console.print(Panel("[bold]Draft Complete![/bold]", style="green"))
    for t in teams:
        total_pts = sum(e.player.fantasy_points for e in t.roster)
        grade = _grade_team(t)
        console.print(f"\n[bold]{t.name}[/bold]  Grade: {grade}  Total Pts: {total_pts:.0f}")
        _show_roster_table(t)


# ═══════════════════════════════════════════════════════════════════════
#  2. Live Draft Assistant
# ═══════════════════════════════════════════════════════════════════════

def live_draft_assistant() -> None:
    global _current_league, _all_players
    console.print(Panel("[bold]Live Draft Assistant[/bold]", style="blue"))

    team_name = questionary.text("Your team name:", default="My Team").ask()
    if team_name is None:
        return
    draft_pos = questionary.text(
        "Your draft position (1-12):", default="1",
        validate=lambda v: v.isdigit() and 1 <= int(v) <= 12,
    ).ask()
    if draft_pos is None:
        return
    draft_pos = int(draft_pos)

    league_size = questionary.text(
        "League size:", default="12",
        validate=lambda v: v.isdigit() and 2 <= int(v) <= 20,
    ).ask()
    if league_size is None:
        return
    league_size = int(league_size)

    console.print("[dim]Loading players...[/dim]")
    players = _load_and_prepare_players()
    _all_players = list(players)

    teams: list[Team] = []
    for i in range(1, league_size + 1):
        if i == draft_pos:
            teams.append(Team(name=team_name, draft_position=i))
        else:
            teams.append(Team(name=f"Team {i}", draft_position=i))

    league = League(name="Live Draft", teams=teams, available_players=list(players))
    _current_league = league
    engine = DraftEngine(league)
    user_team = next(t for t in teams if t.draft_position == draft_pos)

    console.print(f"\n[green]Live draft assistant ready! You are position #{draft_pos}.[/green]")
    console.print("[dim]Type 'quit' at any prompt to stop.[/dim]\n")

    while not engine.is_draft_complete:
        drafter = engine.current_drafter()
        if drafter is None:
            break
        round_num = engine.current_round + 1
        pick_num = engine.overall_pick + 1

        if drafter.name == user_team.name:
            # User's turn
            console.print(Panel(
                f"[bold green]Round {round_num}, Pick {pick_num} — YOUR TURN[/bold green]",
                style="green",
            ))
            _show_recommendations(engine, user_team)
            console.print()
            _show_roster_table(user_team)

            while True:
                pick_name = questionary.text("Enter player you are drafting:").ask()
                if pick_name is None or pick_name.lower() == "quit":
                    return

                player = _find_player_by_name(pick_name, league.available_players)
                if player is None:
                    console.print(f"[red]Player '{pick_name}' not found among available players.[/red]")
                    continue

                engine.make_pick(user_team, player)
                console.print(
                    f"[bold green]Drafted: {player.name} ({player.position.value})[/bold green]"
                )
                _show_roster_table(user_team)
                break
        else:
            # Other team's pick
            console.print(
                f"[dim]Round {round_num}, Pick {pick_num} — "
                f"{drafter.name} (position {drafter.draft_position})[/dim]"
            )
            while True:
                pick_name = questionary.text(
                    f"Who did {drafter.name} pick?"
                ).ask()
                if pick_name is None or pick_name.lower() == "quit":
                    return

                player = _find_player_by_name(pick_name, league.available_players)
                if player is None:
                    console.print(f"[red]Player '{pick_name}' not found. Try again.[/red]")
                    continue

                engine.make_pick(drafter, player)
                console.print(
                    f"  {drafter.name} drafted {player.name} ({player.position.value})"
                )
                break

    console.print(Panel("[bold]Draft Complete![/bold]", style="green"))
    _show_roster_table(user_team)


# ═══════════════════════════════════════════════════════════════════════
#  3. Team Manager
# ═══════════════════════════════════════════════════════════════════════

def _select_team(league: League) -> Team | None:
    choices = [t.name for t in league.teams]
    name = questionary.select("Select a team:", choices=choices).ask()
    if name is None:
        return None
    return next(t for t in league.teams if t.name == name)


def team_manager() -> None:
    global _current_league
    if _current_league is None:
        console.print("[red]No league loaded. Run a draft or load a save first.[/red]")
        return

    league = _current_league

    while True:
        action = questionary.select(
            "Team Manager:",
            choices=[
                "View Roster",
                "Trade",
                "Add/Drop",
                "Optimize Lineup",
                "Waiver Recommendations",
                "Back",
            ],
        ).ask()
        if action is None or action == "Back":
            return

        if action == "View Roster":
            team = _select_team(league)
            if team:
                _show_roster_table(team)

        elif action == "Trade":
            _handle_trade(league)

        elif action == "Add/Drop":
            _handle_add_drop(league)

        elif action == "Optimize Lineup":
            _handle_optimize(league)

        elif action == "Waiver Recommendations":
            _handle_waivers(league)


def _handle_trade(league: League) -> None:
    console.print(Panel("[bold]Trade[/bold]", style="yellow"))
    team1 = _select_team(league)
    if team1 is None:
        return
    team2 = _select_team(league)
    if team2 is None:
        return
    if team1.name == team2.name:
        console.print("[red]Cannot trade with the same team.[/red]")
        return

    # Select players from team1
    t1_choices = [e.player.name for e in team1.roster]
    if not t1_choices:
        console.print(f"[red]{team1.name} has no players.[/red]")
        return
    t1_picks = questionary.checkbox(
        f"Select players FROM {team1.name}:", choices=t1_choices,
    ).ask()
    if not t1_picks:
        console.print("[yellow]No players selected. Trade cancelled.[/yellow]")
        return

    # Select players from team2
    t2_choices = [e.player.name for e in team2.roster]
    if not t2_choices:
        console.print(f"[red]{team2.name} has no players.[/red]")
        return
    t2_picks = questionary.checkbox(
        f"Select players FROM {team2.name}:", choices=t2_choices,
    ).ask()
    if not t2_picks:
        console.print("[yellow]No players selected. Trade cancelled.[/yellow]")
        return

    players1 = [e.player for e in team1.roster if e.player.name in t1_picks]
    players2 = [e.player for e in team2.roster if e.player.name in t2_picks]

    # Evaluate
    evaluation = evaluate_trade(team1, players1, team2, players2)
    table = Table(title="Trade Evaluation", show_lines=True)
    table.add_column("Metric")
    table.add_column(team1.name, justify="right")
    table.add_column(team2.name, justify="right")
    table.add_row("VBD Net", f"{evaluation['team1_net']:+.1f}", f"{evaluation['team2_net']:+.1f}")
    table.add_row("Pts Before", f"{evaluation['team1_before']:.0f}", f"{evaluation['team2_before']:.0f}")
    table.add_row("Pts After", f"{evaluation['team1_after']:.0f}", f"{evaluation['team2_after']:.0f}")
    console.print(table)

    confirm = questionary.confirm("Execute this trade?", default=False).ask()
    if confirm:
        trade_players(league, team1, players1, team2, players2)
        console.print("[green]Trade executed![/green]")
    else:
        console.print("[yellow]Trade cancelled.[/yellow]")


def _handle_add_drop(league: League) -> None:
    console.print(Panel("[bold]Add / Drop[/bold]", style="yellow"))
    team = _select_team(league)
    if team is None:
        return

    _show_roster_table(team)

    action = questionary.select("Action:", choices=["Add Player", "Drop Player", "Back"]).ask()
    if action is None or action == "Back":
        return

    if action == "Drop Player":
        if not team.roster:
            console.print("[red]Roster is empty.[/red]")
            return
        choices = [e.player.name for e in team.roster]
        name = questionary.select("Select player to drop:", choices=choices).ask()
        if name is None:
            return
        player = next(e.player for e in team.roster if e.player.name == name)
        drop_player(league, team, player)
        console.print(f"[green]Dropped {player.name}.[/green]")

    elif action == "Add Player":
        free = league.free_agents()
        if not free:
            console.print("[red]No free agents available.[/red]")
            return
        free_sorted = sorted(free, key=lambda p: p.vbd_score, reverse=True)
        top_agents = free_sorted[:20]

        choices = [f"{p.name} ({p.position.value}, {p.team}) — {p.fantasy_points:.0f} pts" for p in top_agents]
        selection = questionary.select("Select free agent to add:", choices=choices).ask()
        if selection is None:
            return
        idx = choices.index(selection)
        player = top_agents[idx]
        add_player(league, team, player)
        console.print(f"[green]Added {player.name} to {team.name}.[/green]")


def _handle_optimize(league: League) -> None:
    team = _select_team(league)
    if team is None:
        return

    bye_input = questionary.text(
        "Enter bye week to plan around (or leave blank):", default=""
    ).ask()
    bye_week = int(bye_input) if bye_input and bye_input.isdigit() else None

    optimized = optimize_lineup(team, bye_week)
    team.roster = optimized

    console.print(f"[green]Lineup optimized for {team.name}![/green]")
    _show_roster_table(team)


def _handle_waivers(league: League) -> None:
    team = _select_team(league)
    if team is None:
        return

    recs = get_waiver_recommendations(league, team)
    if not recs:
        console.print("[yellow]No waiver recommendations at this time.[/yellow]")
        return

    table = Table(title="Waiver Recommendations", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Add")
    table.add_column("Drop")
    table.add_column("Upgrade", justify="right")
    table.add_column("Reason")

    for i, rec in enumerate(recs, 1):
        table.add_row(
            str(i),
            f"{rec['add'].name} ({rec['add'].position.value})",
            f"{rec['drop'].name} ({rec['drop'].position.value})",
            f"{rec['upgrade_score']:.1f}",
            rec["reason"],
        )
    console.print(table)


# ═══════════════════════════════════════════════════════════════════════
#  4. Player Rankings
# ═══════════════════════════════════════════════════════════════════════

def player_rankings() -> None:
    console.print(Panel("[bold]Player Rankings (VBD)[/bold]", style="blue"))

    players = _load_and_prepare_players()

    filter_pos = questionary.select(
        "Filter by position?",
        choices=["All"] + [p.value for p in Position],
    ).ask()
    if filter_pos is None:
        return

    if filter_pos != "All":
        pos = Position(filter_pos)
        players = [p for p in players if p.position == pos]

    # Already sorted by VBD from calculate_vbd
    table = Table(title="Player Rankings", show_lines=True)
    table.add_column("Rank", justify="right")
    table.add_column("Name")
    table.add_column("Team")
    table.add_column("Pos")
    table.add_column("Projected Pts", justify="right")
    table.add_column("VBD", justify="right")
    table.add_column("ADP", justify="right")

    for i, p in enumerate(players[:50], 1):
        table.add_row(
            str(i),
            p.name,
            p.team,
            pos_text(p.position),
            f"{p.fantasy_points:.1f}",
            f"{p.vbd_score:.1f}",
            f"{p.adp:.0f}",
        )
    console.print(table)


# ═══════════════════════════════════════════════════════════════════════
#  5. Update Player Data
# ═══════════════════════════════════════════════════════════════════════

def update_player_data() -> None:
    console.print(Panel("[bold]Update Player Data[/bold]", style="blue"))

    players = load_players()

    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "Update player's team",
                "Add new player",
                "Remove player",
                "Back",
            ],
        ).ask()
        if action is None or action == "Back":
            return

        if action == "Update player's team":
            name = questionary.text("Player name:").ask()
            if name is None:
                continue
            new_team = questionary.text("New team abbreviation (e.g. KC, BUF):").ask()
            if new_team is None:
                continue
            if update_player_team(players, name, new_team.upper()):
                save_players(players)
                console.print(f"[green]Updated {name}'s team to {new_team.upper()}.[/green]")
            else:
                console.print(f"[red]Player '{name}' not found.[/red]")

        elif action == "Add new player":
            name = questionary.text("Player name:").ask()
            if name is None:
                continue
            team = questionary.text("Team abbreviation:").ask()
            if team is None:
                continue
            pos_val = questionary.select(
                "Position:", choices=[p.value for p in Position]
            ).ask()
            if pos_val is None:
                continue
            bye = questionary.text("Bye week:", validate=lambda v: v.isdigit()).ask()
            if bye is None:
                continue

            stats = ProjectedStats()

            position = Position(pos_val)
            if position == Position.QB:
                val = questionary.text("Projected pass yards:", default="0").ask()
                stats.pass_yards = float(val) if val else 0
                val = questionary.text("Projected pass TDs:", default="0").ask()
                stats.pass_tds = float(val) if val else 0
                val = questionary.text("Projected INTs:", default="0").ask()
                stats.interceptions = float(val) if val else 0
                val = questionary.text("Projected rush yards:", default="0").ask()
                stats.rush_yards = float(val) if val else 0
                val = questionary.text("Projected rush TDs:", default="0").ask()
                stats.rush_tds = float(val) if val else 0
            elif position in (Position.RB, Position.WR, Position.TE):
                val = questionary.text("Projected rush yards:", default="0").ask()
                stats.rush_yards = float(val) if val else 0
                val = questionary.text("Projected rush TDs:", default="0").ask()
                stats.rush_tds = float(val) if val else 0
                val = questionary.text("Projected receptions:", default="0").ask()
                stats.receptions = float(val) if val else 0
                val = questionary.text("Projected receiving yards:", default="0").ask()
                stats.rec_yards = float(val) if val else 0
                val = questionary.text("Projected receiving TDs:", default="0").ask()
                stats.rec_tds = float(val) if val else 0
            elif position == Position.K:
                val = questionary.text("Projected field goals:", default="0").ask()
                stats.field_goals = float(val) if val else 0
                val = questionary.text("Projected extra points:", default="0").ask()
                stats.extra_points = float(val) if val else 0
            elif position == Position.DEF:
                val = questionary.text("Projected sacks:", default="0").ask()
                stats.sacks = float(val) if val else 0
                val = questionary.text("Projected interceptions:", default="0").ask()
                stats.def_interceptions = float(val) if val else 0
                val = questionary.text("Projected defensive TDs:", default="0").ask()
                stats.def_tds = float(val) if val else 0
                val = questionary.text("Points allowed per game:", default="20").ask()
                stats.points_allowed_per_game = float(val) if val else 20

            new_player = Player(
                name=name,
                team=team.upper(),
                position=position,
                bye_week=int(bye),
                projected_stats=stats,
            )
            players.append(new_player)
            save_players(players)
            console.print(f"[green]Added {name} ({pos_val}, {team.upper()}).[/green]")

        elif action == "Remove player":
            name = questionary.text("Player name to remove:").ask()
            if name is None:
                continue
            found = _find_player_by_name(name, players)
            if found is None:
                console.print(f"[red]Player '{name}' not found.[/red]")
                continue
            confirm = questionary.confirm(
                f"Remove {found.name} ({found.position.value}, {found.team})?",
                default=False,
            ).ask()
            if confirm:
                players = [p for p in players if p.name != found.name]
                save_players(players)
                console.print(f"[green]Removed {found.name}.[/green]")
            else:
                console.print("[yellow]Cancelled.[/yellow]")


# ═══════════════════════════════════════════════════════════════════════
#  6. Save / Load League
# ═══════════════════════════════════════════════════════════════════════

def save_load_league() -> None:
    global _current_league, _all_players
    action = questionary.select(
        "Save / Load:",
        choices=["Save Current League", "Load League", "New (Clear)", "Back"],
    ).ask()
    if action is None or action == "Back":
        return

    if action == "Save Current League":
        if _current_league is None:
            console.print("[red]No league to save.[/red]")
            return
        path = save_league(_current_league)
        console.print(f"[green]League saved to {path}[/green]")

    elif action == "Load League":
        saves = list_saves()
        if not saves:
            console.print("[yellow]No saved leagues found.[/yellow]")
            return
        choice = questionary.select("Select a save:", choices=saves).ask()
        if choice is None:
            return
        _current_league = load_league(choice)
        # Re-score the players
        all_players_in_league: list[Player] = list(_current_league.available_players)
        for t in _current_league.teams:
            all_players_in_league.extend(t.players())
        score_all_players(all_players_in_league)
        calculate_vbd(all_players_in_league)
        _all_players = all_players_in_league
        console.print(f"[green]Loaded league: {_current_league.name}[/green]")

    elif action == "New (Clear)":
        _current_league = None
        _all_players = []
        console.print("[green]League cleared.[/green]")


# ═══════════════════════════════════════════════════════════════════════
#  7. Backtest & Strategy Lab
# ═══════════════════════════════════════════════════════════════════════

BACKTEST_RESULTS_DIR = Path(__file__).parent.parent / "data" / "backtest_results"


def _backtest_lab() -> None:
    """Submenu for backtesting and strategy tuning features."""
    console.print(Panel("[bold]Backtest & Strategy Lab[/bold]", style="blue"))

    while True:
        action = questionary.select(
            "Backtest & Strategy Lab:",
            choices=[
                "Run Backtest (current strategy)",
                "Run Strategy Tuner",
                "View Results",
                "Apply Best Strategy",
                "Back",
            ],
        ).ask()
        if action is None or action == "Back":
            return

        if action == "Run Backtest (current strategy)":
            _run_backtest_menu()
        elif action == "Run Strategy Tuner":
            _run_tuner_menu()
        elif action == "View Results":
            _view_results_menu()
        elif action == "Apply Best Strategy":
            _apply_best_strategy()


def _run_backtest_menu() -> None:
    """Run a backtest with the default strategy against historical data."""
    seasons = questionary.checkbox(
        "Select seasons to backtest:",
        choices=["2024", "2025"],
    ).ask()
    if not seasons:
        console.print("[yellow]No seasons selected.[/yellow]")
        return

    config = StrategyConfig()
    all_season_results: list[SeasonBacktestResults] = []

    for year_str in seasons:
        year = int(year_str)
        console.print(f"\n[dim]Scraping data for {year} season...[/dim]")

        try:
            actual_players = scrape_season(year)
        except Exception as exc:
            console.print(f"[red]Failed to scrape {year} season stats: {exc}[/red]")
            continue

        try:
            scrape_preseason_adp(year)
        except Exception as exc:
            console.print(f"[yellow]Warning: Could not fetch ADP data for {year}: {exc}[/yellow]")

        # Use current players.json as projection proxy
        try:
            projection_players = load_players()
        except Exception as exc:
            console.print(f"[red]Failed to load projection players: {exc}[/red]")
            continue

        console.print(f"[dim]Running 1000 backtest iterations for {year}...[/dim]")
        try:
            from rich.progress import Progress
            with Progress(console=console) as progress:
                task = progress.add_task(f"Backtesting {year}...", total=1)
                result = run_backtest(
                    projection_players=projection_players,
                    actual_players=actual_players,
                    config=config,
                    iterations=1000,
                    season=year,
                )
                progress.update(task, completed=1)
            all_season_results.append(result)
        except Exception as exc:
            console.print(f"[red]Backtest failed for {year}: {exc}[/red]")
            continue

    if not all_season_results:
        console.print("[red]No backtest results to display.[/red]")
        return

    print_full_report(all_season_results, console)

    export = questionary.confirm("Export results to CSV?", default=False).ask()
    if export:
        BACKTEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for result in all_season_results:
            filepath = str(BACKTEST_RESULTS_DIR / f"{result.season}_results.csv")
            export_results_csv(result, filepath)
            console.print(f"[green]Exported to {filepath}[/green]")


def _run_tuner_menu() -> None:
    """Run the strategy tuner with random search."""
    num_configs_str = questionary.text(
        "Number of configs to test:", default="200",
        validate=lambda v: v.isdigit() and int(v) > 0,
    ).ask()
    if num_configs_str is None:
        return
    num_configs = int(num_configs_str)

    search_iters_str = questionary.text(
        "Search iterations per config:", default="100",
        validate=lambda v: v.isdigit() and int(v) > 0,
    ).ask()
    if search_iters_str is None:
        return
    search_iters = int(search_iters_str)

    # Load data for available seasons
    projection_players_by_season: dict[int, list[Player]] = {}
    actual_players_by_season: dict[int, list[Player]] = {}

    seasons = questionary.checkbox(
        "Select seasons for tuning:",
        choices=["2024", "2025"],
    ).ask()
    if not seasons:
        console.print("[yellow]No seasons selected.[/yellow]")
        return

    for year_str in seasons:
        year = int(year_str)
        console.print(f"[dim]Loading data for {year}...[/dim]")
        try:
            actual_players = scrape_season(year)
            actual_players_by_season[year] = actual_players
        except Exception as exc:
            console.print(f"[red]Failed to scrape {year} season stats: {exc}[/red]")
            continue

        try:
            projection_players = load_players()
            projection_players_by_season[year] = projection_players
        except Exception as exc:
            console.print(f"[red]Failed to load projections: {exc}[/red]")
            continue

    if not projection_players_by_season:
        console.print("[red]No season data available for tuning.[/red]")
        return

    console.print(f"[dim]Running tuner with {num_configs} configs, {search_iters} iterations each...[/dim]")

    try:
        from rich.progress import Progress
        with Progress(console=console) as progress:
            search_task = progress.add_task("Search phase...", total=num_configs)
            validate_task = progress.add_task("Validation phase...", total=5, visible=False)

            def progress_callback(current: int, total: int, phase: str) -> None:
                if phase == "search":
                    progress.update(search_task, completed=current)
                elif phase == "validate":
                    progress.update(validate_task, visible=True, completed=current)

            tuner_results = run_tuning(
                projection_players_by_season=projection_players_by_season,
                actual_players_by_season=actual_players_by_season,
                num_configs=num_configs,
                search_iterations=search_iters,
                progress_callback=progress_callback,
            )
    except Exception as exc:
        console.print(f"[red]Tuning failed: {exc}[/red]")
        return

    if not tuner_results:
        console.print("[yellow]No tuning results produced.[/yellow]")
        return

    # Display top 5
    top_5 = tuner_results[:5]
    output = format_tuning_results(top_5)
    console.print(output)

    # Save tuning results to JSON
    BACKTEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    import json
    tuning_data = []
    for tr in tuner_results:
        tuning_data.append({
            "config": tr.config.to_dict(),
            "mean_points": tr.mean_points,
            "iterations_run": tr.iterations_run,
        })
    tuning_path = BACKTEST_RESULTS_DIR / "tuning_results.json"
    with open(tuning_path, "w") as f:
        json.dump(tuning_data, f, indent=2)
    console.print(f"[green]Tuning results saved to {tuning_path}[/green]")

    export = questionary.confirm("Export tuning results to CSV?", default=False).ask()
    if export:
        csv_path = str(BACKTEST_RESULTS_DIR / "tuning_results.csv")
        export_tuning_csv(tuner_results, csv_path)
        console.print(f"[green]Exported to {csv_path}[/green]")


def _view_results_menu() -> None:
    """View existing backtest result files."""
    if not BACKTEST_RESULTS_DIR.exists():
        console.print("[yellow]No backtest results directory found.[/yellow]")
        return

    files = sorted(
        [f.name for f in BACKTEST_RESULTS_DIR.iterdir()
         if f.suffix in (".json", ".csv")],
    )
    if not files:
        console.print("[yellow]No result files found.[/yellow]")
        return

    choice = questionary.select("Select a file to view:", choices=files + ["Back"]).ask()
    if choice is None or choice == "Back":
        return

    filepath = BACKTEST_RESULTS_DIR / choice
    try:
        with open(filepath) as f:
            content = f.read()
        console.print(Panel(content[:5000], title=choice, style="dim"))
        if len(content) > 5000:
            console.print(f"[dim]... (truncated, {len(content)} total characters)[/dim]")
    except Exception as exc:
        console.print(f"[red]Failed to read file: {exc}[/red]")


def _apply_best_strategy() -> None:
    """Load tuning results and apply the best strategy config."""
    import json

    tuning_path = BACKTEST_RESULTS_DIR / "tuning_results.json"
    if not tuning_path.exists():
        console.print("[red]No tuning results found. Run the Strategy Tuner first.[/red]")
        return

    try:
        with open(tuning_path) as f:
            tuning_data = json.load(f)
    except Exception as exc:
        console.print(f"[red]Failed to load tuning results: {exc}[/red]")
        return

    if not tuning_data:
        console.print("[red]Tuning results file is empty.[/red]")
        return

    best_entry = tuning_data[0]
    best_config = StrategyConfig.from_dict(best_entry["config"])
    best_pts = best_entry["mean_points"]

    current_config = StrategyConfig()
    # Use 0.0 as placeholder for current points since we don't have a backtest for it
    current_pts = 0.0

    output = format_before_after(current_config, best_config, current_pts, best_pts)
    console.print(output)

    confirm = questionary.confirm(
        "Apply this configuration as your strategy?", default=False
    ).ask()
    if confirm:
        BACKTEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        applied_path = BACKTEST_RESULTS_DIR / "applied_config.json"
        with open(applied_path, "w") as f:
            json.dump(best_config.to_dict(), f, indent=2)
        console.print(f"[green]Best strategy saved to {applied_path}[/green]")
    else:
        console.print("[yellow]Strategy not applied.[/yellow]")


# ═══════════════════════════════════════════════════════════════════════
#  Main Menu
# ═══════════════════════════════════════════════════════════════════════

BANNER = r"""
  ___          _                   ___         _   _          _ _
 | __|_ _ _ _ | |_ __ _ ____  _  | __|__  ___| |_| |__  __ _| | |
 | _/ _` | ' \|  _/ _` (_-< || | | _/ _ \/ _ \  _| '_ \/ _` | | |
 |_|\__,_|_||_|\__\__,_/__/\_, | |_|\___/\___/\__|_.__/\__,_|_|_|
                            |__/
        Draft Tool & Team Manager
"""


def main_menu() -> None:
    """Entry point — runs the main interactive menu loop."""
    console.print(Panel(BANNER, style="bold blue"))

    while True:
        try:
            choice = questionary.select(
                "Main Menu:",
                choices=[
                    "1. Mock Draft Simulator",
                    "2. Live Draft Assistant",
                    "3. Team Manager",
                    "4. Player Rankings",
                    "5. Update Player Data",
                    "6. Save/Load League",
                    "7. Backtest & Strategy Lab",
                    "8. Exit",
                ],
            ).ask()

            if choice is None or "8. Exit" in choice:
                console.print("[bold]Goodbye![/bold]")
                break
            elif "1. Mock Draft" in choice:
                mock_draft()
            elif "2. Live Draft" in choice:
                live_draft_assistant()
            elif "3. Team Manager" in choice:
                team_manager()
            elif "4. Player Rankings" in choice:
                player_rankings()
            elif "5. Update Player" in choice:
                update_player_data()
            elif "6. Save/Load" in choice:
                save_load_league()
            elif "7. Backtest" in choice:
                _backtest_lab()

        except KeyboardInterrupt:
            console.print("\n[yellow]Returning to main menu... (Ctrl+C again to exit)[/yellow]")
            try:
                continue
            except KeyboardInterrupt:
                console.print("\n[bold]Goodbye![/bold]")
                break
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
