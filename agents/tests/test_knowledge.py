from pathlib import Path

import yaml

_KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge" / "known_false_positives.yaml"


def test_knowledge_file_exists() -> None:
    assert _KNOWLEDGE.is_file()


def test_knowledge_file_is_valid_yaml() -> None:
    data = yaml.safe_load(_KNOWLEDGE.read_text())
    assert isinstance(data, dict)


def test_knowledge_has_expected_top_level_key() -> None:
    data = yaml.safe_load(_KNOWLEDGE.read_text())
    assert "false_positives" in data
    assert isinstance(data["false_positives"], list)


def test_each_entry_has_required_fields() -> None:
    data = yaml.safe_load(_KNOWLEDGE.read_text())
    required = {"fingerprint", "reason", "added", "added_by"}
    for entry in data["false_positives"]:
        assert required.issubset(entry.keys()), f"missing keys in {entry}"
