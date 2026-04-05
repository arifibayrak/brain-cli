# brain-cli

A personal AI-powered knowledge management CLI. Capture notes, todos, learnings, and URLs from the terminal — with an AI agent that understands natural language and keeps everything organized in a local SQLite database with Git-backed history.

---

## Features

- **Natural language capture** — `brain "your thought"` routes input to the right command automatically
- **Smart inbox** — captures everything first, process and triage later
- **Todo management** — priorities, due dates, categories, and time slots
- **Learning log** — track insights by topic with auto-generated markdown files
- **URL saving** — fetch, summarize, and store web pages for later reading
- **AI chat agent** — conversational interface with tool use (create todos, search notes, log learnings)
- **Daily & weekly briefs** — AI-generated overviews of your notes, tasks, and calendar
- **Full-text search** — search across notes, todos, learnings, and URLs
- **Google integrations** — Calendar events in daily brief, Gmail inbox triage
- **Local web dashboard** — FastAPI + Jinja2 UI served at `localhost`
- **Git auto-commit** — every write operation optionally commits to a local Git repo
- **Dual AI provider** — Anthropic Claude (default) with optional OpenAI fallback for cost-sensitive ops

---

## Project Structure

```
brain-cli/
├── pyproject.toml              # Project metadata and dependencies
├── brain/
│   ├── cli.py                  # Entry point — command registration, natural language router
│   ├── config.py               # Config loader/writer (stored in ~/.brain/config.toml)
│   │
│   ├── commands/               # CLI subcommands (one file per command)
│   │   ├── add.py              # brain add — capture a note to inbox
│   │   ├── todo.py             # brain todo — create, list, complete tasks
│   │   ├── learned.py          # brain learned — log a new insight
│   │   ├── url.py              # brain url — save & summarize a URL
│   │   ├── search.py           # brain search — full-text search across all content
│   │   ├── process.py          # brain process — triage inbox items
│   │   ├── chat.py             # brain chat — interactive AI agent with tool use
│   │   ├── daily.py            # brain daily — today's brief (tasks, calendar, notes)
│   │   ├── weekly.py           # brain weekly — weekly overview and summary
│   │   ├── categorize.py       # brain categorize — batch-categorize todos and learnings
│   │   ├── insights.py         # brain insights — surface patterns from your learnings
│   │   ├── mail.py             # brain mail — read and triage Gmail inbox
│   │   ├── web.py              # brain web — launch local web dashboard
│   │   └── test_system.py      # brain test — system health check
│   │
│   ├── core/                   # Shared infrastructure
│   │   ├── ai.py               # AI provider abstraction (Anthropic + OpenAI routing)
│   │   ├── db.py               # SQLite schema and query helpers (via sqlite-utils)
│   │   ├── files.py            # Markdown file management (daily notes, learned files)
│   │   ├── git_sync.py         # Auto-commit on write operations
│   │   ├── gmail.py            # Gmail API integration
│   │   └── google_cal.py       # Google Calendar API integration
│   │
│   └── web/                    # Local web dashboard
│       ├── app.py              # FastAPI application
│       └── templates/
│           └── index.html      # Dashboard UI
```

---

## Installation

Requires Python 3.11+.

```bash
git clone https://github.com/arifibayrak/brain-cli.git
cd brain-cli
pip install -e .
brain setup
```

---

## Quick Start

```bash
# Natural language — brain figures out the type
brain "read the paper on diffusion models by Friday"
brain "learned: transformers use self-attention to model token relationships"
brain "https://example.com/article"

# Explicit commands
brain add "rough idea for later"
brain todo "submit assignment" --due 2026-04-10 --priority p1
brain learned "topic: insight"
brain url https://example.com

# Review and triage
brain daily                   # today's brief
brain weekly                  # weekly overview
brain process                 # triage inbox
brain search "attention"      # search everything

# AI agent mode
brain chat

# Web dashboard
brain web
```

---

## Configuration

Run `brain setup` to configure API keys and settings. Config is stored in `~/.brain/config.toml` — never in the repo.

```bash
brain setup                   # API keys, git auto-commit
brain setup --google          # Google Calendar + Gmail OAuth
brain setup --persona         # Set personal context for AI chat
```

**Supported providers:**
- `anthropic` (default) — Claude Haiku for fast ops, Claude Sonnet for quality tasks
- `openai` (optional) — GPT-4o-mini for classification/tagging (~16x cheaper than Haiku)

---

## Data Storage

All data is stored locally in `~/.brain/`:

```
~/.brain/
├── config.toml         # Settings and API keys
├── brain.db            # SQLite database (notes, todos, learnings, URLs)
├── notes/              # Markdown files per note
├── learned/            # Markdown files per topic
├── daily/              # Daily note files (YYYY-MM-DD.md)
├── persona.md          # Personal context injected into AI chat
└── credentials/        # Google OAuth tokens (gitignored)
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `typer` | CLI framework |
| `anthropic` | Claude AI (chat, summaries, intent parsing) |
| `openai` | Optional fast/cheap ops (GPT-4o-mini) |
| `sqlite-utils` | SQLite database with full-text search |
| `rich` | Terminal formatting and UI |
| `gitpython` | Auto-commit data changes |
| `trafilatura` | Web page text extraction |
| `fastapi` + `uvicorn` | Local web dashboard |
| `google-api-python-client` | Google Calendar and Gmail APIs |

---

## License

MIT
