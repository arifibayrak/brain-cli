import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich import box

console = Console()
app = typer.Typer(help="Read and manage Gmail")


@app.callback(invoke_without_command=True)
def mail(
    search: str = typer.Option("", "--search", "-s", help="Search emails (Gmail syntax)"),
    read: str = typer.Option("", "--read", "-r", help="Read full email by ID + AI summary"),
    todo: str = typer.Option("", "--todo", "-t", help="Create a todo from an email ID"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of emails to show"),
    weekly: bool = typer.Option(False, "--weekly", "-w", help="Send weekly digest to yourself"),
    send_to: str = typer.Option("", "--send", help="Send an email: --send you@example.com"),
    subject: str = typer.Option("", "--subject", help="Subject for --send"),
    body: str = typer.Option("", "--body", "-b", help="Body text for --send"),
):
    from brain.core.gmail import is_enabled

    if not is_enabled():
        console.print(
            "[yellow]Gmail not enabled.[/yellow]\n"
            "[dim]Run: brain setup --google[/dim]"
        )
        return

    if weekly:
        _send_weekly_digest()
        return

    if send_to:
        _send_manual(send_to, subject, body)
        return

    if read:
        _read_email(read)
        return

    if todo:
        _email_to_todo(todo)
        return

    if search:
        _search(search, limit)
        return

    _list_unread(limit)


def _list_unread(limit: int):
    from brain.core.gmail import get_unread

    with console.status("[cyan]Fetching inbox...[/cyan]"):
        emails = get_unread(limit=limit)

    if not emails:
        console.print("[dim]No unread emails[/dim]")
        return

    table = Table(box=box.ROUNDED, border_style="cyan",
                  title=f"[bold]Unread Inbox ({len(emails)})[/bold]")
    table.add_column("ID", style="dim", width=12)
    table.add_column("From", max_width=25)
    table.add_column("Subject")
    table.add_column("Date", style="dim", width=12)

    for e in emails:
        sender = e["from"].split("<")[0].strip().strip('"') or e["from"]
        table.add_row(e["id"][:10], sender[:25], e["subject"][:60], e["date"])

    console.print(table)
    console.print("[dim]Read full email: brain mail --read <ID>[/dim]")


def _search(query: str, limit: int):
    from brain.core.gmail import search_emails

    with console.status(f"[cyan]Searching '{query}'...[/cyan]"):
        emails = search_emails(query, limit=limit)

    if not emails:
        console.print(f"[dim]No results for '{query}'[/dim]")
        return

    table = Table(box=box.ROUNDED, border_style="cyan",
                  title=f"[bold]Search: {query}[/bold]")
    table.add_column("ID", style="dim", width=12)
    table.add_column("From", max_width=25)
    table.add_column("Subject")
    table.add_column("Date", style="dim", width=12)

    for e in emails:
        sender = e["from"].split("<")[0].strip().strip('"') or e["from"]
        table.add_row(e["id"][:10], sender[:25], e["subject"][:60], e["date"])

    console.print(table)


def _read_email(msg_id: str):
    from brain.core.gmail import get_email, mark_read
    from brain.core.ai import quality_llm

    with console.status("[cyan]Loading email...[/cyan]"):
        email = get_email(msg_id)

    if "error" in email:
        console.print(f"[red]Error: {email['error']}[/red]")
        return

    console.print(Rule(f"[bold]{email['subject']}[/bold]"))
    console.print(f"[dim]From:[/dim] {email['from']}")
    console.print(f"[dim]Date:[/dim] {email['date']}\n")
    console.print(email["body"] or "[dim](no text content)[/dim]")

    if email.get("body"):
        console.print()
        with console.status("[cyan]Summarizing...[/cyan]"):
            try:
                summary = quality_llm(
                    f"Summarize this email in 2-3 sentences. Focus on any action items.\n\n"
                    f"From: {email['from']}\nSubject: {email['subject']}\n\n{email['body'][:2000]}"
                )
                console.print(Panel(summary, title="[cyan]AI Summary[/cyan]", border_style="cyan"))
            except Exception:
                pass

    mark_read(msg_id)


def _email_to_todo(msg_id: str):
    from brain.core.gmail import get_email
    from brain.core.ai import fast_llm, _strip_json
    from brain.core import db, git_sync
    import json

    with console.status("[cyan]Reading email...[/cyan]"):
        email = get_email(msg_id)

    if "error" in email:
        console.print(f"[red]{email['error']}[/red]")
        return

    with console.status("[cyan]Extracting action item...[/cyan]"):
        try:
            prompt = (
                f"From: {email['from']}\nSubject: {email['subject']}\n\n{email['body'][:1500]}\n\n"
                f'Extract the main action item as JSON: {{"title":"action-oriented task","priority":"p1|p2|p3","due_date":"YYYY-MM-DD or empty","category":"Domain > Sub","context":"brief context"}}'
            )
            result = json.loads(_strip_json(fast_llm(prompt)))
        except Exception:
            result = {"title": email["subject"], "priority": "p2",
                      "due_date": "", "category": "Email > Action", "context": ""}

    row = db.add_todo(
        title=result.get("title", email["subject"]),
        priority=result.get("priority", "p2"),
        category=result.get("category", "Email > Action"),
        due_date=result.get("due_date", ""),
        context=result.get("context", f"From: {email['from']}"),
    )
    git_sync.auto_commit("brain: todo from email")

    console.print(Panel(
        f"[green]✓[/green] [bold]{row['title']}[/bold]\n"
        f"[cyan]{row['category']}[/cyan]  "
        f"[dim]ID: {row['id']}[/dim]",
        title="[yellow]Todo created from email[/yellow]",
        border_style="yellow",
    ))


def _send_manual(to: str, subject: str, body_text: str):
    """Send a plain email via Gmail."""
    from brain.core.gmail import send_email

    if not subject:
        subject = console.input("[bold]Subject:[/bold] ").strip()
    if not body_text:
        console.print("[dim]Body (press Enter twice when done):[/dim]")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        body_text = "\n".join(lines).strip()

    if not body_text:
        console.print("[red]Empty body — cancelled[/red]")
        return

    html = f"<div style='font-family:sans-serif;line-height:1.6'>{body_text.replace(chr(10),'<br>')}</div>"
    with console.status(f"[cyan]Sending to {to}...[/cyan]"):
        result = send_email(to, subject, html, body_text)

    console.print(Panel(
        f"[green]✓[/green] Sent to [bold]{to}[/bold]\n[dim]ID: {result['id']}[/dim]",
        title="[green]Email sent[/green]", border_style="green",
    ))


def _send_weekly_digest():
    """Build and send a weekly review digest to the user's own Gmail."""
    from datetime import date, timedelta
    from brain.core import db
    from brain.core.gmail import send_email, get_my_email
    from brain.core.google_cal import get_upcoming_events, is_enabled as cal_enabled

    with console.status("[cyan]Building weekly digest...[/cyan]"):
        today = date.today()
        week_start = today - timedelta(days=7)

        todos_done = db.get_completed_todos(days=7)
        todos_active = [t for t in db.get_todos(status="todo") if t.get("due_date","") <= (today + timedelta(days=7)).isoformat()]
        todos_doing = db.get_todos(status="doing")
        learned = db.get_learned(days=7)
        cal_events = get_upcoming_events(days=7) if cal_enabled() else []

        html = _build_digest_html(today, week_start, todos_done, todos_active, todos_doing, learned, cal_events)
        subject = f"🧠 Weekly Brain Digest — {week_start.strftime('%b %-d')} to {today.strftime('%b %-d, %Y')}"

        my_email = get_my_email()
        result = send_email(my_email, subject, html)

    console.print(Panel(
        f"[green]✓[/green] Sent to [bold]{my_email}[/bold]\n"
        f"[dim]{len(todos_done)} completed · {len(learned)} learnings · {len(cal_events)} events[/dim]",
        title="[green]Weekly digest sent[/green]", border_style="green",
    ))


def _build_digest_html(today, week_start, todos_done, todos_active, todos_doing, learned, cal_events) -> str:
    from collections import defaultdict

    def pri_color(p):
        return {"p1":"#ef4444","p2":"#f59e0b","p3":"#6b7280"}.get(p,"#6b7280")

    def section(title, icon, content):
        return f"""
        <tr><td style="padding:0 0 28px 0">
          <h2 style="margin:0 0 14px 0;font-size:16px;font-weight:700;color:#1a1a2e;border-bottom:2px solid #f0f0f8;padding-bottom:8px">{icon} {title}</h2>
          {content}
        </td></tr>"""

    def todo_row(t, show_status=False):
        p = t.get("priority","p2")
        cat = t.get("category","")
        status_badge = f'<span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:12px;font-size:11px;margin-left:6px">{t["status"].upper()}</span>' if show_status else ""
        cat_badge = f'<span style="background:#f3f0ff;color:#7c3aed;padding:2px 8px;border-radius:12px;font-size:11px;margin-left:6px">{cat}</span>' if cat else ""
        return f'<div style="padding:8px 0;border-bottom:1px solid #f5f5f8"><span style="background:{pri_color(p)};color:#fff;padding:2px 7px;border-radius:5px;font-size:11px;font-weight:700">{p.upper()}</span>{status_badge}{cat_badge} <span style="font-size:14px;color:#1a1a2e;margin-left:8px">{t["title"]}</span></div>'

    # Calendar section
    if cal_events:
        by_day = defaultdict(list)
        for e in cal_events:
            by_day[e["start"][:10]].append(e)
        cal_html = ""
        for day in sorted(by_day)[:7]:
            from datetime import date as _d
            d = _d.fromisoformat(day)
            label = d.strftime("%A, %B %-d")
            cal_html += f'<div style="margin:10px 0 4px 0;font-weight:700;color:#4b5563;font-size:13px">{label}</div>'
            for ev in by_day[day]:
                t_str = ev["start"][11:16] if "T" in ev["start"] else "All day"
                cal_html += f'<div style="padding:5px 0 5px 12px;border-left:3px solid #5b8af7;margin:4px 0;font-size:13px;color:#1a1a2e"><strong>{t_str}</strong> &nbsp;{ev["summary"]}</div>'
        cal_section = section("This Week's Calendar", "📅", cal_html)
    else:
        cal_section = ""

    # Completed todos
    if todos_done:
        done_html = "".join(todo_row(t) for t in todos_done)
        done_section = section(f"Completed This Week ({len(todos_done)})", "✅", done_html)
    else:
        done_section = section("Completed This Week", "✅", '<p style="color:#9ca3af;font-size:13px">No todos completed this week.</p>')

    # In progress + upcoming
    in_progress = todos_doing + todos_active[:8]
    if in_progress:
        ip_html = "".join(todo_row(t, show_status=True) for t in in_progress)
        ip_section = section(f"In Progress & Upcoming ({len(in_progress)})", "📋", ip_html)
    else:
        ip_section = ""

    # Learnings
    if learned:
        by_cat = defaultdict(list)
        for item in learned:
            by_cat[item.get("category") or "General"].append(item)
        learn_html = ""
        for cat, items in sorted(by_cat.items()):
            learn_html += f'<div style="margin:10px 0 4px 0;font-weight:700;color:#7c3aed;font-size:13px">{cat}</div>'
            for item in items:
                learn_html += f'<div style="padding:8px 12px;background:#faf5ff;border-left:3px solid #a78bfa;border-radius:4px;margin:4px 0"><strong style="color:#1a1a2e;font-size:13px">{item["topic"]}</strong><br><span style="color:#4b5563;font-size:13px;line-height:1.5">{item["insight"]}</span></div>'
        learn_section = section(f"Learned This Week ({len(learned)})", "💡", learn_html)
    else:
        learn_section = section("Learned This Week", "💡", '<p style="color:#9ca3af;font-size:13px">Nothing logged this week.</p>')

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="margin:0;padding:0;background:#f8f8fc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f8fc;padding:32px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">
  <tr><td style="background:linear-gradient(135deg,#667eea,#764ba2);padding:32px 40px;text-align:center">
    <h1 style="margin:0;color:#fff;font-size:24px;font-weight:800">🧠 Weekly Brain Digest</h1>
    <p style="margin:8px 0 0;color:rgba(255,255,255,.8);font-size:14px">{week_start.strftime('%B %-d')} – {today.strftime('%B %-d, %Y')}</p>
  </td></tr>
  <tr><td style="padding:32px 40px">
    <table width="100%" cellpadding="0" cellspacing="0">
      {cal_section}
      {done_section}
      {ip_section}
      {learn_section}
      <tr><td style="padding:20px 0 0 0;text-align:center;color:#9ca3af;font-size:12px;border-top:1px solid #f0f0f8">
        Sent by brain-cli · <a href="http://localhost:7730" style="color:#7c3aed">Open dashboard</a>
      </td></tr>
    </table>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
