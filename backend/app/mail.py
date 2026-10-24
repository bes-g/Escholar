"""Match notices. The dashboard always stores them. Email is sent when SMTP is configured."""

import smtplib
from email.message import EmailMessage

from app.config import settings


def email_configured() -> bool:
    return bool(settings.smtp_host.strip() and settings.smtp_from.strip())


def send_match_email(recipient: str, subject: str, body: str) -> str:
    if not email_configured():
        return "skipped"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from.strip()
    message["To"] = recipient
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host.strip(), settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if settings.smtp_user.strip():
                smtp.login(settings.smtp_user.strip(), settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        return "failed"
    return "sent"
