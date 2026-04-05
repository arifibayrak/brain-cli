from datetime import date
from pathlib import Path
from brain import config


def brain_dir() -> Path:
    return config.brain_dir()


def ensure_dirs() -> None:
    bd = brain_dir()
    for d in ["inbox", "projects", "areas", "resources", "archive", "daily", "learned", "readlater", "credentials"]:
        (bd / d).mkdir(parents=True, exist_ok=True)


def daily_note_path() -> Path:
    return brain_dir() / "daily" / f"{date.today().isoformat()}.md"


def get_or_create_daily_note() -> Path:
    ensure_dirs()
    path = daily_note_path()
    if not path.exists():
        path.write_text(
            f"# {date.today().strftime('%A, %B %d %Y')}\n\n"
            "## Notes\n\n"
            "## Learned\n\n"
            "## Tasks\n\n"
        )
    return path


def append_to_daily(section: str, content: str) -> None:
    path = get_or_create_daily_note()
    text = path.read_text()
    marker = f"## {section}"
    if marker in text:
        lines = text.split("\n")
        idx = next(i for i, l in enumerate(lines) if l.strip() == marker)
        lines.insert(idx + 1, f"\n- {content}")
        path.write_text("\n".join(lines))
    else:
        path.write_text(text + f"\n## {section}\n\n- {content}\n")


def write_note_file(title: str, content: str, subfolder: str = "") -> Path:
    ensure_dirs()
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "-" for c in title).strip().replace(" ", "-").lower()
    filename = f"{date.today().isoformat()}-{safe_title[:50]}.md"
    folder = brain_dir() / (subfolder if subfolder else "resources")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_text(f"# {title}\n\n{content}\n")
    return path


def write_learned_file(topic: str, insight: str) -> Path:
    ensure_dirs()
    path = brain_dir() / "learned" / f"{date.today().isoformat()}.md"
    entry = f"\n## {topic}\n\n{insight}\n"
    if path.exists():
        path.write_text(path.read_text() + entry)
    else:
        path.write_text(f"# Learned — {date.today().isoformat()}{entry}")
    return path


def project_dir(project: str) -> Path:
    p = brain_dir() / "projects" / project
    p.mkdir(parents=True, exist_ok=True)
    return p
