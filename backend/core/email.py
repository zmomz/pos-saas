"""Lightweight email delivery for the provisioning path.

Used when master/agent creates a downstream account and we must hand the
merchant their one-time temporary password. Real SMTP is attempted only when
``SMTP_HOST`` is configured; otherwise it falls back to logging the message and
returning ``False`` so the caller can surface the temp password in the response
(dev/no-SMTP mode). The full notification-stack replacement lives in Phase 3.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from core.config import settings

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(getattr(settings, "smtp_host", None))


def _send_sync(to_email: str, subject: str, body: str) -> None:
    host = getattr(settings, "smtp_host", None)
    port = int(getattr(settings, "smtp_port", 587) or 587)
    username = getattr(settings, "smtp_username", None)
    password = getattr(settings, "smtp_password", None)
    sender = getattr(settings, "smtp_from", None) or username or "no-reply@localhost"
    use_tls = str(getattr(settings, "smtp_use_tls", "true")).lower() != "false"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=15) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send an email. Returns True if delivered via SMTP, False on dev fallback.

    Never raises — provisioning must not fail because email is misconfigured.
    """
    if not _smtp_configured():
        logger.info("Email (dev fallback) → %s | %s", to_email, subject)
        return False
    try:
        await asyncio.to_thread(_send_sync, to_email, subject, body)
        logger.info("Email sent → %s | %s", to_email, subject)
        return True
    except Exception as exc:  # pragma: no cover - network/SMTP failure path
        logger.warning("Email send failed (%s); falling back to dev mode", type(exc).__name__)
        return False


class _SafeDict(dict):
    """``str.format_map`` helper: an unknown ``{placeholder}`` renders empty rather
    than raising, so a malformed agent template never breaks provisioning."""

    def __missing__(self, key: str) -> str:  # noqa: D401 - dict hook
        return ""


def render_provisioning_email(
    *,
    to_email: str,
    business_name: str,
    temp_password: str,
    brand_name: str | None = None,
    login_url: str | None = None,
    subject_template: str | None = None,
    body_template: str | None = None,
) -> tuple[str, str]:
    """Build the (subject, body) of a provisioning email — AG-06 branded.

    Pure (no I/O) so it is unit-testable. When the owning agent supplies a custom
    template (``subject_template`` / ``body_template``) it is rendered with the
    ``{business_name}``/``{email}``/``{password}``/``{login_url}``/``{brand}``
    placeholders. Otherwise a **branded default** is produced that carries the
    agent's brand name and the agent's login URL (the agent's custom domain when
    set) — never the bare platform identity. A template that fails to render falls
    back to the branded default so a misconfigured template can't blank the email.
    """
    brand = (brand_name or "").strip() or "POS"
    where = login_url or getattr(settings, "frontend_url", None) or "your login page"
    fields = _SafeDict(
        business_name=business_name,
        email=to_email,
        password=temp_password,
        login_url=where,
        brand=brand,
    )

    if subject_template or body_template:
        try:
            subject = (subject_template or f"Your {brand} account is ready").format_map(fields)
            body = (
                body_template
                or (
                    "Hello {business_name},\n\n"
                    "An account has been created for you on {brand}.\n\n"
                    "  Email:    {email}\n"
                    "  Password: {password}\n\n"
                    "Sign in at {login_url} and you will be asked to change this "
                    "password on first login.\n"
                )
            ).format_map(fields)
            return subject, body
        except Exception:  # pragma: no cover - malformed template → branded default
            pass

    subject = f"Your {brand} account is ready"
    body = (
        f"Hello {business_name},\n\n"
        f"An account has been created for you on {brand}.\n\n"
        f"  Email:    {to_email}\n"
        f"  Password: {temp_password}\n\n"
        f"Sign in at {where} and you will be asked to change this password on first login.\n"
    )
    return subject, body


async def send_provisioning_email(
    to_email: str,
    business_name: str,
    temp_password: str,
    login_url: str | None = None,
    brand_name: str | None = None,
    subject_template: str | None = None,
    body_template: str | None = None,
) -> bool:
    """Email a freshly-provisioned account its login + one-time password (AG-06)."""
    subject, body = render_provisioning_email(
        to_email=to_email,
        business_name=business_name,
        temp_password=temp_password,
        brand_name=brand_name,
        login_url=login_url,
        subject_template=subject_template,
        body_template=body_template,
    )
    return await send_email(to_email, subject, body)
