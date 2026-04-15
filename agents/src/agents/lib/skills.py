"""Load engineering-methodology skills (ported from superpowers plugin).

Skills are modular system-prompt extensions an agent can prepend when a task
calls for a specific discipline (TDD, systematic debugging, etc).
"""

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent / "skills"


def load(name: str) -> str:
    """Return the raw skill content. Raises FileNotFoundError if unknown."""
    return (_SKILLS_DIR / f"{name}.md").read_text()


def available() -> list[str]:
    return sorted(p.stem for p in _SKILLS_DIR.glob("*.md"))
