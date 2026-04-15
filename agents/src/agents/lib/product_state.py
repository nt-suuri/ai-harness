from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Item:
    id: str
    title: str
    priority: str
    rationale: str
    added_by: str
    issue_number: int | None = None


@dataclass
class State:
    max_open_agent_issues: int
    last_pm_run: str | None
    last_analyzer_run: str | None
    backlog: list[Item] = field(default_factory=list)
    in_progress: list[Item] = field(default_factory=list)
    shipped: list[Item] = field(default_factory=list)
    rejected: list[Item] = field(default_factory=list)

    def start(self, item_id: str, *, issue_number: int) -> Item:
        for i, item in enumerate(self.backlog):
            if item.id == item_id:
                item.issue_number = issue_number
                self.in_progress.append(self.backlog.pop(i))
                return item
        raise KeyError(f"{item_id} not in backlog")

    def ship(self, item_id: str) -> Item:
        for i, item in enumerate(self.in_progress):
            if item.id == item_id:
                self.shipped.append(self.in_progress.pop(i))
                return self.shipped[-1]
        raise KeyError(f"{item_id} not in_progress")


def load(path: Path) -> State:
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    return State(
        max_open_agent_issues=int(data.get("max_open_agent_issues", 2)),
        last_pm_run=data.get("last_pm_run"),
        last_analyzer_run=data.get("last_analyzer_run"),
        backlog=[Item(**d) for d in data.get("backlog") or []],
        in_progress=[Item(**d) for d in data.get("in_progress") or []],
        shipped=[Item(**d) for d in data.get("shipped") or []],
        rejected=[Item(**d) for d in data.get("rejected") or []],
    )


def save(path: Path, state: State) -> None:
    payload = asdict(state)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))
    tmp.replace(path)
