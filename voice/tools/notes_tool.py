"""
voice/tools/notes_tool.py
--------------------------
Local markdown notes.
"""
from datetime import datetime
from pathlib import Path

from voice.config import settings


def _notes_dir() -> Path:
    p = Path(settings.notes_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


async def tool_take_note(note: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _notes_dir() / f"{ts}.md"
    path.write_text(f"# Note — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{note}\n")
    return "Note saved."


async def tool_read_notes(limit: int = 5) -> str:
    files = sorted(_notes_dir().glob("*.md"), reverse=True)[:limit]
    if not files:
        return "You have no notes yet."
    parts = [f.read_text().strip() for f in files]
    return "\n\n---\n\n".join(parts)
