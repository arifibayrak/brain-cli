import typer
from rich.console import Console
from rich.panel import Panel
from brain.core import db, files, git_sync

console = Console()
app = typer.Typer(help="Add a note to your inbox")


@app.callback(invoke_without_command=True)
def add(
    content: str = typer.Argument(None, help="Note content (omit to type multi-line)"),
    project: str = typer.Option("", "--project", "-p", help="Project name"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
):
    if not content:
        console.print("[dim]Enter your note (press Enter twice or Ctrl+D when done):[/dim]")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        content = "\n".join(lines).strip()
        if not content:
            return

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    row = db.add_capture(content, type_="note", raw_input=content)
    files.ensure_dirs()
    files.append_to_daily("Notes", content)
    git_sync.auto_commit("brain: note added")

    console.print(Panel(
        f"[green]✓[/green] [bold]{content[:80]}[/bold]\n"
        f"[dim]ID: {row['id']} · inbox · {db.today_str()}[/dim]",
        title="[cyan]Note captured[/cyan]",
        border_style="cyan",
    ))
