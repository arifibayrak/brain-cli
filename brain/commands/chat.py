import json
import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.rule import Rule
from brain.core import db, files, git_sync

console = Console()
app = typer.Typer(help="Chat with your brain (AI agent mode)")

TOOLS = [
    {
        "name": "create_todo",
        "description": (
            "Create a new todo/task. "
            "IMPORTANT: Always include a category in 'Domain > Subcategory' format "
            "(e.g. 'Work > Code Review', 'Academic > Exams', 'Personal > Health'). "
            "If the user did not mention a due date, you MUST ask them before calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Concise, action-oriented task title"},
                "priority": {"type": "string", "enum": ["p1", "p2", "p3"], "default": "p2"},
                "category": {"type": "string", "description": "Category in 'Domain > Subcategory' format — required"},
                "project": {"type": "string", "description": "Project name if applicable"},
                "due_date": {"type": "string", "description": "Due date YYYY-MM-DD — ask user if not provided"},
                "due_time": {"type": "string", "description": "Start time HH:MM if applicable"},
                "due_end_time": {"type": "string", "description": "End time HH:MM if applicable"},
                "context": {"type": "string", "description": "Extra context, notes, or details"},
            },
            "required": ["title", "category"],
        },
    },
    {
        "name": "add_note",
        "description": "Add a note to the knowledge base",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "project": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "log_learned",
        "description": "Log something you learned",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "insight": {"type": "string"},
                "project": {"type": "string"},
            },
            "required": ["topic", "insight"],
        },
    },
    {
        "name": "save_url",
        "description": "Save a URL to read later",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "notes": {"type": "string"},
                "project": {"type": "string"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "search_brain",
        "description": "Search notes, todos, learnings, and read-later items",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "type": {"type": "string", "enum": ["notes", "todos", "learned", "urls", "all"], "default": "all"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_todos",
        "description": "List todos, optionally filtered by project or status",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["todo", "done", "doing"], "default": "todo"},
                "project": {"type": "string"},
            },
        },
    },
    {
        "name": "complete_todo",
        "description": "Mark a todo as completed",
        "input_schema": {
            "type": "object",
            "properties": {
                "todo_id": {"type": "string"},
            },
            "required": ["todo_id"],
        },
    },
    {
        "name": "get_stats",
        "description": "Get current brain stats (inbox count, active todos, etc.)",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_learned",
        "description": "Get recent learnings",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7},
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Create a Google Calendar event. Ask for date and time if not provided.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title"},
                "date": {"type": "string", "description": "Date YYYY-MM-DD"},
                "start_time": {"type": "string", "description": "Start time HH:MM (omit for all-day)"},
                "end_time": {"type": "string", "description": "End time HH:MM"},
                "description": {"type": "string", "description": "Event description or notes"},
                "location": {"type": "string", "description": "Location"},
            },
            "required": ["summary", "date"],
        },
    },
    {
        "name": "get_calendar_events",
        "description": "Get upcoming calendar events",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "How many days ahead to look"},
            },
        },
    },
    {
        "name": "list_emails",
        "description": "List unread Gmail inbox emails, or search by query",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5},
                "search": {"type": "string", "description": "Gmail search query (e.g. 'from:atomico subject:interview')"},
            },
        },
    },
    {
        "name": "read_email",
        "description": "Read the full content of a Gmail email by ID",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string"},
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "create_todo_from_email",
        "description": "Create a todo from a Gmail email — AI extracts the action item",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string"},
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email to someone via Gmail. Compose the subject and body yourself based on context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body text — compose this based on what the user wants to say"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "list_contacts",
        "description": "List networking contacts, optionally filtered by relationship strength or a search term",
        "input_schema": {
            "type": "object",
            "properties": {
                "strength": {
                    "type": "string",
                    "enum": ["active", "warm", "cold", "dormant", ""],
                    "description": "Filter by relationship strength. Leave empty for all.",
                },
                "search": {
                    "type": "string",
                    "description": "Search by name, company, role, notes, or tags",
                },
            },
        },
    },
    {
        "name": "log_contact_interaction",
        "description": "Log an interaction with a contact (meeting, call, email, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "Contact ID from list_contacts"},
                "note": {"type": "string", "description": "What happened or was discussed"},
                "type": {
                    "type": "string",
                    "enum": ["coffee", "call", "email", "linkedin", "event", "other"],
                    "description": "Type of interaction",
                },
                "date": {"type": "string", "description": "YYYY-MM-DD, defaults to today"},
            },
            "required": ["contact_id", "note"],
        },
    },
]


def _execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "create_todo":
            row = db.add_todo(
                inputs["title"],
                priority=inputs.get("priority", "p2"),
                category=inputs.get("category", ""),
                project=inputs.get("project", ""),
                due_date=inputs.get("due_date", ""),
                due_time=inputs.get("due_time", ""),
                due_end_time=inputs.get("due_end_time", ""),
                context=inputs.get("context", ""),
            )
            files.append_to_daily("Tasks", inputs["title"])
            git_sync.auto_commit("brain: todo added via chat")
            return json.dumps({"success": True, "id": row["id"], "title": row["title"],
                               "category": row["category"], "due_date": row["due_date"]})

        elif name == "add_note":
            row = db.add_note(
                inputs["title"],
                inputs["content"],
                tags=inputs.get("tags", []),
                project=inputs.get("project", ""),
            )
            git_sync.auto_commit("brain: note added via chat")
            return json.dumps({"success": True, "id": row["id"]})

        elif name == "log_learned":
            row = db.add_learned(
                inputs["topic"],
                inputs["insight"],
                project=inputs.get("project", ""),
            )
            files.write_learned_file(inputs["topic"], inputs["insight"])
            git_sync.auto_commit("brain: learned via chat")
            return json.dumps({"success": True, "id": row["id"]})

        elif name == "save_url":
            url_str = inputs["url"]
            # Always save URL immediately so it's never lost
            row = db.add_readlater(url_str, project=inputs.get("project", ""))
            # Then try to enrich with title + summary
            try:
                from brain.commands.url import _fetch_url
                from brain.core.ai import summarize_url
                title, content = _fetch_url(url_str)
                if content:
                    meta = summarize_url(title, content)
                    db.update_readlater(row["id"], title=title,
                                        summary=meta.get("summary", ""),
                                        content=content[:5000],
                                        tags=json.dumps(meta.get("tags", [])))
            except Exception:
                pass
            git_sync.auto_commit("brain: URL saved via chat")
            return json.dumps({"success": True, "id": row["id"], "url": url_str})

        elif name == "search_brain":
            query = inputs["query"]
            results = {"notes": [], "todos": [], "learned": [], "urls": []}
            results["notes"] = [{"id": r["id"], "title": r["title"]} for r in db.search_notes_fts(query, limit=5)]
            d = db.get_db()
            results["todos"] = [{"id": r["id"], "title": r["title"]} for r in
                                 d["todos"].rows_where("title LIKE ?", [f"%{query}%"], limit=5)]
            results["learned"] = [{"topic": r["topic"], "insight": r["insight"][:100]} for r in
                                   d["learned"].rows_where("topic LIKE ? OR insight LIKE ?",
                                                           [f"%{query}%", f"%{query}%"], limit=5)]
            results["urls"] = [{"id": r["id"], "title": r["title"][:60]} for r in
                                d["readlater"].rows_where("title LIKE ?", [f"%{query}%"], limit=5)]
            return json.dumps(results)

        elif name == "list_todos":
            todos = db.get_todos(
                status=inputs.get("status", "todo"),
                project=inputs.get("project", ""),
            )
            return json.dumps([{"id": t["id"], "title": t["title"], "priority": t["priority"],
                                "due_date": t["due_date"]} for t in todos])

        elif name == "complete_todo":
            db.complete_todo(inputs["todo_id"])
            git_sync.auto_commit("brain: todo completed via chat")
            return json.dumps({"success": True})

        elif name == "get_stats":
            return json.dumps(db.get_stats())

        elif name == "get_learned":
            items = db.get_learned(days=inputs.get("days", 7))
            return json.dumps([{"topic": i["topic"], "insight": i["insight"], "date": i["date"]} for i in items])

        elif name == "create_calendar_event":
            from brain.core.google_cal import create_event, is_enabled
            if not is_enabled():
                return json.dumps({"error": "Google Calendar not connected. Run: brain setup --google"})
            event = create_event(
                summary=inputs["summary"],
                date_str=inputs["date"],
                start_time=inputs.get("start_time", ""),
                end_time=inputs.get("end_time", ""),
                description=inputs.get("description", ""),
                location=inputs.get("location", ""),
            )
            return json.dumps({"success": True, "event": event})

        elif name == "get_calendar_events":
            from brain.core.google_cal import get_upcoming_events, is_enabled
            if not is_enabled():
                return json.dumps({"error": "Google Calendar not connected."})
            events = get_upcoming_events(days=inputs.get("days", 7))
            return json.dumps(events)

        elif name == "list_emails":
            from brain.core.gmail import get_unread, search_emails, is_enabled
            if not is_enabled():
                return json.dumps({"error": "Gmail not connected. Run: brain setup --google"})
            q = inputs.get("search", "")
            emails = search_emails(q, limit=inputs.get("limit", 5)) if q else get_unread(limit=inputs.get("limit", 5))
            return json.dumps(emails)

        elif name == "read_email":
            from brain.core.gmail import get_email, is_enabled
            if not is_enabled():
                return json.dumps({"error": "Gmail not connected."})
            return json.dumps(get_email(inputs["email_id"]))

        elif name == "create_todo_from_email":
            from brain.core.gmail import get_email, is_enabled
            from brain.core.ai import fast_llm, _strip_json
            if not is_enabled():
                return json.dumps({"error": "Gmail not connected."})
            email = get_email(inputs["email_id"])
            if "error" in email:
                return json.dumps(email)
            try:
                prompt = (
                    f"From: {email['from']}\nSubject: {email['subject']}\n\n{email['body'][:1500]}\n\n"
                    f'Extract the main action item as JSON: {{"title":"action-oriented task","priority":"p1|p2|p3","due_date":"YYYY-MM-DD or empty","category":"Domain > Sub","context":"brief context"}}'
                )
                import json as _json
                result = _json.loads(_strip_json(fast_llm(prompt)))
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
            git_sync.auto_commit("brain: todo from email via chat")
            return json.dumps({"success": True, "id": row["id"], "title": row["title"]})

        elif name == "send_email":
            from brain.core.gmail import send_email, is_enabled
            if not is_enabled():
                return json.dumps({"error": "Gmail not connected. Run: brain setup --google"})
            body_text = inputs["body"]
            html = f"<div style='font-family:sans-serif;line-height:1.6'>{body_text.replace(chr(10), '<br>')}</div>"
            result = send_email(inputs["to"], inputs["subject"], html, body_text)
            return json.dumps({"success": True, "id": result["id"], "to": inputs["to"]})

        elif name == "list_contacts":
            contacts = db.get_contacts(
                strength=inputs.get("strength", ""),
                search=inputs.get("search", ""),
            )
            return json.dumps([
                {
                    "id": c["id"],
                    "name": c["name"],
                    "company": c.get("company", ""),
                    "role": c.get("role", ""),
                    "relationship_strength": c.get("relationship_strength", "dormant"),
                    "last_interaction_date": c.get("last_interaction_date", ""),
                    "last_interaction_note": c.get("last_interaction_note", ""),
                    "met_where": c.get("met_where", ""),
                    "interactions_count": c.get("interactions_count", 0),
                }
                for c in contacts
            ])

        elif name == "log_contact_interaction":
            row = db.add_interaction(
                contact_id=inputs["contact_id"],
                date_str=inputs.get("date", ""),
                type_=inputs.get("type", "other"),
                note=inputs["note"],
            )
            git_sync.auto_commit("brain: interaction logged via chat")
            return json.dumps({"success": True, "id": row["id"], "date": row["date"]})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


SYSTEM = """You are the user's personal AI brain assistant with access to their knowledge base, todos, learnings, and read-later queue.

You can:
- Create, list, and complete todos
- Add notes and knowledge
- Log learnings
- Save URLs
- Search all content
- Provide insights and summaries

## Rules you MUST follow

### Creating todos
1. **Category is mandatory.** Always assign a category in "Domain > Subcategory" format (e.g. "Work > Code Review", "Academic > Exams", "Personal > Health"). Never call create_todo without a category.
2. **Due date: always ask first.** If the user hasn't provided a due date, you MUST ask "When is this due?" before calling create_todo. Do not skip this even if the task seems undated — a "no due date" answer is fine but you must ask.
3. Once you have both category and due date (or confirmation there is none), call create_todo immediately.

### General behavior
- Be concise and action-oriented.
- When asked to do something, use the tools. When asked for information, search first then answer.
- Be proactive about surfacing patterns and insights."""


def _load_persona() -> str:
    """Load ~/.brain/persona.md if it exists."""
    try:
        from brain import config
        from pathlib import Path
        p = Path(config.brain_dir()) / "persona.md"
        if p.exists():
            return p.read_text().strip()
    except Exception:
        pass
    return ""


@app.callback(invoke_without_command=True)
def chat():
    from brain.core.ai import _get_anthropic
    from brain import config

    try:
        client = _get_anthropic()
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(Panel(
        "[bold cyan]Brain Chat[/bold cyan] — AI agent with access to your full knowledge base\n"
        "[dim]Type your message. 'quit' or Ctrl+C to exit.[/dim]",
        border_style="cyan",
    ))

    # Build system prompt — prepend persona if set
    persona = _load_persona()
    system = (f"## About the user\n{persona}\n\n{SYSTEM}" if persona else SYSTEM)

    messages = []

    while True:
        try:
            user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if user_input.lower() in ("quit", "exit", "bye", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        with console.status("[cyan]Thinking...[/cyan]"):
            chat_model = config.get("chat_model", config.get("sonnet_model", "claude-sonnet-4-6"))
        response = client.messages.create(
                model=chat_model,
                max_tokens=4096,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

        # Agentic loop — handle tool calls
        while response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    console.print(f"[dim]  → {block.name}({json.dumps(block.input)[:80]})[/dim]")
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            with console.status("[cyan]Processing...[/cyan]"):
                response = client.messages.create(
                    model=chat_model,
                    max_tokens=4096,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                )

        # Extract final text response
        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        if final_text:
            console.print(f"\n[bold]Brain:[/bold]")
            console.print(Markdown(final_text))

        messages.append({"role": "assistant", "content": response.content})
