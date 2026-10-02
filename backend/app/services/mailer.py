"""Dev mail. Mailpit only — no real email is ever sent.

If Mailpit is unreachable we log and carry on. A user asking for a magic link
should not get a 500 because a convenience container is down.
decisions/0007-mailpit-dev-mail.md
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger(__name__)

_warned = False


def _warn_once() -> None:
    global _warned
    if not _warned:
        _warned = True
        log.warning(
            "Mailpit at %s:%s is not reachable — magic links will not be delivered. "
            "Check `docker compose ps mailpit`. The app still works.",
            get_settings().mailpit_smtp_host,
            get_settings().mailpit_smtp_port,
        )


def send_magic_link(to_email: str, link: str) -> bool:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = "Your Bootcamp Connect sign-in link"
    msg["From"] = settings.mail_from
    msg["To"] = to_email
    msg.set_content(
        f"Sign in to Bootcamp Connect:\n\n{link}\n\n"
        "This link works once and expires in "
        f"{settings.magic_link_minutes} minutes.\n"
        "If you did not ask for this, ignore it.\n"
    )
    try:
        with smtplib.SMTP(
            settings.mailpit_smtp_host, settings.mailpit_smtp_port, timeout=5
        ) as smtp:
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 - deliberate: mail is optional
        _warn_once()
        log.warning("Could not send magic link to %s: %s", to_email, exc)
        return False