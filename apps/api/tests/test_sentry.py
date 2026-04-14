import os
from unittest.mock import patch

from api.sentry import init_sentry


def test_init_sentry_noop_when_dsn_missing() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert init_sentry() is False


def test_init_sentry_called_when_dsn_set() -> None:
    with patch.dict(os.environ, {"SENTRY_DSN": "https://k@s.io/1"}), patch(
        "api.sentry.sentry_sdk.init"
    ) as mock_init:
        assert init_sentry() is True
        mock_init.assert_called_once()
