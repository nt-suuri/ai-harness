"""Product Analyzer: post-release agent that moves shipped items + tops up backlog."""

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from agents.lib import gh, kill_switch, product_state, prompts
from agents.lib.anthropic import run_agent

_DEFAULT_STATE = Path("docs/product/state.yaml")
_DEFAULT_VISION = Path("docs/product/vision.md")
_COMMIT_LOOKBACK = 50


async def run(state_path: Path, vision_path: Path, *, dry_run: bool) -> None:
    state = product_state.load(state_path)
    vision = vision_path.read_text() if vision_path.exists() else ""
    repo = gh.repo()
    commits = list(repo.get_commits()[:_COMMIT_LOOKBACK])

    commit_blob = "\n".join(f"- {c.commit.message.splitlines()[0]}" for c in commits)

    user_prompt = (
        f"RECENT_COMMITS:\n{commit_blob}\n\n"
        f"CURRENT_BACKLOG:\n{[{'id': b.id, 'title': b.title} for b in state.backlog]}\n\n"
        f"CURRENT_IN_PROGRESS:\n{[{'id': b.id, 'title': b.title} for b in state.in_progress]}\n\n"
        f"VISION:\n{vision}\n"
    )
    system = prompts.load("product_analyzer")
    result = await run_agent(prompt=user_prompt, system=system, max_turns=3, allowed_tools=[])
    text = _extract_text(result.messages)

    shipped_ids = _parse_shipped(text)
    new_items = _parse_new_backlog(text)

    if dry_run:
        return

    for item_id in shipped_ids:
        try:
            state.ship(item_id)
        except KeyError:
            continue

    existing_titles = {i.title for i in state.backlog + state.in_progress + state.shipped}
    for new in new_items:
        if new["title"] in existing_titles:
            continue
        state.backlog.append(product_state.Item(
            id=new["id"], title=new["title"],
            priority=new.get("priority", "normal"),
            rationale=new.get("rationale", ""),
            added_by="analyzer",
        ))

    state.last_analyzer_run = datetime.now(UTC).isoformat()
    product_state.save(state_path, state)


def _extract_text(messages: list[object]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _parse_shipped(text: str) -> list[str]:
    m = re.search(r"^SHIPPED_IDS:\s*(.*)$", text, flags=re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_new_backlog(text: str) -> list[dict[str, str]]:
    m = re.search(r"^NEW_BACKLOG:\s*(.*)", text, flags=re.DOTALL | re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw in ("[]", ""):
        return []
    try:
        parsed = yaml.safe_load(raw) or []
    except yaml.YAMLError:
        return []
    return [dict(entry) for entry in parsed if isinstance(entry, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agents.product_analyzer")
    parser.add_argument("--state", type=Path, default=_DEFAULT_STATE)
    parser.add_argument("--vision", type=Path, default=_DEFAULT_VISION)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    kill_switch.exit_if_paused()
    asyncio.run(run(args.state, args.vision, dry_run=args.dry_run))
    print("analyzer: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
