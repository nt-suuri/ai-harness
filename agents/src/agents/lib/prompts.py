"""Load agent system prompts from sibling .md files."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.md").read_text()


def list_prompts() -> list[str]:
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.md"))
