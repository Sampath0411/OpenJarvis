"""Email automation — send emails via configured SMTP.

Requires email to be configured in Settings (or .env). The SMTP
credentials are loaded by server.py into _EMAIL_CONFIG.
"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from .registry import tool

# This module-level dict is patched at startup by server.py with the
# actual _EMAIL_CONFIG so the tool can send without importing server.
_CREDENTIALS: dict = {}


def patch_credentials(cfg: dict) -> None:
    """Called once at import time from server.py to share the email config."""
    _CREDENTIALS.clear()
    _CREDENTIALS.update(cfg)


@tool(
    name="send_email",
    description="Send an email to one or more recipients via SMTP. "
                "Requires email to be configured in Settings first. "
                "Use this when the user asks to send an email.",
    parameters={
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address(es). "
                               "Multiple recipients separated by comma.",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line.",
            },
            "body": {
                "type": "string",
                "description": "Email body text (plain text).",
            },
            "html": {
                "type": "boolean",
                "description": "Set to true if body contains HTML. Default false.",
            },
        },
        "required": ["to", "subject", "body"],
    },
)
def send_email(to: str, subject: str, body: str, html: bool = False) -> str:
    """Send an email via the configured SMTP server."""
    if not _CREDENTIALS.get("smtp_host") or not _CREDENTIALS.get("email"):
        return (
            "❌ Email is not configured. "
            "Open Settings → Email and enter your SMTP credentials, "
            "or set JARVIS_EMAIL / JARVIS_EMAIL_PASSWORD in .env."
        )
    if not _CREDENTIALS.get("password"):
        return "❌ Email password is not configured."
    try:
        msg = MIMEText(body, "html" if html else "plain")
        msg["Subject"] = subject
        msg["From"] = _CREDENTIALS["email"]
        msg["To"] = to

        port = int(_CREDENTIALS.get("smtp_port", 587))
        if port == 465:
            with smtplib.SMTP_SSL(
                _CREDENTIALS["smtp_host"], port,
            ) as s:
                s.login(_CREDENTIALS["email"], _CREDENTIALS.get("password", ""))
                s.send_message(msg)
        else:
            with smtplib.SMTP(
                _CREDENTIALS["smtp_host"], port,
            ) as s:
                s.starttls()
                s.login(_CREDENTIALS["email"], _CREDENTIALS.get("password", ""))
                s.send_message(msg)

        return f"✅ Email sent to {to} with subject \"{subject}\"."
    except Exception as exc:
        return f"❌ Failed to send email: {exc}"
