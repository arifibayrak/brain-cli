import json
import uuid
from datetime import datetime, date
from pathlib import Path
import sqlite_utils
from brain import config


def _db_path() -> Path:
    return config.brain_dir() / "brain.db"


def get_db() -> sqlite_utils.Database:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(path)
    _ensure_schema(db)
    return db


def _ensure_schema(db: sqlite_utils.Database) -> None:
    if "captures" not in db.table_names():
        db["captures"].create({
            "id": str,
            "content": str,
            "type": str,       # note, todo, learned, url
            "status": str,     # inbox, processed
            "created_at": str,
            "raw_input": str,
        })

    if "notes" not in db.table_names():
        db["notes"].create({
            "id": str,
            "title": str,
            "content": str,
            "file_path": str,
            "tags": str,       # JSON array
            "project": str,
            "area": str,
            "source_url": str,
            "created_at": str,
            "updated_at": str,
            "review_date": str,
            "review_count": int,
        })
        db["notes"].create_index(["project"])
        db["notes"].enable_fts(["title", "content", "tags"])

    if "todos" not in db.table_names():
        db["todos"].create({
            "id": str,
            "title": str,
            "status": str,     # todo, doing, done, cancelled
            "priority": str,   # p1, p2, p3
            "category": str,   # e.g. "Academic > Exams", "Work > Code"
            "project": str,
            "area": str,
            "due_date": str,
            "due_time": str,   # HH:MM start time
            "due_end_time": str,  # HH:MM end time
            "created_at": str,
            "completed_at": str,
            "context": str,
            "archived": int,   # 0 or 1 — manually archived
        })
        db["todos"].create_index(["status"])
        db["todos"].create_index(["project"])
        db["todos"].create_index(["category"])
    else:
        # Migrate existing table — add new columns if missing
        existing_cols = {col.name for col in db["todos"].columns}
        if "category" not in existing_cols:
            db["todos"].add_column("category", str, not_null_default="")
        if "due_time" not in existing_cols:
            db["todos"].add_column("due_time", str, not_null_default="")
        if "due_end_time" not in existing_cols:
            db["todos"].add_column("due_end_time", str, not_null_default="")
        if "archived" not in existing_cols:
            db["todos"].add_column("archived", int, not_null_default=0)

    if "learned" not in db.table_names():
        db["learned"].create({
            "id": str,
            "topic": str,
            "insight": str,
            "date": str,
            "tags": str,       # JSON array
            "project": str,
            "category": str,   # e.g. "Technology > AI", "Career > VC"
            "created_at": str,
        })
        db["learned"].enable_fts(["topic", "insight"])
    else:
        existing_cols = {col.name for col in db["learned"].columns}
        if "category" not in existing_cols:
            db["learned"].add_column("category", str, not_null_default="")

    if "readlater" not in db.table_names():
        db["readlater"].create({
            "id": str,
            "url": str,
            "title": str,
            "summary": str,
            "content": str,
            "tags": str,       # JSON array
            "status": str,     # unread, reading, done, archived
            "added_at": str,
            "read_at": str,
            "notes": str,
            "project": str,
        })
        db["readlater"].enable_fts(["title", "summary", "content"])

    if "contacts" not in db.table_names():
        db["contacts"].create({
            "id": str,
            "name": str,
            "role": str,
            "company": str,
            "email": str,
            "linkedin": str,
            "met_where": str,
            "met_date": str,
            "tags": str,                  # JSON array
            "notes": str,
            "strength_override": str,     # "" | "active"|"warm"|"cold"|"dormant"
            "circle": str,                # "" | "family"|"friends"|"mentors"|"work"|"other"
            "last_interaction_date": str,
            "last_interaction_note": str,
            "created_at": str,
            "updated_at": str,
        })
        db["contacts"].create_index(["company"])
        db["contacts"].create_index(["strength_override"])
    else:
        existing_cols = {col.name for col in db["contacts"].columns}
        for col in ["role", "company", "email", "linkedin", "met_where", "met_date",
                    "tags", "notes", "strength_override", "circle",
                    "last_interaction_date", "last_interaction_note", "updated_at"]:
            if col not in existing_cols:
                db["contacts"].add_column(col, str, not_null_default="")

    if "contact_interactions" not in db.table_names():
        db["contact_interactions"].create({
            "id": str,
            "contact_id": str,
            "date": str,
            "type": str,   # coffee|call|email|linkedin|event|other
            "note": str,
            "created_at": str,
        })
        db["contact_interactions"].create_index(["contact_id"])
        db["contact_interactions"].create_index(["date"])


def new_id() -> str:
    return str(uuid.uuid4())[:8]


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def today_str() -> str:
    return date.today().isoformat()


# --- Captures ---

def add_capture(content: str, type_: str = "note", raw_input: str = "") -> dict:
    db = get_db()
    row = {
        "id": new_id(),
        "content": content,
        "type": type_,
        "status": "inbox",
        "created_at": now_iso(),
        "raw_input": raw_input or content,
    }
    db["captures"].insert(row)
    return row


def inbox_items() -> list[dict]:
    db = get_db()
    return list(db["captures"].rows_where("status = 'inbox'", order_by="created_at"))


def mark_capture_processed(capture_id: str) -> None:
    db = get_db()
    db["captures"].update(capture_id, {"status": "processed"})


# --- Notes ---

def add_note(title: str, content: str, file_path: str = "", tags: list = None,
             project: str = "", area: str = "", source_url: str = "") -> dict:
    db = get_db()
    row = {
        "id": new_id(),
        "title": title,
        "content": content,
        "file_path": file_path,
        "tags": json.dumps(tags or []),
        "project": project or "",
        "area": area or "",
        "source_url": source_url or "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "review_date": "",
        "review_count": 0,
    }
    db["notes"].insert(row)
    return row


def search_notes_fts(query: str, limit: int = 10) -> list[dict]:
    db = get_db()
    try:
        results = list(db["notes"].search(query, limit=limit))
    except Exception:
        results = list(db["notes"].rows_where(
            "title LIKE ? OR content LIKE ?",
            [f"%{query}%", f"%{query}%"],
            limit=limit
        ))
    return results


# --- Todos ---

def add_todo(title: str, priority: str = "p2", project: str = "",
             area: str = "", due_date: str = "", context: str = "",
             category: str = "", due_time: str = "", due_end_time: str = "") -> dict:
    db = get_db()
    row = {
        "id": new_id(),
        "title": title,
        "status": "todo",
        "priority": priority,
        "category": category or "",
        "project": project or "",
        "area": area or "",
        "due_date": due_date or "",
        "due_time": due_time or "",
        "due_end_time": due_end_time or "",
        "created_at": now_iso(),
        "completed_at": "",
        "context": context or "",
    }
    db["todos"].insert(row)
    return row


def get_categories() -> list[str]:
    """Return all distinct non-empty categories."""
    d = get_db()
    rows = d.execute("SELECT DISTINCT category FROM todos WHERE category != '' ORDER BY category").fetchall()
    return [r[0] for r in rows]


def get_todos(status: str = "todo", project: str = "") -> list[dict]:
    db = get_db()
    where = "status = ?"
    params = [status]
    if project:
        where += " AND project = ?"
        params.append(project)
    return list(db["todos"].rows_where(where, params, order_by="due_date, priority"))


def get_overdue_todos() -> list[dict]:
    db = get_db()
    today = today_str()
    return list(db["todos"].rows_where(
        "status = 'todo' AND due_date != '' AND due_date < ?",
        [today]
    ))


def complete_todo(todo_id: str) -> None:
    d = get_db()
    d.execute("UPDATE todos SET status='done', completed_at=? WHERE id=?", [now_iso(), todo_id])
    d.conn.commit()


def update_todo(todo_id: str, **kwargs) -> None:
    d = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [todo_id]
    d.execute(f"UPDATE todos SET {sets} WHERE id = ?", values)
    d.conn.commit()


def find_todos_by_title(query: str) -> list[dict]:
    d = get_db()
    return list(d["todos"].rows_where(
        "status = 'todo' AND title LIKE ?", [f"%{query}%"]
    ))


# --- Learned ---

def add_learned(topic: str, insight: str, tags: list = None, project: str = "") -> dict:
    db = get_db()
    row = {
        "id": new_id(),
        "topic": topic,
        "insight": insight,
        "date": today_str(),
        "tags": json.dumps(tags or []),
        "project": project or "",
        "created_at": now_iso(),
    }
    db["learned"].insert(row)
    return row


def get_learned(days: int = 7) -> list[dict]:
    db = get_db()
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return list(db["learned"].rows_where("date >= ?", [cutoff], order_by="date DESC"))


# --- Read Later ---

def add_readlater(url: str, title: str = "", summary: str = "",
                  content: str = "", tags: list = None, project: str = "") -> dict:
    db = get_db()
    row = {
        "id": new_id(),
        "url": url,
        "title": title or "",
        "summary": summary or "",
        "content": content or "",
        "tags": json.dumps(tags or []),
        "status": "unread",
        "added_at": now_iso(),
        "read_at": "",
        "notes": "",
        "project": project or "",
    }
    db["readlater"].insert(row)
    return row


def get_readlater(status: str = "unread", limit: int = 20) -> list[dict]:
    db = get_db()
    return list(db["readlater"].rows_where(
        "status = ?", [status], order_by="added_at DESC", limit=limit
    ))


def update_readlater(item_id: str, **kwargs) -> None:
    db = get_db()
    db["readlater"].update(item_id, kwargs)


# --- Categorization helpers ---

def get_completed_todos(days: int = 7) -> list[dict]:
    """Return todos completed in the last N days."""
    d = get_db()
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return list(d["todos"].rows_where(
        "status = 'done' AND completed_at >= ?", [cutoff],
        order_by="completed_at DESC"
    ))


def get_uncategorized_todos() -> list[dict]:
    d = get_db()
    return list(d["todos"].rows_where(
        "status = 'todo' AND (category IS NULL OR category = '')"
    ))


def get_learned_all() -> list[dict]:
    d = get_db()
    return list(d["learned"].rows_where("1=1", order_by="date DESC"))


def update_learned(item_id: str, **kwargs) -> None:
    d = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [item_id]
    d.execute(f"UPDATE learned SET {sets} WHERE id = ?", values)
    d.conn.commit()


# --- Contacts ---

def _compute_strength(last_date: str, override: str) -> str:
    if override:
        return override
    if not last_date:
        return "dormant"
    try:
        days = (date.today() - date.fromisoformat(last_date)).days
    except ValueError:
        return "dormant"
    if days <= 30:
        return "active"
    if days <= 90:
        return "warm"
    if days <= 180:
        return "cold"
    return "dormant"


def _enrich_contact(row: dict) -> dict:
    r = dict(row)
    r["relationship_strength"] = _compute_strength(
        r.get("last_interaction_date", ""), r.get("strength_override", "")
    )
    return r


def add_contact(name: str, role: str = "", company: str = "", email: str = "",
                linkedin: str = "", met_where: str = "", met_date: str = "",
                tags: list = None, notes: str = "", strength_override: str = "",
                circle: str = "") -> dict:
    db = get_db()
    row = {
        "id": new_id(),
        "name": name,
        "role": role or "",
        "company": company or "",
        "email": email or "",
        "linkedin": linkedin or "",
        "met_where": met_where or "",
        "met_date": met_date or "",
        "tags": json.dumps(tags or []),
        "notes": notes or "",
        "strength_override": strength_override or "",
        "circle": circle or "",
        "last_interaction_date": "",
        "last_interaction_note": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    db["contacts"].insert(row)
    return _enrich_contact(row)


def get_contacts(strength: str = "", search: str = "") -> list[dict]:
    d = get_db()
    if search:
        q = f"%{search}%"
        rows = list(d["contacts"].rows_where(
            "name LIKE ? OR company LIKE ? OR role LIKE ? OR notes LIKE ? OR tags LIKE ?",
            [q, q, q, q, q], order_by="name"
        ))
    else:
        rows = list(d["contacts"].rows_where("1=1", order_by="name"))

    # Add interactions_count
    counts = {
        r[0]: r[1]
        for r in d.execute(
            "SELECT contact_id, COUNT(*) FROM contact_interactions GROUP BY contact_id"
        ).fetchall()
    }

    enriched = [_enrich_contact(r) for r in rows]
    for r in enriched:
        r["interactions_count"] = counts.get(r["id"], 0)

    if strength:
        enriched = [r for r in enriched if r["relationship_strength"] == strength]

    return enriched


def get_contact(contact_id: str) -> dict | None:
    d = get_db()
    rows = list(d["contacts"].rows_where("id = ?", [contact_id]))
    if not rows:
        return None
    r = _enrich_contact(rows[0])
    r["interactions"] = get_interactions(contact_id)
    return r


def update_contact(contact_id: str, **kwargs) -> None:
    d = get_db()
    if "tags" in kwargs and isinstance(kwargs["tags"], list):
        kwargs["tags"] = json.dumps(kwargs["tags"])
    kwargs["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [contact_id]
    d.execute(f"UPDATE contacts SET {sets} WHERE id = ?", values)
    d.conn.commit()


def delete_contact(contact_id: str) -> None:
    d = get_db()
    d.execute("DELETE FROM contact_interactions WHERE contact_id = ?", [contact_id])
    d.execute("DELETE FROM contacts WHERE id = ?", [contact_id])
    d.conn.commit()


# --- Contact interactions ---

def add_interaction(contact_id: str, date_str: str = "", type_: str = "other",
                    note: str = "") -> dict:
    d = get_db()
    row = {
        "id": new_id(),
        "contact_id": contact_id,
        "date": date_str or today_str(),
        "type": type_ or "other",
        "note": note or "",
        "created_at": now_iso(),
    }
    d["contact_interactions"].insert(row)
    # Update contact's last interaction fields
    d.execute(
        "UPDATE contacts SET last_interaction_date=?, last_interaction_note=?, updated_at=? WHERE id=?",
        [row["date"], note or "", now_iso(), contact_id]
    )
    d.conn.commit()
    return row


def get_interactions(contact_id: str) -> list[dict]:
    d = get_db()
    return list(d["contact_interactions"].rows_where(
        "contact_id = ?", [contact_id], order_by="date DESC"
    ))


def get_recent_interactions(days: int = 7) -> list[dict]:
    """Return interactions in the last N days, joined with contact name/company."""
    d = get_db()
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = d.execute(
        """SELECT ci.id, ci.contact_id, ci.date, ci.type, ci.note, ci.created_at,
                  c.name as contact_name, c.company as contact_company
           FROM contact_interactions ci
           JOIN contacts c ON c.id = ci.contact_id
           WHERE ci.date >= ?
           ORDER BY ci.date DESC""",
        [cutoff]
    ).fetchall()
    cols = ["id", "contact_id", "date", "type", "note", "created_at", "contact_name", "contact_company"]
    return [dict(zip(cols, r)) for r in rows]


def delete_interaction(interaction_id: str) -> None:
    d = get_db()
    # Find the contact to potentially recalculate last_interaction
    rows = list(d["contact_interactions"].rows_where("id = ?", [interaction_id]))
    d.execute("DELETE FROM contact_interactions WHERE id = ?", [interaction_id])
    d.conn.commit()
    # Update contact's last_interaction_date to the newest remaining interaction
    if rows:
        contact_id = rows[0]["contact_id"]
        remaining = list(d["contact_interactions"].rows_where(
            "contact_id = ?", [contact_id], order_by="date DESC", limit=1
        ))
        if remaining:
            d.execute(
                "UPDATE contacts SET last_interaction_date=?, last_interaction_note=?, updated_at=? WHERE id=?",
                [remaining[0]["date"], remaining[0]["note"], now_iso(), contact_id]
            )
        else:
            d.execute(
                "UPDATE contacts SET last_interaction_date='', last_interaction_note='', updated_at=? WHERE id=?",
                [now_iso(), contact_id]
            )
        d.conn.commit()


# --- Stats ---

def get_stats() -> dict:
    db = get_db()
    stats = {
        "inbox": db.execute("SELECT COUNT(*) FROM captures WHERE status='inbox'").fetchone()[0],
        "todos_active": db.execute("SELECT COUNT(*) FROM todos WHERE status='todo'").fetchone()[0],
        "todos_overdue": db.execute(
            f"SELECT COUNT(*) FROM todos WHERE status='todo' AND due_date != '' AND due_date < '{today_str()}'"
        ).fetchone()[0],
        "notes": db.execute("SELECT COUNT(*) FROM notes").fetchone()[0],
        "readlater_unread": db.execute("SELECT COUNT(*) FROM readlater WHERE status='unread'").fetchone()[0],
        "learned_today": db.execute(f"SELECT COUNT(*) FROM learned WHERE date='{today_str()}'").fetchone()[0],
    }
    stats["readlater_done"] = db.execute("SELECT COUNT(*) FROM readlater WHERE status='done'").fetchone()[0]
    stats["todos_doing"] = db.execute("SELECT COUNT(*) FROM todos WHERE status='doing'").fetchone()[0]
    if "contacts" in db.table_names():
        stats["contacts"] = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        stats["contacts_active"] = sum(
            1 for r in db.execute("SELECT last_interaction_date, strength_override FROM contacts").fetchall()
            if _compute_strength(r[0] or "", r[1] or "") == "active"
        )
    else:
        stats["contacts"] = 0
        stats["contacts_active"] = 0
    return stats
