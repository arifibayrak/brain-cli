import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from brain.core import db, git_sync

console = Console()
app = typer.Typer(help="Process inbox items")


@app.callback(invoke_without_command=True)
def process():
    items = db.inbox_items()
    if not items:
        console.print("[green]✓ Inbox is empty![/green]")
        return

    console.print(f"[cyan]Processing {len(items)} inbox item(s)...[/cyan]\n")
    processed = 0

    for item in items:
        console.print(Panel(
            f"[bold]{item['content']}[/bold]\n[dim]{item['created_at'][:16]} · type: {item['type']}[/dim]",
            title=f"[cyan]Item {processed + 1}/{len(items)}[/cyan]",
            border_style="cyan",
        ))

        action = Prompt.ask(
            "Action",
            choices=["note", "todo", "learned", "url", "skip", "delete", "quit"],
            default="note",
        )

        if action == "quit":
            break
        elif action == "skip":
            continue
        elif action == "delete":
            db.mark_capture_processed(item["id"])
            processed += 1
            continue
        elif action == "note":
            project = Prompt.ask("Project (optional)", default="")
            from brain.core import files
            files.write_note_file(
                title=item["content"][:60],
                content=item["content"],
                subfolder=f"projects/{project}" if project else "resources"
            )
            db.add_note(
                title=item["content"][:60],
                content=item["content"],
                project=project,
            )
        elif action == "todo":
            priority = Prompt.ask("Priority", choices=["p1", "p2", "p3"], default="p2")
            due = Prompt.ask("Due date (optional, YYYY-MM-DD)", default="")
            project = Prompt.ask("Project (optional)", default="")
            db.add_todo(item["content"], priority=priority, project=project, due_date=due)
        elif action == "learned":
            topic = Prompt.ask("Topic", default="general")
            db.add_learned(topic=topic, insight=item["content"])
            from brain.core import files
            files.write_learned_file(topic, item["content"])
        elif action == "url":
            # Already a URL type, just needs processing
            console.print("[dim]URL already in read-later queue[/dim]")

        db.mark_capture_processed(item["id"])
        processed += 1
        console.print(f"[green]✓ Processed[/green]\n")

    git_sync.auto_commit("brain: inbox processed")
    console.print(f"[green]✓ Processed {processed} item(s)[/green]")
