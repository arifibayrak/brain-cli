import json
import typer
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from brain.core import db, git_sync

console = Console()
app = typer.Typer(help="Save URLs to read later")


@app.callback(invoke_without_command=True)
def url(
    ctx: typer.Context,
    link: str = typer.Argument(None, help="URL to save"),
    note: str = typer.Option("", "--note", "-n", help="Personal note about this URL"),
    project: str = typer.Option("", "--project", "-p"),
    no_summary: bool = typer.Option(False, "--no-summary", help="Skip AI summary"),
    list_: bool = typer.Option(False, "--list", help="List read-later queue"),
    file: str = typer.Option("", "--file", "-f", help="Bulk import: file with one URL per line"),
):
    if ctx.invoked_subcommand:
        return

    if file:
        _bulk_import(file, project=project, no_summary=no_summary)
        return

    if list_ or not link:
        _show_queue()
        return

    _save_one(link, project=project, no_summary=no_summary)


def _save_one(link: str, project: str = "", no_summary: bool = False) -> dict:
    """Save a single URL. Returns the db row."""
    # Always save immediately so it's never lost
    row = db.add_readlater(link, project=project)

    title = link
    summary = ""
    tags = []

    if not no_summary:
        with console.status("[cyan]Fetching and summarizing...[/cyan]"):
            try:
                fetched_title, content = _fetch_url(link)
                title = fetched_title
                if content:
                    try:
                        from brain.core.ai import summarize_url
                        result = summarize_url(title, content)
                        # Use AI short_title if available and page title is long
                        ai_title = result.get("short_title", "")
                        if ai_title and len(fetched_title) > 60:
                            title = ai_title
                        summary = result.get("summary", "")
                        tags = result.get("tags", [])
                    except Exception as e:
                        console.print(f"[dim]AI summary skipped: {e}[/dim]")
                if title or summary or tags:
                    db.update_readlater(row["id"], title=title, summary=summary,
                                        content=content[:5000],
                                        tags=json.dumps(tags))
            except Exception as e:
                console.print(f"[dim]Could not fetch URL ({e}) — saved raw link[/dim]")

    git_sync.auto_commit("brain: URL saved")

    display = f"[green]✓[/green] [bold]{title or link}[/bold]\n"
    if summary:
        display += f"[dim]{summary}[/dim]\n"
    if tags:
        display += f"[cyan]{', '.join(tags)}[/cyan]\n"
    display += f"[dim]ID: {row['id']} · unread[/dim]"

    console.print(Panel(display, title="[blue]Saved[/blue]", border_style="blue"))
    return row


def _bulk_import(file_path: str, project: str = "", no_summary: bool = False):
    """Import URLs from a file — one per line. Lines can be 'URL' or 'URL  note'."""
    path = Path(file_path).expanduser()
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        return

    lines = [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]
    if not lines:
        console.print("[dim]File is empty[/dim]")
        return

    console.print(f"[dim]Importing {len(lines)} URLs from {path.name}...[/dim]\n")
    saved = 0
    failed = 0
    for line in lines:
        parts = line.split(None, 1)
        link = parts[0]
        if not (link.startswith("http://") or link.startswith("https://")):
            console.print(f"[dim]Skipping (not a URL): {line[:60]}[/dim]")
            continue
        try:
            _save_one(link, project=project, no_summary=no_summary)
            saved += 1
        except Exception as e:
            console.print(f"[red]Failed {link[:50]}: {e}[/red]")
            failed += 1

    console.print(f"\n[green]✓ {saved} URLs saved[/green]" + (f"  [red]{failed} failed[/red]" if failed else ""))


def _fetch_url(url: str) -> tuple[str, str]:
    try:
        import httpx
        import trafilatura
        import re
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text
        content = trafilatura.extract(html) or ""
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else url
        return title, content
    except Exception:
        return url, ""


def _show_queue():
    items = db.get_readlater(status="unread", limit=20)
    if not items:
        console.print("[dim]Read-later queue is empty[/dim]")
        return

    table = Table(box=box.ROUNDED, border_style="blue", title="Read Later Queue")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Title")
    table.add_column("Description", max_width=50)
    table.add_column("Tags", style="cyan")
    table.add_column("Added", style="dim")

    for item in items:
        tags = json.loads(item["tags"]) if item["tags"] else []
        added = item["added_at"][:10] if item["added_at"] else "—"
        table.add_row(
            item["id"],
            item["title"][:50] or item["url"][:50],
            item["summary"][:60] if item["summary"] else "—",
            ", ".join(tags[:3]) or "—",
            added,
        )

    console.print(table)
