from collections import defaultdict

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich import box
from brain.core import db, git_sync

console = Console()
app = typer.Typer(help="Batch-categorize todos and learnings with AI")


@app.callback(invoke_without_command=True)
def categorize(
    todos_only: bool = typer.Option(False, "--todos", help="Only categorize todos"),
    learned_only: bool = typer.Option(False, "--learned", help="Only categorize learnings"),
):
    if not todos_only:
        _categorize_learned()
    if not learned_only:
        _categorize_todos()


def _categorize_todos():
    from brain.core.ai import fast_llm, _strip_json
    import json

    uncategorized = db.get_uncategorized_todos()
    if not uncategorized:
        console.print("[green]✓ All todos already have categories[/green]")
        return

    console.print(Rule(f"[yellow]Categorizing {len(uncategorized)} todos[/yellow]"))

    existing_cats = db.get_categories()
    cats_str = ", ".join(f'"{c}"' for c in existing_cats) if existing_cats else "none yet"

    system = f"""Suggest a category for each todo in "Domain > Subcategory" format.
Existing categories (reuse if matching): [{cats_str}]
Examples: "Work > Code Review", "Academic > Exams", "Career > Interviews", "Personal > Health"
Return JSON array: [{{"id":"...","category":"Domain > Sub","title":"..."}}]"""

    batch = [{"id": t["id"], "title": t["title"]} for t in uncategorized]
    try:
        result = json.loads(fast_llm(json.dumps(batch), system=system).strip().lstrip("```json").rstrip("```").strip())
        if isinstance(result, dict):
            result = [result]
    except Exception as e:
        console.print(f"[red]AI failed: {e}[/red]")
        return

    # Group by suggested category for validation
    by_cat: dict = defaultdict(list)
    id_to_suggestion = {r["id"]: r for r in result}
    for t in uncategorized:
        suggestion = id_to_suggestion.get(t["id"], {})
        cat = suggestion.get("category", "Uncategorized")
        by_cat[cat].append({"id": t["id"], "title": t["title"], "suggested": cat})

    console.print(f"\n[dim]AI suggested {len(by_cat)} categories. Review each group:[/dim]\n")

    updated = 0
    for cat, items in sorted(by_cat.items()):
        console.print(f"\n[bold cyan]{cat}[/bold cyan] ({len(items)} todo{'s' if len(items) > 1 else ''})")
        for item in items:
            console.print(f"  [dim]•[/dim] {item['title']}")

        raw = console.input(
            f"  [dim]Enter to accept '[cyan]{cat}[/cyan]', type new category, or 's' to skip: [/dim]"
        ).strip()

        if raw.lower() == "s":
            continue
        final_cat = raw if raw else cat
        for item in items:
            db.update_todo(item["id"], category=final_cat)
            updated += 1

    if updated:
        git_sync.auto_commit(f"brain: categorized {updated} todos")
        console.print(f"\n[green]✓ {updated} todos categorized[/green]")
    else:
        console.print("\n[dim]No changes made[/dim]")


def _categorize_learned():
    from brain.core.ai import categorize_learned_batch

    all_items = db.get_learned_all()
    uncategorized = [i for i in all_items if not i.get("category")]

    if not uncategorized:
        console.print("[green]✓ All learnings already have categories[/green]")
        return

    console.print(Rule(f"[magenta]Auto-categorizing {len(uncategorized)} learnings[/magenta]"))

    # Process in batches of 30 to keep prompts small
    batch_size = 30
    total_updated = 0
    for i in range(0, len(uncategorized), batch_size):
        batch = uncategorized[i:i + batch_size]
        console.print(f"[dim]  Processing {i+1}–{min(i+batch_size, len(uncategorized))}...[/dim]")
        suggestions = categorize_learned_batch(batch)
        for s in suggestions:
            if s.get("id") and s.get("category"):
                db.update_learned(s["id"], category=s["category"])
                total_updated += 1

    if total_updated:
        git_sync.auto_commit(f"brain: auto-categorized {total_updated} learnings")
        console.print(f"[green]✓ {total_updated} learnings categorized[/green]")

        # Show summary of categories assigned
        updated_items = db.get_learned_all()
        cat_counts: dict = defaultdict(int)
        for item in updated_items:
            if item.get("category"):
                cat_counts[item["category"]] += 1
        if cat_counts:
            console.print("\n[dim]Categories:[/dim]")
            for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
                console.print(f"  [magenta]{cat}[/magenta] [dim]({count})[/dim]")
