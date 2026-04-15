"""Local file-system tool executors for the GH Models tool-use loop."""

import json
import re
from collections.abc import Callable
from pathlib import Path

_MAX_FILE_SIZE = 256 * 1024
_MAX_GLOB_MATCHES = 100
_MAX_GREP_MATCHES = 200


def _safe_path(raw: str) -> Path:
    cwd = Path.cwd().resolve()
    candidate = (cwd / raw).resolve()
    try:
        candidate.relative_to(cwd)
    except ValueError as e:
        raise ValueError(f"path {raw!r} escapes working directory") from e
    return candidate


def read(path: str, **_: object) -> str:
    p = _safe_path(path)
    if not p.is_file():
        return f"ERROR: {path} does not exist or is not a file"
    if p.stat().st_size > _MAX_FILE_SIZE:
        return f"ERROR: {path} is {p.stat().st_size} bytes (> {_MAX_FILE_SIZE})"
    return p.read_text(encoding="utf-8", errors="replace")


def write(path: str, content: str, **_: object) -> str:
    content = _unescape(content)
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {path}"


def _unescape(s: str) -> str:
    """Some models send literal \\n instead of real newlines in tool args."""
    return s.replace("\\n", "\n").replace("\\t", "\t")


def edit(path: str, old_string: str, new_string: str, **_: object) -> str:
    old_string = _unescape(old_string)
    new_string = _unescape(new_string)
    p = _safe_path(path)
    if not p.is_file():
        return f"ERROR: {path} does not exist"
    original = p.read_text(encoding="utf-8")
    if old_string not in original:
        return f"ERROR: old_string not found in {path}"
    count = original.count(old_string)
    if count > 1:
        return f"ERROR: old_string appears {count} times in {path} — make it more specific"
    p.write_text(original.replace(old_string, new_string, 1), encoding="utf-8")
    return f"Edited {path} ({len(old_string)}→{len(new_string)} chars)"


def glob(pattern: str, **_: object) -> str:
    cwd = Path.cwd()
    matches = sorted(str(p.relative_to(cwd)) for p in cwd.glob(pattern) if p.is_file())
    if len(matches) > _MAX_GLOB_MATCHES:
        return "\n".join(matches[:_MAX_GLOB_MATCHES]) + f"\n... and {len(matches) - _MAX_GLOB_MATCHES} more"
    return "\n".join(matches) if matches else "(no matches)"


def grep(pattern: str, path: str = ".", **_: object) -> str:
    cwd = Path.cwd()
    root = _safe_path(path) if path != "." else cwd
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"ERROR: invalid regex: {e}"
    hits: list[str] = []
    targets = root.rglob("*") if root.is_dir() else [root]
    for file in targets:
        if not file.is_file():
            continue
        if file.stat().st_size > _MAX_FILE_SIZE:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                hits.append(f"{file.relative_to(cwd)}:{lineno}: {line.rstrip()}")
                if len(hits) >= _MAX_GREP_MATCHES:
                    return "\n".join(hits) + f"\n... (capped at {_MAX_GREP_MATCHES})"
    return "\n".join(hits) if hits else "(no matches)"


TOOL_IMPLS: dict[str, Callable[..., str]] = {
    "Read": read,
    "Write": write,
    "Edit": edit,
    "Glob": glob,
    "Grep": grep,
}


def execute(name: str, arguments_json: str) -> str:
    fn = TOOL_IMPLS.get(name)
    if fn is None:
        return f"ERROR: unknown tool {name!r}"
    try:
        kwargs: dict[str, object] = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return f"ERROR: invalid tool arguments JSON: {e}"
    try:
        return str(fn(**kwargs))
    except Exception as e:
        return f"ERROR: tool {name} raised {type(e).__name__}: {e}"
