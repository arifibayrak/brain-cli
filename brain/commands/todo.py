import typer
from datetime import date, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from brain.core import db, files, git_sync

console = Console()
app = typer.Typer(help="Manage todos",
                  context_settings={"allow_interspersed_args": True})


@app.callback(invoke_without_command=True)
def todo(
    ctx: typer.Context,
    title: str = typer.Argument(None, help="Task title or complex input (AI will parse)"),
    project: str = typer.Option("", "--project", "-p"),
    priority: str = typer.Option("", "--priority", "-P", help="p1/p2/p3 (AI sets if omitted)"),
    due: str = typer.Option("", "--due", "-d", help="Due date override (YYYY-MM-DD / today / tomorrow)"),
    category: str = typer.Option("", "--category", "-c", help="Category override"),
    done: str = typer.Option(None, "--done", help="Mark todo ID as done"),
    delete: str = typer.Option(None, "--delete", help="Delete a todo by ID"),
    list_: bool = typer.Option(False, "--list", help="List active todos"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Skip AI analysis, add as-is"),
):
    if ctx.invoked_subcommand:
        return

    if done:
        _mark_done(done)
        return

    if delete:
        d = db.get_db()
        d.execute("DELETE FROM todos WHERE id = ?", [delete])
        d.conn.commit()
        git_sync.auto_commit("brain: todo deleted")
        console.print(f"[dim]Deleted todo {delete}[/dim]")
        return

    if list_:
        _show_todos()
        return

    if not title:
        # No argument given → open interactive multi-line input (avoids shell quoting entirely)
        console.print("[dim]Enter your task (paste multi-line freely, press Enter twice or Ctrl+D when done):[/dim]")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        title = "\n".join(lines).strip()
        if not title:
            _show_todos()
            return

    if no_ai:
        _add_single(title, priority or "p2", project, _parse_due(due), category, "", "", "")
        return

    # AI-powered analysis
    with console.status("[cyan]Analyzing with AI...[/cyan]"):
        try:
            from brain.core.ai import analyze_todos
            existing_cats = db.get_categories()
            todos = analyze_todos(title, existing_categories=existing_cats)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return
        except Exception as e:
            console.print(f"[yellow]AI unavailable ({e}), adding as plain todo[/yellow]")
            todos = [{"title": title, "priority": priority or "p2", "category": category,
                      "due_date": "", "due_time": "", "due_end_time": "", "context": "", "project": project}]

    # Apply any manual overrides
    for t in todos:
        if priority:
            t["priority"] = priority
        if due:
            t["due_date"] = _parse_due(due)
        if category:
            t["category"] = category
        if project:
            t["project"] = project

    # Insert all parsed todos
    created = []
    for t in todos:
        row = db.add_todo(
            title=t.get("title", title),
            priority=t.get("priority", "p2"),
            project=t.get("project", project),
            due_date=t.get("due_date", ""),
            context=t.get("context", ""),
            category=t.get("category", ""),
            due_time=t.get("due_time", ""),
            due_end_time=t.get("due_end_time", ""),
        )
        files.append_to_daily("Tasks", f"[{row['priority'].upper()}] {row['title']}")
        created.append(row)

    git_sync.auto_commit("brain: todo(s) added")
    _show_created(created)


def _add_single(title, priority, project, due_date, category, context, due_time, due_end_time):
    row = db.add_todo(title=title, priority=priority, project=project,
                      due_date=due_date, category=category, context=context,
                      due_time=due_time, due_end_time=due_end_time)
    files.append_to_daily("Tasks", f"[{priority.upper()}] {title}")
    git_sync.auto_commit("brain: todo added")
    _show_created([row])


def _show_created(rows: list[dict]):
    if len(rows) == 1:
        r = rows[0]
        due_str = _format_due(r.get("due_date", ""), r.get("due_time", ""), r.get("due_end_time", ""))
        console.print(Panel(
            f"[green]✓[/green] [bold]{r['title']}[/bold]\n"
            f"[cyan]{r.get('category') or 'Uncategorized'}[/cyan]  "
            f"[{'red' if r['priority']=='p1' else 'yellow' if r['priority']=='p2' else 'dim'}]{r['priority'].upper()}[/{'red' if r['priority']=='p1' else 'yellow' if r['priority']=='p2' else 'dim'}]  "
            f"{'[magenta]' + due_str + '[/magenta]' if due_str else '[dim]no due date[/dim]'}\n"
            f"[dim]ID: {r['id']}{' · ' + r['context'] if r.get('context') else ''}[/dim]",
            title="[yellow]Todo added[/yellow]",
            border_style="yellow",
        ))
    else:
        table = Table(box=box.ROUNDED, border_style="green",
                      title=f"[green]✓ {len(rows)} todos created[/green]")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Title")
        table.add_column("Category", style="cyan")
        table.add_column("Pri", width=3)
        table.add_column("Due", style="magenta")

        for r in rows:
            due_str = _format_due(r.get("due_date", ""), r.get("due_time", ""), r.get("due_end_time", ""))
            pri = r["priority"]
            pri_fmt = f"[red]{pri.upper()}[/red]" if pri == "p1" else \
                      f"[yellow]{pri.upper()}[/yellow]" if pri == "p2" else \
                      f"[dim]{pri.upper()}[/dim]"
            table.add_row(r["id"], r["title"], r.get("category") or "—", pri_fmt, due_str or "—")

        console.print(table)


def _show_todos():
    todos = db.get_todos(status="todo")
    overdue = db.get_overdue_todos()
    overdue_ids = {t["id"] for t in overdue}
    today = date.today()

    table = Table(box=box.ROUNDED, border_style="yellow", show_header=True,
                  title="Active Todos")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Pri", width=3)
    table.add_column("Title")
    table.add_column("Category", style="cyan", max_width=20)
    table.add_column("Due")

    for t in todos:
        due_date = t.get("due_date", "")
        due_str = _format_due(due_date, t.get("due_time", ""), t.get("due_end_time", ""))
        is_overdue = t["id"] in overdue_ids

        # Color the due date by urgency
        if is_overdue:
            due_display = f"[bold red]{due_str} ⚠[/bold red]" if due_str else "[bold red]OVERDUE[/bold red]"
        elif due_date:
            days_left = (date.fromisoformat(due_date) - today).days
            if days_left <= 2:
                due_display = f"[red]{due_str}[/red]"
            elif days_left <= 7:
                due_display = f"[yellow]{due_str}[/yellow]"
            else:
                due_display = f"[dim]{due_str}[/dim]"
        else:
            due_display = "[dim]—[/dim]"

        title_str = f"[red]{t['title']}[/red]" if is_overdue else t["title"]
        pri = t["priority"]
        pri_fmt = f"[red]{pri.upper()}[/red]" if pri == "p1" else \
                  f"[yellow]{pri.upper()}[/yellow]" if pri == "p2" else \
                  f"[dim]{pri.upper()}[/dim]"

        table.add_row(t["id"], pri_fmt, title_str,
                      t.get("category") or "—", due_display)

    if todos:
        console.print(table)
        if overdue:
            console.print(f"[bold red]⚠ {len(overdue)} overdue[/bold red]")
        # Show category breakdown
        _show_category_summary(todos)
    else:
        console.print("[dim]No active todos[/dim]")


def _show_category_summary(todos: list[dict]):
    from collections import Counter
    cats = Counter(t.get("category") or "Uncategorized" for t in todos)
    if len(cats) > 1:
        parts = "  ".join(f"[cyan]{cat}[/cyan] [dim]({count})[/dim]"
                          for cat, count in cats.most_common())
        console.print(f"\n[dim]Categories:[/dim] {parts}")


def _format_due(due_date: str, due_time: str = "", due_end_time: str = "") -> str:
    if not due_date:
        return ""
    try:
        d = date.fromisoformat(due_date)
        today = date.today()
        days_diff = (d - today).days

        # Friendly date label
        if days_diff == 0:
            label = "Today"
        elif days_diff == 1:
            label = "Tomorrow"
        elif days_diff == -1:
            label = "Yesterday"
        elif 0 < days_diff <= 6:
            label = d.strftime("%A")           # "Monday"
        else:
            label = d.strftime("%b %d")        # "Apr 14"

        # Append time range if present
        if due_time and due_end_time:
            label += f" {due_time}–{due_end_time}"
        elif due_time:
            label += f" {due_time}"

        return label
    except ValueError:
        return due_date


def _parse_due(due: str) -> str:
    if not due:
        return ""
    due = due.lower().strip()
    if due == "today":
        return date.today().isoformat()
    if due == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    if due in ("next week", "nextweek"):
        return (date.today() + timedelta(days=7)).isoformat()
    return due


def _mark_done(query: str) -> None:
    """Mark done by ID or title substring. If multiple matches, show picker."""
    import re
    # Looks like an 8-char hex ID?
    if re.fullmatch(r"[0-9a-f]{8}", query):
        todos = list(db.get_db()["todos"].rows_where("id = ? AND status = 'todo'", [query]))
    else:
        todos = db.find_todos_by_title(query)

    if not todos:
        console.print(f"[red]No active todo matching '{query}'[/red]")
        return

    if len(todos) == 1:
        t = todos[0]
        db.complete_todo(t["id"])
        git_sync.auto_commit("brain: todo completed")
        console.print(f"[green]✓[/green] [bold]{t['title']}[/bold] [dim]done[/dim]")
        return

    # Multiple matches — show picker
    console.print(f"[yellow]Multiple matches for '{query}':[/yellow]")
    for i, t in enumerate(todos, 1):
        due = _format_due(t.get("due_date",""), t.get("due_time",""), t.get("due_end_time",""))
        console.print(f"  [dim]{i}.[/dim] [{t['priority'].upper()}] {t['title']}"
                      + (f"  [dim]{due}[/dim]" if due else ""))
    choice = console.input("\nMark done (number): ").strip()
    try:
        t = todos[int(choice) - 1]
        db.complete_todo(t["id"])
        git_sync.auto_commit("brain: todo completed")
        console.print(f"[green]✓[/green] [bold]{t['title']}[/bold] [dim]done[/dim]")
    except (ValueError, IndexError):
        console.print("[dim]Cancelled[/dim]")


def interactive_done() -> None:
    """Show numbered todo list and let user pick one or more to complete."""
    todos = db.get_todos(status="todo")
    overdue = db.get_overdue_todos()
    overdue_ids = {t["id"] for t in overdue}

    if not todos:
        console.print("[dim]No active todos[/dim]")
        return

    console.print()
    for i, t in enumerate(todos, 1):
        due = _format_due(t.get("due_date",""), t.get("due_time",""), t.get("due_end_time",""))
        is_overdue = t["id"] in overdue_ids
        pri = t["priority"]
        pri_fmt = (f"[red]{pri.upper()}[/red]" if pri == "p1" else
                   f"[yellow]{pri.upper()}[/yellow]" if pri == "p2" else
                   f"[dim]{pri.upper()}[/dim]")
        due_fmt = (f"[red]{due}[/red]" if is_overdue else f"[dim]{due}[/dim]") if due else ""
        console.print(f"  [dim]{i:2}.[/dim] {pri_fmt} {t['title']}"
                      + (f"  {due_fmt}" if due_fmt else ""))

    console.print()
    raw = console.input("[bold]Mark done[/bold] [dim](number, or 1 3 5 for multiple, or title):[/dim] ").strip()
    if not raw:
        console.print("[dim]Cancelled[/dim]")
        return

    # Try number(s) first
    parts = raw.split()
    completed = []
    if all(p.isdigit() for p in parts):
        for p in parts:
            idx = int(p) - 1
            if 0 <= idx < len(todos):
                t = todos[idx]
                db.complete_todo(t["id"])
                completed.append(t["title"])
    else:
        # Treat as title search
        matches = db.find_todos_by_title(raw)
        if matches:
            db.complete_todo(matches[0]["id"])
            completed.append(matches[0]["title"])
        else:
            console.print(f"[red]No match for '{raw}'[/red]")
            return

    git_sync.auto_commit("brain: todo(s) completed")
    for title in completed:
        console.print(f"[green]✓[/green] [bold]{title}[/bold] [dim]done[/dim]")
