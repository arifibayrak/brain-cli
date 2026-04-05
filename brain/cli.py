import typer
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from brain.commands import add, todo, learned, url, daily, weekly, search, process, chat, categorize, insights, test_system, mail, web

console = Console()

app = typer.Typer(
    name="brain",
    help="🧠 Your personal AI-powered knowledge base",
    no_args_is_help=False,
    add_completion=True,
)

# Register subcommands
app.add_typer(add.app, name="add", help="Add a note to inbox")
app.add_typer(todo.app, name="todo", help="Manage todos")
app.add_typer(learned.app, name="learned", help="Log learnings")
app.add_typer(url.app, name="url", help="Save URLs to read later")
app.add_typer(daily.app, name="daily", help="Daily brief")
app.add_typer(weekly.app, name="weekly", help="Weekly overview")
app.add_typer(search.app, name="search", help="Search everything")
app.add_typer(process.app, name="process", help="Process inbox")
app.add_typer(chat.app, name="chat", help="Chat with your brain")
app.add_typer(categorize.app, name="categorize", help="Batch-categorize todos and learnings")
app.add_typer(insights.app, name="insights", help="Insights from your learnings")
app.add_typer(test_system.app, name="test", help="System health check")
app.add_typer(mail.app, name="mail", help="Read Gmail inbox")
app.add_typer(web.app, name="web", help="Local web dashboard")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v"),
):
    if version:
        console.print("[cyan]brain-cli v0.1.0[/cyan]")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        _show_welcome()


@app.command(
    "c",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Natural language capture — brain c 'your thought'",
)
def capture(ctx: typer.Context):
    """Route free-form natural language to the right command."""
    text = " ".join(ctx.args).strip()
    if not text:
        console.print("[dim]Usage: brain c 'your thought'[/dim]")
        return
    _route_natural_language(text)


def _route_natural_language(text: str) -> None:
    """Parse natural language input and route to the right command."""
    from brain.core import ai, db, files, git_sync

    # Check if it's a URL
    if text.strip().startswith("http://") or text.strip().startswith("https://"):
        from brain.commands.url import url as url_cmd
        url_cmd(link=text.strip(), note="", project="", no_summary=False, list_=False)
        return

    with console.status("[dim]Understanding...[/dim]"):
        try:
            intent = ai.parse_intent(text)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return
        except Exception:
            # Fallback: treat as note
            intent = {"type": "note", "content": text, "title": text[:60], "tags": []}

    itype = intent.get("type", "note")

    if itype == "todo":
        from brain.commands.todo import _parse_due
        due = _parse_due(intent.get("due_date") or "")
        row = db.add_todo(
            intent.get("content") or intent.get("title") or text,
            priority=intent.get("priority", "p2"),
            project=intent.get("project") or "",
            due_date=due,
        )
        files.append_to_daily("Tasks", row["title"])
        git_sync.auto_commit("brain: todo added")
        console.print(Panel(
            f"[green]✓[/green] [bold]{row['title']}[/bold]\n"
            f"[dim]{row['priority']} · {f'due {due}' if due else 'no due date'}[/dim]",
            title="[yellow]Todo added[/yellow]", border_style="yellow",
        ))

    elif itype == "learned":
        topic = intent.get("topic") or "general"
        insight = intent.get("content") or text
        row = db.add_learned(topic, insight, project=intent.get("project") or "")
        files.write_learned_file(topic, insight)
        files.append_to_daily("Learned", f"**{topic}**: {insight}")
        git_sync.auto_commit("brain: learned")
        console.print(Panel(
            f"[green]✓[/green] [bold]{topic}[/bold]\n{insight}",
            title="[magenta]Learning logged[/magenta]", border_style="magenta",
        ))

    elif itype == "url":
        link = intent.get("url") or text
        from brain.commands.url import url as url_cmd
        url_cmd(link=link, note="", project=intent.get("project") or "", no_summary=False, list_=False)

    elif itype == "search":
        from brain.commands.search import search as search_cmd
        search_cmd(
            query=intent.get("content") or text,
            notes=True, todos=True, learned=True, urls=True, limit=5,
        )

    elif itype == "daily":
        from brain.commands.daily import daily as daily_cmd
        daily_cmd(ai_brief=False)

    elif itype == "process":
        from brain.commands.process import process as process_cmd
        process_cmd()

    else:
        # Default: note → inbox
        row = db.add_capture(intent.get("content") or text, type_="note", raw_input=text)
        files.append_to_daily("Notes", intent.get("content") or text)
        git_sync.auto_commit("brain: note captured")
        console.print(Panel(
            f"[green]✓[/green] {intent.get('content') or text}\n"
            f"[dim]ID: {row['id']} · inbox[/dim]",
            title="[cyan]Captured[/cyan]", border_style="cyan",
        ))


def _show_welcome() -> None:
    from brain.core.db import get_stats
    try:
        stats = get_stats()
        stats_line = (
            f"[yellow]{stats['todos_active']} todos[/yellow] · "
            f"[red]{stats['todos_overdue']} overdue[/red] · "
            f"[blue]{stats['readlater_unread']} to read[/blue] · "
            f"[dim]{stats['inbox']} in inbox[/dim]"
        )
    except Exception:
        stats_line = "[dim]Run 'brain setup' to get started[/dim]"

    console.print(Panel(
        f"[bold cyan]🧠 brain[/bold cyan] — your personal AI knowledge base\n\n"
        f"{stats_line}\n\n"
        "[dim]brain \"your thought\"       → smart capture\n"
        "brain add \"note\"            → add to inbox\n"
        "brain todo \"task\" --due today\n"
        "brain learned \"topic: insight\"\n"
        "brain url https://...       → save & summarize\n"
        "brain daily                 → today's brief\n"
        "brain search \"query\"        → search everything\n"
        "brain process               → triage inbox\n"
        "brain chat                  → AI agent mode\n"
        "brain setup                 → configure API key[/dim]",
        border_style="cyan",
        title="[cyan]brain-cli v0.1.0[/cyan]",
    ))


def _sanitize_key(key: str) -> str:
    """Strip ANSI escape codes and non-printable chars from pasted API keys."""
    import re
    # Remove ANSI escape sequences (e.g. ESC[A from terminal arrow keys)
    key = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', key)
    key = re.sub(r'\x1b.', '', key)
    # Remove all non-printable ASCII except normal chars
    key = re.sub(r'[^\x20-\x7E]', '', key)
    return key.strip()


@app.command("done", help="Mark todo(s) as done — interactive picker or fuzzy title match")
def done_cmd(
    query: str = typer.Argument(None, help="Todo number, title keyword, or ID"),
):
    from brain.commands.todo import interactive_done, _mark_done
    if query:
        _mark_done(query)
    else:
        interactive_done()


@app.command()
def setup(
    google: bool = typer.Option(False, "--google", help="Set up Google Calendar integration"),
    persona: bool = typer.Option(False, "--persona", help="Set your personal context for AI"),
):
    """Configure brain (API keys, settings, Google Calendar)."""
    from brain import config
    from brain.core import files

    console.print("[bold cyan]Brain Setup[/bold cyan]\n")
    files.ensure_dirs()

    cfg = config.load()

    if google:
        _setup_google(cfg)
        config.save(cfg)
        return

    if persona:
        _setup_persona()
        return

    # --- Anthropic API Key ---
    current_key = cfg.get("anthropic_api_key", "")
    if current_key:
        console.print(f"[green]✓ Anthropic API key set[/green] ({current_key[:8]}...)")
        change = typer.confirm("Change it?", default=False)
        if change:
            current_key = ""

    if not current_key:
        key = Prompt.ask("Anthropic API key (console.anthropic.com)", password=True)
        key = _sanitize_key(key)
        if not key.startswith("sk-ant-"):
            console.print(f"[red]Warning: key doesn't look right (starts with '{key[:10]}...').[/red]")
            console.print("[dim]Expected format: sk-ant-api03-...[/dim]")
        cfg["anthropic_api_key"] = key

    # --- OpenAI API Key (optional, for cost savings) ---
    current_oai = cfg.get("openai_api_key", "")
    if current_oai:
        console.print(f"[green]✓ OpenAI API key set[/green] ({current_oai[:8]}...) [dim](used for fast ops — ~5x cheaper than Haiku)[/dim]")
        change = typer.confirm("Change it?", default=False)
        if change:
            current_oai = ""

    if not current_oai:
        add_oai = typer.confirm("Add OpenAI API key? (optional — GPT-4o-mini is cheaper for tagging/classification)", default=False)
        if add_oai:
            oai_key = Prompt.ask("OpenAI API key (platform.openai.com)", password=True)
            oai_key = _sanitize_key(oai_key)
            cfg["openai_api_key"] = oai_key
            console.print("[dim]Fast ops (tagging, parsing) will now use GPT-4o-mini[/dim]")

    # --- Git auto-commit ---
    cfg["git_auto_commit"] = typer.confirm("Enable git auto-commit?", default=True)

    config.save(cfg)

    # Init git repo
    from brain.core.git_sync import _repo
    _repo(config.brain_dir())

    console.print(f"\n[green]✓ Brain configured![/green]")
    console.print(f"[dim]Data dir: {config.brain_dir()}[/dim]")
    console.print(f"\nRun [bold]brain daily[/bold] to get started.")
    console.print(f"[dim]To connect Google Calendar: brain setup --google[/dim]")


def _setup_persona() -> None:
    """Interactively set personal context injected into brain chat."""
    from brain import config
    from pathlib import Path

    persona_path = Path(config.brain_dir()) / "persona.md"
    console.print("[bold cyan]Persona Setup[/bold cyan]\n")
    console.print("[dim]This context is injected into brain chat so AI knows who you are.[/dim]\n")

    if persona_path.exists():
        console.print(f"[green]✓ Existing persona found[/green] ({len(persona_path.read_text())} chars)")
        if not typer.confirm("Replace it?", default=False):
            console.print(f"[dim]Kept existing persona at {persona_path}[/dim]")
            return

    console.print("[bold]Who are you?[/bold] [dim](role, background, current projects, goals)[/dim]")
    console.print("[dim]Press Enter twice or Ctrl+D when done:[/dim]")
    lines = []
    try:
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
    except EOFError:
        pass
    about = "\n".join(lines).strip()

    console.print("\n[bold]Any instructions for how brain chat should talk to you?[/bold]")
    console.print("[dim](tone, things to avoid, preferred format — or just press Enter to skip)[/dim]")
    console.print("[dim]Press Enter twice or Ctrl+D when done:[/dim]")
    instruction_lines = []
    try:
        while True:
            line = input()
            if line == "" and instruction_lines and instruction_lines[-1] == "":
                break
            instruction_lines.append(line)
    except EOFError:
        pass
    instructions = "\n".join(instruction_lines).strip()

    content = f"## About me\n{about}\n"
    if instructions:
        content += f"\n## Instructions\n{instructions}\n"

    persona_path.parent.mkdir(parents=True, exist_ok=True)
    persona_path.write_text(content)
    console.print(f"\n[green]✓ Persona saved[/green] ({len(content)} chars)")
    console.print(f"[dim]{persona_path}[/dim]")
    console.print("\n[dim]brain chat will now use this context in every conversation.[/dim]")


def _setup_google(cfg: dict) -> None:
    """Interactive Google Calendar OAuth setup."""
    from pathlib import Path

    console.print("[bold]Google Calendar Setup[/bold]\n")
    console.print(
        "[dim]Steps:\n"
        "1. Go to https://console.cloud.google.com/\n"
        "2. Create/select a project\n"
        "3. APIs & Services → Enable 'Google Calendar API'\n"
        "4. APIs & Services → Credentials → Create OAuth 2.0 Client ID\n"
        "5. Application type: Desktop app\n"
        "6. Download the JSON file\n"
        "[/dim]"
    )

    creds_path = Prompt.ask(
        "Path to downloaded OAuth JSON file",
        default=cfg.get("google_credentials_path", ""),
    ).strip()

    creds_path = Path(creds_path).expanduser()
    if not creds_path.exists():
        console.print(f"[red]File not found: {creds_path}[/red]")
        return

    # Copy to brain credentials dir
    from brain import config as brain_config
    dest = Path(brain_config.get("google_credentials_path",
                                  str(brain_config.brain_dir() / "credentials" / "google_oauth.json")))
    dest.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(str(creds_path), str(dest))

    cfg["google_credentials_path"] = str(dest)
    cfg["google_calendar_enabled"] = True

    # Remove stale token so fresh auth flow runs next time
    token_path = Path(cfg.get("google_token_path",
                               str(brain_config.brain_dir() / "credentials" / "google_token.json")))
    if token_path.exists():
        token_path.unlink()

    # Ask about Gmail too
    enable_gmail = typer.confirm("Enable Gmail integration? (read inbox, search, create todos from emails)", default=True)
    cfg["google_gmail_enabled"] = enable_gmail

    console.print("\n[dim]Authorizing with Google (browser will open)...[/dim]")
    # Delete old token to force re-auth with new scopes
    token_path = Path(cfg.get("google_token_path",
                               str(brain_config.brain_dir() / "credentials" / "google_token.json")))
    if token_path.exists():
        token_path.unlink()

    try:
        from brain.core.google_cal import get_today_events
        events = get_today_events()
        console.print(f"[green]✓ Google Calendar connected![/green] Found {len(events)} event(s) today.")
        if enable_gmail:
            from brain.core.gmail import get_unread_count
            count = get_unread_count()
            console.print(f"[green]✓ Gmail connected![/green] {count} unread emails.")
    except Exception as e:
        console.print(f"[red]Auth failed: {e}[/red]")


@app.command()
def summary(
    period: str = typer.Argument("week", help="week or month"),
):
    """Generate an AI summary of your week or month."""
    from brain.core import db, ai
    from datetime import date, timedelta

    days = 7 if period == "week" else 30
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    d = db.get_db()

    todos_done = list(d["todos"].rows_where("status='done' AND completed_at >= ?", [cutoff]))
    learned_items = db.get_learned(days=days)
    notes_added = list(d["notes"].rows_where("created_at >= ?", [cutoff]))

    console.print(f"[dim]Generating {period} summary...[/dim]\n")
    with console.status("Thinking..."):
        try:
            text = ai.generate_summary(period, todos_done, learned_items, notes_added)
            console.print(Panel(text, title=f"[cyan]Your {period} in review[/cyan]", border_style="cyan"))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
