from agents.lib import labels


def test_constants_match_expected_strings() -> None:
    assert labels.BUG == "bug"
    assert labels.AUTOTRIAGE == "autotriage"
    assert labels.REGRESSION == "regression"
    assert labels.AGENT_BUILD == "agent:build"
    assert labels.HEALTHCHECK == "healthcheck"


def test_severity_constants() -> None:
    assert labels.SEVERITY_CRITICAL == "severity:critical"
    assert labels.SEVERITY_IMPORTANT == "severity:important"
    assert labels.SEVERITY_MINOR == "severity:minor"


def test_severity_all_set() -> None:
    assert labels.SEVERITY_CRITICAL in labels.SEVERITY_ALL
    assert labels.SEVERITY_IMPORTANT in labels.SEVERITY_ALL
    assert labels.SEVERITY_MINOR in labels.SEVERITY_ALL
    assert len(labels.SEVERITY_ALL) == 3


def test_all_managed_includes_everything() -> None:
    for name in (labels.BUG, labels.AUTOTRIAGE, labels.REGRESSION, labels.HEALTHCHECK, labels.AGENT_BUILD):
        assert name in labels.ALL_MANAGED
    for sev in labels.SEVERITY_ALL:
        assert sev in labels.ALL_MANAGED
    for area in labels.AREA_ALL:
        assert area in labels.ALL_MANAGED


def test_no_duplicate_strings() -> None:
    """frozenset dedupes — verify minimum count."""
    assert isinstance(labels.ALL_MANAGED, frozenset)
    assert len(labels.ALL_MANAGED) >= 13
