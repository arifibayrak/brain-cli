from collections import defaultdict

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box
from brain.core import db

console = Console()
app = typer.Typer(help="Insights and patterns from your learnings")


@app.callback(invoke_without_command=True)
def insights(
    category: str = typer.Option("", "--category", "-c", help="Deep-dive a specific category"),
    days: int = typer.Option(0, "--days", "-d", help="Limit to last N days (0 = all time)"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Skip AI insight generation"),
):
    if days > 0:
        items = db.get_learned(days=days)
    else:
        items = db.get_learned_all()

    if not items:
        console.print("[dim]No learnings found[/dim]")
        return

    # Warn if many items lack categories
    uncategorized = [i for i in items if not i.get("category")]
    if len(uncategorized) > len(items) * 0.3:
        console.print(
            f"[yellow]{len(uncategorized)} learnings have no category — "
            f"run [bold]brain categorize --learned[/bold] first for better insights[/yellow]\n"
        )

    # Filter by category if specified
    if category:
        items = [i for i in items if category.lower() in (i.get("category") or "").lower()]
        if not items:
            console.print(f"[red]No learnings found in category '{category}'[/red]")
            return
        _show_category_detail(category, items, no_ai)
        return

    # Group by category
    by_cat: dict = defaultdict(list)
    for item in items:
        cat = item.get("category") or "Uncategorized"
        by_cat[cat].append(item)

    period = f"last {days} days" if days else "all time"
    console.print(Rule(f"[bold cyan]🧠 Learning Insights — {period} ({len(items)} entries)[/bold cyan]"))

    # Sort by count descending
    for cat, cat_items in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        console.print(f"\n[bold cyan]{cat}[/bold cyan] [dim]({len(cat_items)} entries)[/dim]")

        # Show up to 4 sample entries
        for item in cat_items[:4]:
            created = item.get("created_at", "")
            ts = created[:10] if created else item.get("date", "")
            console.print(f"  [dim]{ts}[/dim]  [magenta]{item['topic']}:[/magenta] {item['insight'][:90]}")
        if len(cat_items) > 4:
            console.print(f"  [dim]... and {len(cat_items) - 4} more[/dim]")

        # AI insight per category
        if not no_ai and len(cat_items) >= 2:
            with console.status(f"[dim]Generating insight for {cat}...[/dim]"):
                try:
                    from brain.core.ai import generate_category_insights
                    insight_text = generate_category_insights(cat, cat_items)
                    if insight_text:
                        console.print(
                            Panel(insight_text, border_style="cyan", padding=(0, 1))
                        )
                except Exception:
                    pass

    console.print(Rule(style="dim"))
    console.print(f"\n[dim]Deep dive: [bold]brain insights --category \"Work > Code\"[/bold][/dim]")


def _show_category_detail(category: str, items: list, no_ai: bool):
    console.print(Rule(f"[bold cyan]{category} — {len(items)} learnings[/bold cyan]"))

    table = Table(box=box.ROUNDED, border_style="magenta")
    table.add_column("Date", style="dim", width=10)
    table.add_column("Topic", style="bold magenta")
    table.add_column("Insight")

    for item in items:
        created = item.get("created_at", "")
        ts = created[:10] if created else item.get("date", "")
        table.add_row(ts, item["topic"], item["insight"])

    console.print(table)

    if not no_ai and len(items) >= 2:
        console.print()
        with console.status("[dim]Generating AI insight...[/dim]"):
            try:
                from brain.core.ai import generate_category_insights
                text = generate_category_insights(category, items)
                if text:
                    console.print(Panel(text, title="[cyan]AI Pattern Analysis[/cyan]",
                                        border_style="cyan"))
            except Exception as e:
                console.print(f"[dim]AI unavailable: {e}[/dim]")
