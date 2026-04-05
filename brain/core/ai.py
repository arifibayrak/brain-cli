"""
AI provider abstraction.

Cost routing:
  fast_llm()    → GPT-5 Nano ($0.05/1M in) if openai_api_key set, else Haiku with prompt caching
  quality_llm() → Claude Sonnet (default) OR GPT-4o if quality_provider = "openai"
  brain chat    → Claude Haiku by default (chat_model in config), configurable to Sonnet

GPT-5 Nano is 16x cheaper than Haiku for fast ops (tagging, parsing, summarization).
Anthropic Haiku/Sonnet remain for chat and quality tasks.
"""
import json
from datetime import date
from brain import config

_anthropic_client = None
_openai_client = None


# ── Client factories ──────────────────────────────────────────────────────────

def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        key = config.api_key()
        if not key:
            raise ValueError("Anthropic API key not set.\nRun: brain setup")
        _anthropic_client = anthropic.Anthropic(api_key=key)
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ValueError("openai package not installed. Run: pip install openai")
        key = config.get("openai_api_key", "")
        if not key:
            raise ValueError("OpenAI API key not set.\nRun: brain setup")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


# ── Core call wrappers ────────────────────────────────────────────────────────

def haiku(prompt: str, system: str = "") -> str:
    """Anthropic Haiku with prompt caching on large system prompts."""
    client = _get_anthropic()
    model = config.get("haiku_model", "claude-haiku-4-5-20251001")

    # Use cache_control for system prompts > 200 chars — saves ~90% on repeated calls
    if system and len(system) > 200:
        system_param = [{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}]
    elif system:
        system_param = system
    else:
        system_param = None

    kwargs = {"model": model, "max_tokens": 1024,
              "messages": [{"role": "user", "content": prompt}]}
    if system_param:
        kwargs["system"] = system_param

    msg = client.messages.create(**kwargs)
    return msg.content[0].text


def sonnet(prompt: str, system: str = "", messages: list = None) -> str:
    """Anthropic Sonnet with prompt caching."""
    client = _get_anthropic()
    model = config.get("sonnet_model", "claude-sonnet-4-6")
    if messages is None:
        messages = [{"role": "user", "content": prompt}]

    if system and len(system) > 200:
        system_param = [{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}]
    elif system:
        system_param = system
    else:
        system_param = None

    kwargs = {"model": model, "max_tokens": 4096, "messages": messages}
    if system_param:
        kwargs["system"] = system_param

    msg = client.messages.create(**kwargs)
    return msg.content[0].text


def _openai_fast(prompt: str, system: str = "") -> str:
    client = _get_openai()
    model = config.get("openai_fast_model", "gpt-5-nano")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model=model, messages=messages, max_tokens=1024)
    return resp.choices[0].message.content


def _openai_quality(prompt: str, system: str = "", messages: list = None) -> str:
    client = _get_openai()
    model = config.get("openai_quality_model", "gpt-4o")
    if messages is None:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
    else:
        msgs = messages
    resp = client.chat.completions.create(model=model, messages=msgs, max_tokens=4096)
    return resp.choices[0].message.content


# ── Routing: fast_llm / quality_llm ──────────────────────────────────────────

def fast_llm(prompt: str, system: str = "") -> str:
    """
    Cheapest model for tagging, classification, parsing.
    Uses GPT-4o-mini if openai_api_key is set (5x cheaper than Haiku).
    Falls back to Haiku with prompt caching.
    """
    oai_key = config.get("openai_api_key", "")
    if oai_key:
        try:
            return _openai_fast(prompt, system)
        except Exception:
            pass  # fallback to Anthropic
    return haiku(prompt, system)


def quality_llm(prompt: str, system: str = "", messages: list = None) -> str:
    """
    Best quality model for chat, summaries, insights.
    Defaults to Claude Sonnet; can use GPT-4o if configured.
    """
    quality_provider = config.get("quality_provider", "anthropic")
    if quality_provider == "openai":
        try:
            return _openai_quality(prompt, system, messages)
        except Exception:
            pass  # fallback to Anthropic
    return sonnet(prompt, system, messages)


def sonnet_with_tools(messages: list, tools: list, system: str = "") -> object:
    """Raw Anthropic Sonnet call with tool use — returns the Message object."""
    client = _get_anthropic()
    model = config.get("sonnet_model", "claude-sonnet-4-6")

    if system and len(system) > 200:
        system_param = [{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}]
    elif system:
        system_param = system
    else:
        system_param = None

    kwargs = {"model": model, "max_tokens": 4096,
              "messages": messages, "tools": tools}
    if system_param:
        kwargs["system"] = system_param

    return client.messages.create(**kwargs)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def resolve_dates_in_text(text: str) -> str:
    """Replace weekday references with explicit ISO dates to prevent AI date-math errors."""
    import re
    from datetime import timedelta

    today = date.today()
    today_dow = today.weekday()

    day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
               "friday": 4, "saturday": 5, "sunday": 6}

    def _next_occurrence(target_dow: int, force_next_week: bool = False) -> date:
        delta = (target_dow - today_dow) % 7
        if delta == 0:
            delta = 7
        if force_next_week and delta < 7:
            delta += 7
        return today + timedelta(days=delta)

    def _replace(m: re.Match) -> str:
        qualifier = (m.group(1) or "").lower().strip()
        day_name = m.group(2)
        target_dow = day_map[day_name.lower()]
        force_next = "next" in qualifier
        resolved = _next_occurrence(target_dow, force_next_week=force_next)
        return f"{m.group(0)}[{resolved.isoformat()}]"

    day_pattern = "|".join(day_map.keys())
    pattern = rf"((?:next|this|on|coming)\s+)?({day_pattern})"
    return re.sub(pattern, _replace, text, flags=re.IGNORECASE)


def _build_date_context() -> str:
    """Next 7 days as an ISO lookup table (reduced from 22 to save tokens)."""
    from datetime import timedelta
    today = date.today()
    days = []
    for i in range(8):
        d = today + timedelta(days=i)
        prefix = "today" if i == 0 else ("tomorrow" if i == 1 else "")
        entry = f"{d.strftime('%A')} {d.strftime('%-d %B')}={d.isoformat()}"
        if prefix:
            entry = f"{prefix}/{entry}"
        days.append(entry)
    return "  ".join(days)


# ── Public AI functions ───────────────────────────────────────────────────────

def parse_intent(user_input: str) -> dict:
    system = """You are a personal assistant classifier. Parse user input and return JSON only.
Classify into: note, todo, learned, url, search, daily, process
Return JSON: {"type":"...","content":"...","title":"...","topic":"...","url":"...","project":null,"priority":"p2","due_date":null,"tags":[]}"""
    try:
        result = fast_llm(user_input, system=system)
        return json.loads(_strip_json(result))
    except Exception:
        return {"type": "note", "content": user_input, "title": user_input[:60], "tags": []}


def analyze_todos(raw_input: str, existing_categories: list[str] = None) -> list[dict]:
    """Parse any todo input and return list of structured todo dicts."""
    today = date.today().isoformat()
    cats = existing_categories or []
    cats_str = ", ".join(f'"{c}"' for c in cats) if cats else "none yet"
    date_ctx = _build_date_context()

    system = f"""Today is {today} ({date.today().strftime('%A')}).
Upcoming dates: {date_ctx}
Weekday refs in input already have ISO dates in [brackets] — use them directly.

Parse into todos. Rules:
- One todo per task (split multi-item input)
- Times: "10:00-12:00" → due_time="10:00", due_end_time="12:00"
- Priority: p1=high stakes or ≤7 days away, p2=normal/≤14 days, p3=someday
- Category format: "Domain > Subcategory". Existing: [{cats_str}]. Reuse if matching.
- Titles: concise and action-oriented
- "N days before X" → subtract N days from X's ISO date

Return JSON array only:
[{{"title":"...","priority":"p1|p2|p3","category":"Domain > Sub","due_date":"YYYY-MM-DD or ''","due_time":"HH:MM or ''","due_end_time":"HH:MM or ''","context":"...","project":""}}]"""

    processed = resolve_dates_in_text(raw_input)
    result = fast_llm(processed, system=system)
    try:
        parsed = json.loads(_strip_json(result))
        if isinstance(parsed, dict):
            parsed = [parsed]
        return parsed
    except json.JSONDecodeError:
        first_line = raw_input.strip().splitlines()[0][:120]
        return [{"title": first_line, "priority": "p2", "category": "",
                 "due_date": "", "due_time": "", "due_end_time": "",
                 "context": raw_input[:300], "project": ""}]


def summarize_url(title: str, content: str) -> dict:
    prompt = (
        f'Title: {title}\n\nContent:\n{content[:2000]}\n\n'
        f'Return JSON only: {{"short_title":"concise title under 8 words","summary":"1 sentence under 20 words","tags":["tag1","tag2","tag3"]}}'
    )
    try:
        result = json.loads(_strip_json(fast_llm(prompt)))
        return result
    except Exception:
        return {"short_title": title, "summary": "", "tags": []}


def generate_daily_brief(stats: dict, todos: list, learned: list, resurfaced: list,
                         persona: str = "") -> str:
    system = "You are a personal productivity assistant. Be concise and actionable. No fluff."
    if persona:
        system = f"{system}\n\n## About the user\n{persona}"
    prompt = f"""Morning briefing (max 150 words). Data:
Stats: {json.dumps(stats)}
Todos (top 10): {json.dumps(todos[:10], default=str)}
Learned recently: {json.dumps(learned[:5], default=str)}
Include: key focus, patterns noticed, one insight."""
    try:
        return quality_llm(prompt, system=system)
    except Exception:
        return ""


def generate_summary(period: str, todos_done: list, learned_items: list, notes_added: list) -> str:
    context = {"period": period, "tasks_completed": len(todos_done),
               "things_learned": learned_items, "notes_added": len(notes_added),
               "sample_todos": [t["title"] for t in todos_done[:10]]}
    prompt = f"""Generate a {period} summary with insights:
{json.dumps(context, default=str)}
Include: accomplishments, key learnings, patterns, suggestions. Max 300 words."""
    return quality_llm(prompt)


def categorize_learned_batch(items: list[dict]) -> list[dict]:
    """
    Takes list of {id, topic, insight}, returns list of {id, category}.
    Category format: "Domain > Subcategory" (e.g. "Technology > AI", "Career > VC").
    Uses GPT-5 Nano via fast_llm.
    """
    if not items:
        return []
    system = """Categorize each learning into "Domain > Subcategory" format.
Examples: "Technology > AI", "Career > Venture Capital", "Business > Go-To-Market",
"Academic > Computer Science", "Personal > Health", "Finance > Investing"

Return JSON array only: [{"id":"...","category":"Domain > Sub"}, ...]"""
    batch = [{"id": item["id"], "topic": item["topic"],
               "insight": item["insight"][:150]} for item in items]
    prompt = json.dumps(batch)
    try:
        result = json.loads(_strip_json(fast_llm(prompt, system=system)))
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def generate_category_insights(category: str, items: list[dict]) -> str:
    """Generate a short insight paragraph for a category of learnings."""
    system = "You are an analyst summarizing someone's learning patterns. Be concise, direct, insightful."
    entries = [f"- {i['topic']}: {i['insight'][:200]}" for i in items[:20]]
    prompt = f"""Category: {category}
Learnings ({len(items)} total):
{chr(10).join(entries)}

Write 2-3 sentences: what patterns emerge, what this person is building towards, one actionable observation."""
    try:
        return quality_llm(prompt, system=system)
    except Exception:
        return ""
