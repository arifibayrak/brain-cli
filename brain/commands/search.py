import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from brain.core import db

console = Console()
app = typer.Typer(help="Search your brain")


@app.callback(invoke_without_command=True)
def search(
    query: str = typer.Argument(..., help="Search query"),
    notes: bool = typer.Option(True, "--notes/--no-notes"),
    todos: bool = typer.Option(True, "--todos/--no-todos"),
    learned: bool = typer.Option(True, "--learned/--no-learned"),
    urls: bool = typer.Option(True, "--urls/--no-urls"),
    limit: int = typer.Option(5, "--limit", "-n"),
):
    console.print(f"[cyan]Searching for:[/cyan] [bold]{query}[/bold]\n")
    found_any = False

    if notes:
        results = db.search_notes_fts(query, limit=limit)
        if results:
            found_any = True
            table = Table(box=box.SIMPLE, title="[bold]Notes[/bold]", border_style="green")
            table.add_column("ID", style="dim", width=8)
            table.add_column("Title")
            table.add_column("Project", style="cyan")
            for r in results:
                table.add_row(r["id"], r["title"], r.get("project") or "—")
            console.print(table)

    if todos:
        d = db.get_db()
        results = list(d["todos"].rows_where(
            "title LIKE ? AND status = 'todo'", [f"%{query}%"], limit=limit
        ))
        if results:
            found_any = True
            table = Table(box=box.SIMPLE, title="[bold]Todos[/bold]", border_style="yellow")
            table.add_column("ID", style="dim", width=8)
            table.add_column("Title")
            table.add_column("Priority")
            table.add_column("Due", style="magenta")
            for r in results:
                table.add_row(r["id"], r["title"], r["priority"], r["due_date"] or "—")
            console.print(table)

    if learned:
        d = db.get_db()
        results = list(d["learned"].search(query, limit=limit)) if hasattr(d["learned"], "search") else \
                  list(d["learned"].rows_where("topic LIKE ? OR insight LIKE ?",
                                               [f"%{query}%", f"%{query}%"], limit=limit))
        if results:
            found_any = True
            table = Table(box=box.SIMPLE, title="[bold]Learned[/bold]", border_style="magenta")
            table.add_column("Date", style="dim")
            table.add_column("Topic", style="bold magenta")
            table.add_column("Insight")
            for r in results:
                table.add_row(r["date"], r["topic"], r["insight"][:80])
            console.print(table)

    if urls:
        d = db.get_db()
        results = list(d["readlater"].rows_where(
            "title LIKE ? OR summary LIKE ?", [f"%{query}%", f"%{query}%"], limit=limit
        ))
        if results:
            found_any = True
            table = Table(box=box.SIMPLE, title="[bold]Read Later[/bold]", border_style="blue")
            table.add_column("ID", style="dim", width=8)
            table.add_column("Title")
            table.add_column("Status", style="cyan")
            for r in results:
                table.add_row(r["id"], r["title"][:60] or r["url"][:60], r["status"])
            console.print(table)

    if not found_any:
        console.print(f"[dim]No results found for '{query}'[/dim]")
