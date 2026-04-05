import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from brain.core import db, files, git_sync

console = Console()
app = typer.Typer(help="Log what you learned")


@app.callback(invoke_without_command=True)
def learned(
    ctx: typer.Context,
    entry: str = typer.Argument(None, help="'topic: insight' or just insight"),
    project: str = typer.Option("", "--project", "-p"),
    list_: bool = typer.Option(False, "--list", help="Show recent learnings"),
    days: int = typer.Option(7, "--days", "-d"),
):
    if ctx.invoked_subcommand:
        return

    if list_:
        _show_learned(days)
        return

    if not entry:
        console.print("[dim]Enter topic: insight (or just your insight, press Enter twice or Ctrl+D when done):[/dim]")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        entry = "\n".join(lines).strip()
        if not entry:
            _show_learned(days)
            return

    # Parse "topic: insight" format
    if ":" in entry and not entry.startswith("http"):
        parts = entry.split(":", 1)
        topic = parts[0].strip()
        insight = parts[1].strip()
    else:
        topic = "general"
        insight = entry

    row = db.add_learned(topic, insight, project=project)
    files.write_learned_file(topic, insight)
    files.append_to_daily("Learned", f"**{topic}**: {insight}")
    git_sync.auto_commit("brain: learned entry added")

    recorded_at = row.get("created_at", "")
    time_str = recorded_at[11:16] if recorded_at and "T" in recorded_at else ""
    console.print(Panel(
        f"[green]✓[/green] [bold]{topic}[/bold]\n{insight}\n"
        f"[dim]ID: {row['id']} · {db.today_str()}{' ' + time_str if time_str else ''}[/dim]",
        title="[magenta]Learning logged[/magenta]",
        border_style="magenta",
    ))


def _show_learned(days: int):
    items = db.get_learned(days=days)
    if not items:
        console.print(f"[dim]No learnings in the last {days} days[/dim]")
        return

    table = Table(box=box.ROUNDED, border_style="magenta", title=f"Last {days} days")
    table.add_column("Recorded", style="dim", width=16)
    table.add_column("Topic", style="bold magenta")
    table.add_column("Insight")

    for item in items:
        # Show date + time (HH:MM) from created_at; fall back to date only
        created = item.get("created_at", "")
        if created and "T" in created:
            dt_part = created[11:16]  # HH:MM
            timestamp = f"{item['date']} {dt_part}"
        else:
            timestamp = item["date"]
        table.add_row(timestamp, item["topic"], item["insight"])

    console.print(table)
