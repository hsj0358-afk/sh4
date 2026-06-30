"""Gmail SMTP 발송 (앱 비밀번호 사용)."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from .settings import Settings

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL


def send_briefing(settings: Settings, subject: str, text_body: str, html_body: str) -> None:
    if not (settings.gmail_user and settings.gmail_app_password and settings.briefing_to):
        raise RuntimeError("Gmail 설정(GMAIL_USER/GMAIL_APP_PASSWORD/BRIEFING_TO)이 비어 있습니다.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.briefing_from_name, settings.gmail_user))
    msg["To"] = ", ".join(settings.briefing_to)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.sendmail(settings.gmail_user, settings.briefing_to, msg.as_string())
    log.info("브리핑 메일 발송 완료 → %s", ", ".join(settings.briefing_to))
