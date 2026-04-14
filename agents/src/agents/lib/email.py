"""Send transactional emails via Resend."""

import os

import httpx

_DEFAULT_FROM = "ai-harness@onresend.dev"


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    from_addr: str | None = None,
) -> str:
    """Send an email via Resend; return the message id."""
    api_key = os.environ["RESEND_API_KEY"]
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": from_addr or _DEFAULT_FROM,
            "to": [to],
            "subject": subject,
            "html": body,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return str(resp.json()["id"])
