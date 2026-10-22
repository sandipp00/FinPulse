"""Sending the account emails (address verification and password reset).

Three backends, chosen by EMAIL_BACKEND (see backend/config.py):
  smtp     talk to any SMTP server, including the free tiers of common providers
  console  write the email, link included, to the server log (development only)
  off      send nothing

Emails are built with the standard library's EmailMessage, which refuses
newlines in headers, so a hostile address cannot inject extra headers.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from backend import config

log = logging.getLogger("finpulse.mail")

SMTP_TIMEOUT_SECONDS = 10


class MailError(Exception):
    """The email could not be sent."""


def enabled() -> bool:
    return config.EMAIL_BACKEND in ("smtp", "console")


def build_message(to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.EMAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_email(to: str, subject: str, body: str) -> None:
    """Deliver one plain-text email. Raises MailError if it cannot be sent."""
    backend = config.EMAIL_BACKEND

    if backend == "off":
        return

    try:
        message = build_message(to, subject, body)
    except ValueError as exc:  # e.g. a newline in the address
        raise MailError(f"Invalid email headers: {exc}") from exc

    if backend == "console":
        log.warning("EMAIL (console backend)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return

    if backend != "smtp" or not config.SMTP_HOST:
        raise MailError(f"Email backend {backend!r} is not usable (is SMTP_HOST set?).")

    try:
        if config.SMTP_SSL:
            client = smtplib.SMTP_SSL(
                config.SMTP_HOST, config.SMTP_PORT,
                timeout=SMTP_TIMEOUT_SECONDS, context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
        with client:
            if config.SMTP_STARTTLS and not config.SMTP_SSL:
                client.starttls(context=ssl.create_default_context())
            if config.SMTP_USER:
                client.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
            client.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"SMTP delivery failed: {type(exc).__name__}: {exc}") from exc


def send_quietly(to: str, subject: str, body: str) -> None:
    """Send an email from a background task: log failures instead of raising.

    The requester is never told whether delivery worked, so errors here cannot
    be used to learn anything about an address; they are for the operator's log.
    """
    try:
        send_email(to, subject, body)
    except MailError as exc:
        log.error("Could not send email to %s: %s", to, exc)


# ---- the emails themselves ------------------------------------------------------

def verification_email(link: str) -> tuple[str, str]:
    return (
        "Confirm your email for FinPulse",
        "Welcome to FinPulse!\n\n"
        "Confirm this email address to start paper trading:\n\n"
        f"{link}\n\n"
        f"The link works once and expires in {config.VERIFY_TOKEN_HOURS} hours.\n"
        "If you did not create a FinPulse account, you can ignore this email.\n",
    )


def reset_email(link: str) -> tuple[str, str]:
    return (
        "Reset your FinPulse password",
        "Someone asked to reset the password for this FinPulse account.\n\n"
        "To choose a new password, open:\n\n"
        f"{link}\n\n"
        f"The link works once and expires in {config.RESET_TOKEN_MINUTES} minutes. "
        "Using it signs you out everywhere.\n"
        "If this was not you, ignore this email: your password has not changed.\n",
    )
