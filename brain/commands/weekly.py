from collections import defaultdict
from datetime import date, timedelta

import typer
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.panel import Panel
from rich import box
from brain.core import db

console = Console()
app = typer.Typer(help="Weekly overview — todos, calendar, learnings")


@app.callback(invoke_without_command=True)
def weekly(
    ai_brief: bool = typer.Option(False, "--ai", help="Include AI-generated weekly insight"),
):
    today = date.today()
    week_end = today + timedelta(days=7)
    console.print(Rule(
        f"[bold cyan]🗓  Week of {today.strftime('%B %-d')} – {week_end.strftime('%B %-d, %Y')}[/bold cyan]"
    ))

    # ── Calendar ──────────────────────────────────────────────────────────────
    try:
        from brain.core.google_cal import get_upcoming_events, format_event_time, is_enabled
        if is_enabled():
            events = get_upcoming_events(days=7)
            if events:
                console.print(f"\n[bold blue]📅 Calendar[/bold blue]")
                by_day: dict = defaultdict(list)
                for ev in events:
                    by_day[ev["start"][:10]].append(ev)
                for day in sorted(by_day):
                    d = date.fromisoformat(day)
                    if d == today:
                        label = f"[bold]Today — {d.strftime('%A %-d %b')}[/bold]"
                    elif d == today + timedelta(days=1):
                        label = f"[bold]Tomorrow — {d.strftime('%A %-d %b')}[/bold]"
                    else:
                        label = f"[dim]{d.strftime('%A %-d %b')}[/dim]"
                    console.print(f"  {label}")
                    for ev in by_day[day]:
                        time_str = format_event_time(ev["start"])
                        console.print(f"    [blue]• {time_str}[/blue] {ev['summary']}")
            else:
                console.print("\n[dim]No calendar events this week[/dim]")
    except Exception:
        pass

    # ── Todos due this week ───────────────────────────────────────────────────
    todos = db.get_todos(status="todo")
    overdue = db.get_overdue_todos()
    overdue_ids = {t["id"] for t in overdue}
    today_str = today.isoformat()
    week_end_str = week_end.isoformat()

    due_this_week = [
        t for t in todos
        if t.get("due_date") and today_str <= t["due_date"] <= week_end_str
    ]
    no_date = [
        t for t in todos
        if not t.get("due_date") and t["id"] not in overdue_ids
    ]

    if overdue:
        console.print(f"\n[bold red]⚠  Overdue ({len(overdue)})[/bold red]")
        for t in overdue:
            console.print(f"  [red]• [{t['priority'].upper()}][/red] {t['title']} [dim]({t['due_date']})[/dim]")

    if due_this_week:
        console.print(f"\n[bold yellow]📋 Due This Week ({len(due_this_week)})[/bold yellow]")
        # Group by date
        by_date: dict = defaultdict(list)
        for t in due_this_week:
            by_date[t["due_date"]].append(t)
        for day in sorted(by_date):
            d = date.fromisoformat(day)
            label = "Today" if d == today else ("Tomorrow" if d == today + timedelta(days=1) else d.strftime("%A %-d %b"))
            console.print(f"  [dim]{label}[/dim]")
            for t in by_date[day]:
                pri = t["priority"]
                color = "red" if pri == "p1" else "yellow" if pri == "p2" else "dim"
                time_str = f" [dim]{t['due_time']}[/dim]" if t.get("due_time") else ""
                console.print(f"    [{color}]• [{pri.upper()}][/{color}] {t['title']}{time_str}")

    if no_date:
        console.print(f"\n[bold]📌 No Due Date ({len(no_date)})[/bold]")
        for t in no_date[:8]:
            pri = t["priority"]
            color = "red" if pri == "p1" else "yellow" if pri == "p2" else "dim"
            console.print(f"  [{color}]• [{pri.upper()}][/{color}] {t['title']}")
        if len(no_date) > 8:
            console.print(f"  [dim]... and {len(no_date) - 8} more[/dim]")

    # ── Learnings this week ───────────────────────────────────────────────────
    learned = db.get_learned(days=7)
    if learned:
        console.print(f"\n[bold magenta]💡 Learned This Week ({len(learned)})[/bold magenta]")
        for item in learned:
            created = item.get("created_at", "")
            time_str = created[11:16] if created and "T" in created else ""
            ts = f"[dim]{item['date']}{' ' + time_str if time_str else ''}[/dim]  "
            console.print(f"  {ts}[magenta]{item['topic']}:[/magenta] {item['insight'][:80]}")

    # ── Read-later queue ──────────────────────────────────────────────────────
    stats = db.get_stats()
    if stats["readlater_unread"]:
        console.print(f"\n[dim]📚 {stats['readlater_unread']} unread in read-later queue — [bold]brain url --list[/bold][/dim]")

    # ── AI insight ────────────────────────────────────────────────────────────
    if ai_brief:
        console.print(f"\n[bold cyan]✨ AI Weekly Insight[/bold cyan]")
        with console.status("Generating..."):
            try:
                from brain.core.ai import generate_daily_brief
                brief = generate_daily_brief(stats, todos, learned, [])
                console.print(Panel(brief, border_style="cyan"))
            except Exception as e:
                console.print(f"[dim]AI unavailable: {e}[/dim]")

    console.print(Rule(style="dim"))
