"""Minimal Sentry REST API client — list_events, counts_by_fingerprint."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx

_BASE_URL = "https://sentry.io/api/0"


def _client() -> httpx.Client:
    token = os.environ["SENTRY_AUTH_TOKEN"]
    return httpx.Client(
        base_url=_BASE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )


def list_events(
    organization_slug: str,
    project_slug: str,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    if since is None:
        since = datetime.now(UTC) - timedelta(hours=24)
    with _client() as c:
        resp = c.get(
            f"/projects/{organization_slug}/{project_slug}/events/",
            params={"since": since.isoformat()},
        )
        resp.raise_for_status()
        return cast(list[dict[str, Any]], resp.json())
