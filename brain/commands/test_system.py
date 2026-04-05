import typer
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()
app = typer.Typer(help="Run end-to-end system health check")

PASS = "[green]✓ PASS[/green]"
FAIL = "[red]✗ FAIL[/red]"
SKIP = "[dim]– SKIP[/dim]"


@app.callback(invoke_without_command=True)
def test_system():
    results = []

    # 1. DB connection + schema
    try:
        from brain.core.db import get_db, get_stats
        d = get_db()
        tables = set(d.table_names())
        required = {"todos", "learned", "notes", "readlater", "captures"}
        missing = required - tables
        if missing:
            results.append(("DB schema", FAIL, f"Missing tables: {missing}"))
        else:
            stats = get_stats()
            results.append(("DB connection", PASS, f"{stats['todos_active']} active todos, {stats['notes']} notes"))
    except Exception as e:
        results.append(("DB connection", FAIL, str(e)))

    # 2. Add + delete a test todo
    try:
        from brain.core.db import add_todo, get_db
        row = add_todo("__brain_test_todo__", priority="p3", category="Test > System")
        d = get_db()
        found = list(d["todos"].rows_where("id = ?", [row["id"]]))
        d.execute("DELETE FROM todos WHERE id = ?", [row["id"]])
        d.conn.commit()
        results.append(("Todo create/delete", PASS if found else FAIL, f"ID {row['id']}"))
    except Exception as e:
        results.append(("Todo create/delete", FAIL, str(e)))

    # 3. Add + delete a test learning
    try:
        from brain.core.db import add_learned, get_db
        row = add_learned("__test__", "system health check", project="test")
        d = get_db()
        found = list(d["learned"].rows_where("id = ?", [row["id"]]))
        d.execute("DELETE FROM learned WHERE id = ?", [row["id"]])
        d.conn.commit()
        results.append(("Learned create/delete", PASS if found else FAIL, f"ID {row['id']}"))
    except Exception as e:
        results.append(("Learned create/delete", FAIL, str(e)))

    # 4. URL save + delete
    try:
        from brain.core.db import add_readlater, get_db
        row = add_readlater("https://httpbin.org/get", title="test")
        d = get_db()
        found = list(d["readlater"].rows_where("id = ?", [row["id"]]))
        d.execute("DELETE FROM readlater WHERE id = ?", [row["id"]])
        d.conn.commit()
        results.append(("URL save/delete", PASS if found else FAIL, f"ID {row['id']}"))
    except Exception as e:
        results.append(("URL save/delete", FAIL, str(e)))

    # 5. Search
    try:
        from brain.core.db import search_notes_fts
        search_notes_fts("test", limit=1)
        results.append(("Search (FTS)", PASS, "ok"))
    except Exception as e:
        results.append(("Search (FTS)", FAIL, str(e)))

    # 6. Anthropic connection
    try:
        from brain.core.ai import haiku
        reply = haiku("reply with just: ok")
        results.append(("Anthropic (Haiku)", PASS, reply.strip()[:40]))
    except Exception as e:
        results.append(("Anthropic (Haiku)", FAIL, str(e)[:60]))

    # 7. OpenAI connection
    try:
        from brain import config
        oai_key = config.get("openai_api_key", "")
        if not oai_key or oai_key.startswith("Error"):
            results.append(("OpenAI (GPT-5 Nano)", SKIP, "No API key configured"))
        else:
            from brain.core.ai import fast_llm
            reply = fast_llm("reply with just: ok")
            results.append(("OpenAI (GPT-5 Nano)", PASS, reply.strip()[:40]))
    except Exception as e:
        results.append(("OpenAI (GPT-5 Nano)", FAIL, str(e)[:60]))

    # 8. Google Calendar
    try:
        from brain.core.google_cal import is_enabled, get_today_events
        if not is_enabled():
            results.append(("Google Calendar", SKIP, "Not enabled"))
        else:
            events = get_today_events()
            results.append(("Google Calendar", PASS, f"{len(events)} events today"))
    except Exception as e:
        results.append(("Google Calendar", FAIL, str(e)[:60]))

    # 9. Persona file
    try:
        from brain import config
        from pathlib import Path
        persona_path = Path(config.brain_dir()) / "persona.md"
        if persona_path.exists():
            size = len(persona_path.read_text())
            results.append(("Persona", PASS, f"{size} chars at {persona_path}"))
        else:
            results.append(("Persona", SKIP, "Not set — run: brain setup --persona"))
    except Exception as e:
        results.append(("Persona", FAIL, str(e)))

    # Display results
    table = Table(box=box.ROUNDED, title="[bold]brain system check[/bold]")
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    for name, status, detail in results:
        table.add_row(name, status, detail)

    console.print()
    console.print(table)

    passed = sum(1 for _, s, _ in results if "PASS" in s)
    failed = sum(1 for _, s, _ in results if "FAIL" in s)
    skipped = sum(1 for _, s, _ in results if "SKIP" in s)
    console.print(f"\n[green]{passed} passed[/green]  [red]{failed} failed[/red]  [dim]{skipped} skipped[/dim]")
