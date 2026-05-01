from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class SMTPAccount:
    email: str
    host: str
    port: int
    username: str
    use_tls: bool
    password: str


def send_email(account: SMTPAccount, to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = account.email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(account.host, account.port, timeout=30) as smtp:
        smtp.ehlo()
        if account.use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(account.username, account.password)
        smtp.send_message(message)
