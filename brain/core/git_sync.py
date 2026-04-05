from pathlib import Path
from brain import config


def _repo(brain_dir: Path):
    try:
        import git
        if (brain_dir / ".git").exists():
            return git.Repo(brain_dir)
        repo = git.Repo.init(brain_dir)
        # Create initial .gitignore
        gitignore = brain_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("credentials/\n*.db-wal\n*.db-shm\n")
        return repo
    except Exception:
        return None


def auto_commit(message: str = "brain: auto-save") -> bool:
    if not config.get("git_auto_commit", True):
        return False
    bd = config.brain_dir()
    repo = _repo(bd)
    if repo is None:
        return False
    try:
        repo.git.add(A=True)
        if repo.is_dirty(index=True, untracked_files=True):
            repo.index.commit(message)
            return True
    except Exception:
        pass
    return False
