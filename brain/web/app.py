from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import Optional
import json
import asyncio
import csv
import io

try:
    import openpyxl as _openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

from brain.core import db
from brain.core.db import get_db

app = FastAPI(title="brain dashboard", docs_url=None, redoc_url=None)

TEMPLATE = Path(__file__).parent / "templates" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return TEMPLATE.read_text()


# ── Stats ──────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    return db.get_stats()


# ── Todos ──────────────────────────────────────────────────────────────────────

@app.get("/api/todos")
async def list_todos(status: str = "all"):
    d = get_db()
    if status == "all":
        rows = list(d["todos"].rows_where(
            "status != 'cancelled'", order_by="due_date, priority"
        ))
    else:
        rows = db.get_todos(status=status)
    return rows


@app.post("/api/todos")
async def create_todo(body: dict):
    row = db.add_todo(
        title=body["title"],
        priority=body.get("priority", "p2"),
        category=body.get("category", ""),
        project=body.get("project", ""),
        due_date=body.get("due_date", ""),
        due_time=body.get("due_time", ""),
        due_end_time=body.get("due_end_time", ""),
        context=body.get("context", ""),
    )
    from brain.core import git_sync
    git_sync.auto_commit("brain: todo added via dashboard")
    return row


@app.patch("/api/todos/{todo_id}")
async def update_todo(todo_id: str, body: dict):
    d = get_db()
    existing = list(d["todos"].rows_where("id = ?", [todo_id]))
    if not existing:
        raise HTTPException(status_code=404, detail="Todo not found")

    if "status" in body and body["status"] == "done":
        db.complete_todo(todo_id)
        body.pop("status")

    if body:
        db.update_todo(todo_id, **body)

    from brain.core import git_sync
    git_sync.auto_commit("brain: todo updated via dashboard")
    return list(d["todos"].rows_where("id = ?", [todo_id]))[0]


@app.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: str):
    d = get_db()
    d.execute("DELETE FROM todos WHERE id = ?", [todo_id])
    d.conn.commit()
    from brain.core import git_sync
    git_sync.auto_commit("brain: todo deleted via dashboard")
    return {"success": True}


# ── Categories ────────────────────────────────────────────────────────────────

@app.get("/api/categories")
async def categories():
    return db.get_categories()


# ── Learnings ─────────────────────────────────────────────────────────────────

@app.get("/api/learned")
async def learned(days: int = 0, category: str = ""):
    if days > 0:
        items = db.get_learned(days=days)
    else:
        items = db.get_learned_all()
    if category:
        items = [i for i in items if (i.get("category") or "") == category]
    return items


@app.post("/api/learned")
async def create_learned(body: dict):
    topic = body.get("topic", "").strip()
    insight = body.get("insight", "").strip()
    if not topic or not insight:
        raise HTTPException(status_code=400, detail="topic and insight are required")
    row = db.add_learned(
        topic=topic,
        insight=insight,
        tags=body.get("tags", []),
        project=body.get("project", ""),
    )
    if body.get("category"):
        db.update_learned(row["id"], category=body["category"])
        row["category"] = body["category"]
    from brain.core import git_sync
    git_sync.auto_commit("brain: learning added via dashboard")
    return row


@app.get("/api/learned/categories")
async def learned_categories():
    d = get_db()
    rows = d.execute(
        "SELECT DISTINCT category FROM learned WHERE category != '' AND category IS NOT NULL ORDER BY category"
    ).fetchall()
    return [r[0] for r in rows]


# ── Calendar ──────────────────────────────────────────────────────────────────

@app.get("/api/calendar")
async def calendar_events(days: int = 14):
    try:
        from brain.core.google_cal import get_upcoming_events, is_enabled
        if not is_enabled():
            return []
        return get_upcoming_events(days=days)
    except Exception:
        return []


# ── Read Later ────────────────────────────────────────────────────────────────

@app.get("/api/readlater")
async def list_readlater(status: str = "unread"):
    d = get_db()
    if status == "all":
        rows = list(d["readlater"].rows_where("1=1", order_by="added_at DESC"))
    else:
        rows = db.get_readlater(status=status, limit=100)
    return rows


@app.post("/api/readlater")
async def create_readlater(body: dict):
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    row = db.add_readlater(
        url=url,
        title=body.get("title", ""),
        summary=body.get("summary", ""),
        project=body.get("project", ""),
    )
    from brain.core import git_sync
    git_sync.auto_commit("brain: link saved via dashboard")
    return row


@app.patch("/api/readlater/{item_id}")
async def update_readlater(item_id: str, body: dict):
    d = get_db()
    existing = list(d["readlater"].rows_where("id = ?", [item_id]))
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    db.update_readlater(item_id, **body)
    return list(d["readlater"].rows_where("id = ?", [item_id]))[0]


@app.delete("/api/readlater/{item_id}")
async def delete_readlater(item_id: str):
    d = get_db()
    d.execute("DELETE FROM readlater WHERE id = ?", [item_id])
    d.conn.commit()
    return {"success": True}


# ── Calendar ──────────────────────────────────────────────────────────────────

@app.post("/api/calendar")
async def create_calendar_event(body: dict):
    try:
        from brain.core.google_cal import create_event
        event = create_event(
            summary=body["summary"],
            date_str=body["date"],
            start_time=body.get("start_time", ""),
            end_time=body.get("end_time", ""),
            description=body.get("description", ""),
            location=body.get("location", ""),
        )
        return event
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Contacts ──────────────────────────────────────────────────────────────────

@app.get("/api/interactions/recent")
async def recent_interactions(days: int = 7):
    return db.get_recent_interactions(days=days)


@app.get("/api/contacts")
async def list_contacts(strength: str = "", q: str = ""):
    return db.get_contacts(strength=strength, search=q)


@app.post("/api/contacts")
async def create_contact(body: dict):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    tags = body.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    met_where = body.get("met_where", "")
    met_date = body.get("met_date", "")
    row = db.add_contact(
        name=name,
        role=body.get("role", ""),
        company=body.get("company", ""),
        email=body.get("email", ""),
        linkedin=body.get("linkedin", ""),
        met_where=met_where,
        met_date=met_date,
        tags=tags,
        notes=body.get("notes", ""),
        strength_override=body.get("strength_override", ""),
        circle=body.get("circle", ""),
    )
    # Auto-log the first meeting as an interaction if met_where or met_date is provided
    if met_where or met_date:
        note = f"First met{' at ' + met_where if met_where else ''}"
        db.add_interaction(
            contact_id=row["id"],
            date_str=met_date or "",
            type_="event",
            note=note,
        )
    from brain.core import git_sync
    git_sync.auto_commit("brain: contact added via dashboard")
    return db.get_contact(row["id"]) or row


@app.get("/api/contacts/{contact_id}")
async def get_contact(contact_id: str):
    row = db.get_contact(contact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    return row


@app.patch("/api/contacts/{contact_id}")
async def update_contact(contact_id: str, body: dict):
    existing = db.get_contact(contact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    tags = body.get("tags")
    if isinstance(tags, str):
        body["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    db.update_contact(contact_id, **{k: v for k, v in body.items() if k != "id"})
    from brain.core import git_sync
    git_sync.auto_commit("brain: contact updated via dashboard")
    return db.get_contact(contact_id)


@app.delete("/api/contacts/{contact_id}")
async def delete_contact(contact_id: str):
    existing = db.get_contact(contact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete_contact(contact_id)
    from brain.core import git_sync
    git_sync.auto_commit("brain: contact deleted via dashboard")
    return {"success": True}


@app.get("/api/contacts/{contact_id}/interactions")
async def list_interactions(contact_id: str):
    return db.get_interactions(contact_id)


@app.post("/api/contacts/{contact_id}/interactions")
async def create_interaction(contact_id: str, body: dict):
    existing = db.get_contact(contact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    row = db.add_interaction(
        contact_id=contact_id,
        date_str=body.get("date", ""),
        type_=body.get("type", "other"),
        note=body.get("note", ""),
    )
    from brain.core import git_sync
    git_sync.auto_commit("brain: interaction logged via dashboard")
    return row


@app.delete("/api/interactions/{interaction_id}")
async def delete_interaction(interaction_id: str):
    db.delete_interaction(interaction_id)
    from brain.core import git_sync
    git_sync.auto_commit("brain: interaction deleted via dashboard")
    return {"success": True}


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(body: dict):
    """Streaming SSE chat endpoint. Accepts {messages: [...], history: [...]}
    Yields server-sent events: data: {"type": "text"|"tool"|"done", ...}
    """
    from brain.commands.chat import TOOLS, SYSTEM, _execute_tool, _load_persona
    from brain.core.ai import _get_anthropic
    from brain import config

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages required")

    try:
        client = _get_anthropic()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    persona = _load_persona()
    system = (f"## About the user\n{persona}\n\n{SYSTEM}" if persona else SYSTEM)
    chat_model = config.get("chat_model", config.get("sonnet_model", "claude-sonnet-4-6"))

    async def event_stream():
        history = list(messages)  # copy to avoid mutation

        try:
            # Agentic loop — handle multiple tool_use rounds
            while True:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.messages.create(
                        model=chat_model,
                        max_tokens=4096,
                        system=system,
                        tools=TOOLS,
                        messages=history,
                    )
                )

                if response.stop_reason != "tool_use":
                    # Final text response
                    final_text = "".join(
                        block.text for block in response.content if hasattr(block, "text")
                    )
                    yield f"data: {json.dumps({'type': 'text', 'text': final_text})}\n\n"
                    break

                # Tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        yield f"data: {json.dumps({'type': 'tool', 'name': block.name, 'input': block.input})}\n\n"
                        result = await asyncio.get_event_loop().run_in_executor(
                            None, lambda b=block: _execute_tool(b.name, b.input)
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                history.append({"role": "assistant", "content": response.content})
                history.append({"role": "user", "content": tool_results})

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Bulk Import ────────────────────────────────────────────────────────────────

_IMPORT_PROMPTS = {
    "contacts": (
        "Extract all contacts/people from the text below. "
        "Return ONLY a JSON array of objects with these keys: "
        '"name" (required string), "role", "company", "email", "linkedin", '
        '"met_where", "met_date" (YYYY-MM-DD or empty string), "tags" (array of strings), "notes". '
        "Omit keys that are not present. Return only the JSON array, no explanation."
    ),
    "learned": (
        "Extract all learnings, insights, or knowledge items from the text. "
        "Return ONLY a JSON array of objects with keys: "
        '"topic" (required), "insight" (required), "category", '
        '"tags" (array of strings), "project". '
        "Return only the JSON array, no explanation."
    ),
    "readlater": (
        "Extract all URLs / links / articles to read from the text. "
        "Return ONLY a JSON array of objects with keys: "
        '"url" (required), "title", "summary", "project". '
        "Return only the JSON array, no explanation."
    ),
    "todos": (
        "Extract all tasks or to-do items from the text. "
        "Return ONLY a JSON array of objects with keys: "
        '"title" (required), "priority" (p1/p2/p3, default p2), '
        '"category", "project", "due_date" (YYYY-MM-DD or empty string). '
        "Return only the JSON array, no explanation."
    ),
}

_COL_MAP = {
    "name": "name", "full name": "name", "fullname": "name",
    "role": "role", "job title": "role", "position": "role",
    "company": "company", "organization": "company", "org": "company",
    "email": "email", "e-mail": "email",
    "linkedin": "linkedin", "linkedin url": "linkedin",
    "met where": "met_where", "where met": "met_where", "met_where": "met_where", "connection type": "met_where",
    "met date": "met_date", "date met": "met_date", "met_date": "met_date", "date": "met_date",
    "tags": "tags", "tag": "tags", "labels": "tags",
    "notes": "notes", "note": "notes", "comments": "notes",
    "topic": "topic", "subject": "topic",
    "insight": "insight", "learning": "insight", "content": "insight", "body": "insight",
    "category": "category", "type": "category",
    "project": "project",
    "url": "url", "link": "url", "website": "url",
    "summary": "summary", "description": "summary",
    "title": "title", "task": "title", "todo": "title",
    "priority": "priority",
    "due date": "due_date", "due_date": "due_date", "due": "due_date",
}


def _normalise_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        mapped = _COL_MAP.get(k.lower().strip(), k.lower().strip().replace(" ", "_"))
        out[mapped] = v if v is not None else ""
    return out


def _parse_csv_bytes(data: bytes) -> list:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [_normalise_row(dict(r)) for r in reader]


def _parse_xlsx_bytes(data: bytes) -> list:
    wb = _openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(c).strip() if c is not None else f"col{i}" for i, c in enumerate(rows[0])]
    result = []
    for row in rows[1:]:
        if all(v is None for v in row):
            continue
        d = {headers[i]: (str(v) if v is not None else "") for i, v in enumerate(row)}
        result.append(_normalise_row(d))
    return result


@app.post("/api/import/parse-text")
async def import_parse_text(body: dict):
    import_type = body.get("type", "")
    text = body.get("text", "").strip()
    if not import_type or not text:
        raise HTTPException(status_code=400, detail="type and text required")
    if import_type not in _IMPORT_PROMPTS:
        raise HTTPException(status_code=400, detail=f"unknown type: {import_type}")

    from brain.core.ai import _get_anthropic
    from brain import config

    try:
        client = _get_anthropic()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    model = config.get("haiku_model", "claude-haiku-4-5-20251001")
    prompt = _IMPORT_PROMPTS[import_type]

    resp = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": f"{prompt}\n\n---\n{text}"}],
        )
    )
    raw = resp.content[0].text.strip()
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise HTTPException(status_code=422, detail="AI did not return a valid JSON array")
    try:
        records = json.loads(raw[start:end])
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"JSON parse error: {e}")
    return {"records": records, "type": import_type}


@app.post("/api/import/parse-file")
async def import_parse_file(type: str = Form(...), file: UploadFile = File(...)):
    if type not in _IMPORT_PROMPTS:
        raise HTTPException(status_code=400, detail=f"unknown type: {type}")
    data = await file.read()
    fname = (file.filename or "").lower()
    if fname.endswith(".xlsx") or fname.endswith(".xls"):
        if not _HAS_OPENPYXL:
            raise HTTPException(status_code=422, detail="openpyxl not installed; use CSV instead")
        records = _parse_xlsx_bytes(data)
    else:
        records = _parse_csv_bytes(data)
    return {"records": records, "type": type}


@app.post("/api/import/commit")
async def import_commit(body: dict):
    import_type = body.get("type", "")
    records = body.get("records", [])
    if not import_type or not records:
        raise HTTPException(status_code=400, detail="type and records required")

    created = 0
    errors = []

    for i, rec in enumerate(records):
        try:
            if import_type == "contacts":
                tags = rec.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                name = str(rec.get("name", "")).strip()
                if not name:
                    errors.append({"index": i, "error": "missing name"})
                    continue
                row = db.add_contact(
                    name=name,
                    role=rec.get("role", ""),
                    company=rec.get("company", ""),
                    email=rec.get("email", ""),
                    linkedin=rec.get("linkedin", ""),
                    met_where=rec.get("met_where", ""),
                    met_date=rec.get("met_date", ""),
                    tags=tags,
                    notes=rec.get("notes", ""),
                )
                met_where = rec.get("met_where", "")
                met_date = rec.get("met_date", "")
                if met_where or met_date:
                    note = f"First met{' at ' + met_where if met_where else ''}"
                    db.add_interaction(contact_id=row["id"], date_str=met_date or "", type_="event", note=note)
                created += 1
            elif import_type == "learned":
                tags = rec.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                topic = str(rec.get("topic", "")).strip()
                insight = str(rec.get("insight", "")).strip()
                if not topic or not insight:
                    errors.append({"index": i, "error": "missing topic or insight"})
                    continue
                r = db.add_learned(topic=topic, insight=insight, tags=tags, project=rec.get("project", ""))
                if rec.get("category"):
                    db.update_learned(r["id"], category=rec["category"])
                created += 1
            elif import_type == "readlater":
                url = str(rec.get("url", "")).strip()
                if not url:
                    errors.append({"index": i, "error": "missing url"})
                    continue
                db.add_readlater(url=url, title=rec.get("title", ""), summary=rec.get("summary", ""), project=rec.get("project", ""))
                created += 1
            elif import_type == "todos":
                title = str(rec.get("title", "")).strip()
                if not title:
                    errors.append({"index": i, "error": "missing title"})
                    continue
                db.add_todo(
                    title=title,
                    priority=rec.get("priority", "p2"),
                    category=rec.get("category", ""),
                    project=rec.get("project", ""),
                    due_date=rec.get("due_date", ""),
                )
                created += 1
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    if created:
        from brain.core import git_sync
        git_sync.auto_commit(f"brain: bulk import {created} {import_type} via dashboard")

    return {"created": created, "errors": errors}
