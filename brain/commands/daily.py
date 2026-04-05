import typer
from datetime import date
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.table import Table
from rich.rule import Rule
from rich import box
from brain.core import db, files

console = Console()
app = typer.Typer(help="Show your daily brief")


@app.callback(invoke_without_command=True)
def daily(
    ai_brief: bool = typer.Option(False, "--ai", help="Include AI-generated insight"),
):
    today = date.today().strftime("%A, %B %d %Y")
    console.print(Rule(f"[bold cyan]🧠 Brain — {today}[/bold cyan]"))

    stats = db.get_stats()
    todos = db.get_todos(status="todo")
    overdue = db.get_overdue_todos()
    learned_today = db.get_learned(days=1)
    inbox_count = stats["inbox"]

    # --- Stats row ---
    panels = [
        Panel(f"[yellow]{stats['todos_active']}[/yellow]\n[dim]active tasks[/dim]", border_style="yellow"),
        Panel(f"[red]{stats['todos_overdue']}[/red]\n[dim]overdue[/dim]", border_style="red"),
        Panel(f"[blue]{stats['readlater_unread']}[/blue]\n[dim]to read[/dim]", border_style="blue"),
        Panel(f"[magenta]{stats['learned_today']}[/magenta]\n[dim]learned today[/dim]", border_style="magenta"),
        Panel(f"[dim]{inbox_count}[/dim]\n[dim]inbox[/dim]", border_style="dim"),
    ]
    console.print(Columns(panels))

    # --- Overdue todos ---
    if overdue:
        console.print(f"\n[bold red]⚠ Overdue ({len(overdue)})[/bold red]")
        for t in overdue[:5]:
            console.print(f"  [red]• [{t['priority'].upper()}][/red] {t['title']} [dim]({t['due_date']})[/dim]")

    # --- Today's todos ---
    today_str = date.today().isoformat()
    due_today = [t for t in todos if t.get("due_date") == today_str]
    if due_today:
        console.print(f"\n[bold yellow]📋 Due Today ({len(due_today)})[/bold yellow]")
        for t in due_today[:5]:
            console.print(f"  [yellow]• [{t['priority'].upper()}][/yellow] {t['title']}")

    # --- All active todos (if not too many) ---
    active_not_due = [t for t in todos if t.get("due_date") != today_str and t["id"] not in {o["id"] for o in overdue}]
    if active_not_due:
        console.print(f"\n[bold]📌 Active Tasks ({len(active_not_due)})[/bold]")
        for t in active_not_due[:5]:
            due = f" [dim]({t['due_date']})[/dim]" if t.get("due_date") else ""
            console.print(f"  • [{t['priority'].upper()}] {t['title']}{due}")
        if len(active_not_due) > 5:
            console.print(f"  [dim]... and {len(active_not_due) - 5} more[/dim]")

    # --- Learned today ---
    if learned_today:
        console.print(f"\n[bold magenta]💡 Learned Today[/bold magenta]")
        for item in learned_today:
            console.print(f"  [magenta]• {item['topic']}:[/magenta] {item['insight'][:80]}")

    # --- Google Calendar — today only ---
    try:
        from brain.core.google_cal import get_today_events, format_event_time, is_enabled
        if is_enabled():
            cal_today = get_today_events()
            console.print(f"\n[bold blue]📅 Today's Calendar[/bold blue]")
            if cal_today:
                for ev in cal_today:
                    time_str = format_event_time(ev["start"])
                    console.print(f"  [blue]• {time_str}[/blue] {ev['summary']}")
            else:
                console.print(f"  [dim]No events today[/dim]")
    except Exception:
        pass

    # --- Gmail unread ---
    try:
        from brain.core.gmail import is_enabled as gmail_enabled, get_unread
        if gmail_enabled():
            emails = get_unread(limit=3)
            unread_count_str = f"{len(emails)}+" if len(emails) == 3 else str(len(emails))
            console.print(f"\n[bold cyan]📬 Gmail — {unread_count_str} unread[/bold cyan]")
            if emails:
                for e in emails:
                    sender = e["from"].split("<")[0].strip().strip('"')[:20]
                    console.print(f"  [cyan]• [{sender}][/cyan] {e['subject'][:50]}  [dim]{e['date']}[/dim]")
            else:
                console.print("  [dim]Inbox clear[/dim]")
    except Exception:
        pass

    # --- Inbox ---
    if inbox_count > 0:
        console.print(f"\n[dim]📬 Inbox: {inbox_count} unprocessed — run [bold]brain process[/bold] to triage[/dim]")

    # --- AI brief ---
    if ai_brief:
        console.print(f"\n[bold cyan]✨ AI Insight[/bold cyan]")
        with console.status("Generating..."):
            try:
                from brain.core.ai import generate_daily_brief
                brief = generate_daily_brief(stats, todos, learned_today, [])
                console.print(Panel(brief, border_style="cyan"))
            except Exception as e:
                console.print(f"[dim]AI unavailable: {e}[/dim]")

    # --- Open daily note ---
    daily_path = files.get_or_create_daily_note()
    console.print(f"\n[dim]Daily note: {daily_path}[/dim]")
    console.print(Rule(style="dim"))
