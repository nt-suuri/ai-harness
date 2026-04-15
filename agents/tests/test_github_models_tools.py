import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.lib import tool_executors


def test_read_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "hello.txt").write_text("world", encoding="utf-8")
    assert tool_executors.read("hello.txt") == "world"


def test_read_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert "does not exist" in tool_executors.read("nope.txt")


def test_read_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = tool_executors.execute("Read", json.dumps({"path": "../escape"}))
    assert "escapes" in result.lower() or "valueerror" in result.lower()


def test_write_creates_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    tool_executors.write("sub/new.txt", "hi")
    assert (tmp_path / "sub" / "new.txt").read_text() == "hi"


def test_edit_replaces_unique(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "x.py"
    f.write_text("foo\nbar\n")
    assert "Edited" in tool_executors.edit("x.py", "foo", "FOO")
    assert f.read_text() == "FOO\nbar\n"


def test_edit_refuses_non_unique(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("foo\nfoo\n")
    assert "appears 2 times" in tool_executors.edit("x.py", "foo", "X")


def test_glob_returns_matches(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.txt").write_text("")
    result = tool_executors.glob("*.py")
    assert "a.py" in result and "b.py" in result and "c.txt" not in result


def test_grep_finds_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("alpha\nbeta\ngamma\n")
    result = tool_executors.grep("b.ta")
    assert "x.py:2" in result
    assert "beta" in result


def test_grep_invalid_regex(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert "ERROR" in tool_executors.grep("[unclosed")


def test_execute_unknown_tool() -> None:
    assert "unknown" in tool_executors.execute("Bogus", "{}").lower()


def test_execute_invalid_json_args() -> None:
    assert "invalid tool arguments" in tool_executors.execute("Read", "not json")


@pytest.mark.asyncio
async def test_gh_models_tool_loop_terminates_on_stop(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text("print('hi')")

    from agents.lib import github_models

    first = MagicMock(status_code=200)
    first.json = MagicMock(return_value={
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "Read", "arguments": json.dumps({"path": "foo.py"})},
                }],
            },
            "finish_reason": "tool_calls",
        }],
    })
    first.raise_for_status = MagicMock()

    second = MagicMock(status_code=200)
    second.json = MagicMock(return_value={
        "choices": [{
            "message": {"role": "assistant", "content": "Done — it prints hi.", "tool_calls": None},
            "finish_reason": "stop",
        }],
    })
    second.raise_for_status = MagicMock()

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=[first, second])
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True),
        patch("agents.lib.github_models.httpx.AsyncClient", return_value=fake_client),
    ):
        result = await github_models.run_agent(
            "explain foo.py",
            system="you are helpful",
            allowed_tools=["Read", "Write"],
        )

    assert result.stopped_reason == "complete"
    assert any("Done" in m.get("text", "") for m in result.messages if isinstance(m, dict))
    assert fake_client.post.call_count == 2
    second_body = fake_client.post.call_args_list[1].kwargs["json"]
    assert any(m.get("role") == "tool" and "print" in m.get("content", "") for m in second_body["messages"])


@pytest.mark.asyncio
async def test_gh_models_tool_loop_respects_max_turns(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text("x")

    from agents.lib import github_models

    never_stops = MagicMock(status_code=200)
    never_stops.json = MagicMock(return_value={
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "cN",
                    "type": "function",
                    "function": {"name": "Read", "arguments": json.dumps({"path": "foo.py"})},
                }],
            },
            "finish_reason": "tool_calls",
        }],
    })
    never_stops.raise_for_status = MagicMock()

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=never_stops)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True),
        patch("agents.lib.github_models.httpx.AsyncClient", return_value=fake_client),
    ):
        result = await github_models.run_agent(
            "loop forever",
            system="x",
            max_turns=3,
            allowed_tools=["Read"],
        )

    assert result.stopped_reason == "turn_cap"
    assert fake_client.post.call_count == 3
