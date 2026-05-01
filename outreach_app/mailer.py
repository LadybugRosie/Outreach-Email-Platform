from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from email.message import EmailMessage

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

KEYRING_SERVICE = "outreach-email-platform"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES = [GMAIL_SEND_SCOPE]


@dataclass
class GmailAccount:
    email: str
    credentials: Credentials


def save_client_config(client_config_json: str) -> None:
    config = json.loads(client_config_json)
    if "installed" not in config and "web" not in config:
        raise ValueError("Google OAuth client JSON must contain an installed or web client")
    keyring.set_password(KEYRING_SERVICE, "gmail_oauth_client_config", json.dumps(config))


def get_client_config() -> dict:
    raw = keyring.get_password(KEYRING_SERVICE, "gmail_oauth_client_config")
    if not raw:
        raise RuntimeError("Gmail OAuth client config is not saved")
    return json.loads(raw)


def run_local_oauth(email: str, client_config_json: str | None = None) -> Credentials:
    if client_config_json:
        save_client_config(client_config_json)
    flow = InstalledAppFlow.from_client_config(get_client_config(), SCOPES)
    credentials = flow.run_local_server(port=0)
    save_token(email, credentials)
    return credentials


def make_web_flow(redirect_uri: str, state: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        get_client_config(),
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri,
    )
    return flow


def save_token(email: str, credentials: Credentials) -> None:
    keyring.set_password(KEYRING_SERVICE, _token_key(email), credentials.to_json())


def load_credentials(email: str) -> Credentials:
    raw = keyring.get_password(KEYRING_SERVICE, _token_key(email))
    if not raw:
        raise RuntimeError(f"Gmail OAuth token was not found for {email}")
    credentials = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_token(email, credentials)
    if not credentials.valid:
        raise RuntimeError(f"Gmail OAuth token for {email} is not valid; reconnect Gmail")
    return credentials


def send_email(account: GmailAccount, to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = account.email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    service = build("gmail", "v1", credentials=account.credentials)
    service.users().messages().send(userId="me", body={"raw": encoded}).execute()


def _token_key(email: str) -> str:
    return f"gmail_oauth_token:{email.lower()}"
