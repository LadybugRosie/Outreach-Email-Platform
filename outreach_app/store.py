from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import keyring

from .db import connect, init_db
from .mailer import SMTPAccount
from .rendering import render, required_fields


KEYRING_SERVICE = "outreach-email-platform"


def configure_smtp(
    email: str,
    host: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool = True,
    db_path: str | None = None,
) -> None:
    init_db(db_path)
    keyring.set_password(KEYRING_SERVICE, username, password)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO smtp_accounts (id, email, host, port, username, use_tls, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
              email = excluded.email,
              host = excluded.host,
              port = excluded.port,
              username = excluded.username,
              use_tls = excluded.use_tls,
              updated_at = CURRENT_TIMESTAMP
            """,
            (email, host, port, username, int(use_tls)),
        )


def get_smtp_account(db_path: str | None = None) -> SMTPAccount:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM smtp_accounts WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("SMTP account is not configured")
    password = keyring.get_password(KEYRING_SERVICE, row["username"])
    if not password:
        raise RuntimeError("SMTP password was not found in the OS keychain")
    return SMTPAccount(
        email=row["email"],
        host=row["host"],
        port=int(row["port"]),
        username=row["username"],
        use_tls=bool(row["use_tls"]),
        password=password,
    )


def create_campaign(
    name: str,
    subject_template: str,
    body_template: str,
    recipients_path: str,
    db_path: str | None = None,
) -> int:
    init_db(db_path)
    recipients = _load_recipients(Path(recipients_path))
    expected = required_fields(subject_template, body_template)

    with connect(db_path) as conn:
        campaign_id = conn.execute(
            """
            INSERT INTO campaigns (name, subject_template, body_template)
            VALUES (?, ?, ?)
            """,
            (name, subject_template, body_template),
        ).lastrowid
        for item in recipients:
            missing = sorted(expected - {_normalize_key(key) for key in item.keys()})
            if missing:
                raise ValueError(f"Recipient {item!r} is missing fields: {', '.join(missing)}")
            email = item.get("email") or item.get("Email") or item.get("to") or item.get("To")
            if not email:
                raise ValueError(f"Recipient {item!r} must include email, Email, to, or To")
            conn.execute(
                """
                INSERT INTO recipients (campaign_id, email, data_json)
                VALUES (?, ?, ?)
                """,
                (campaign_id, str(email), json.dumps(item, sort_keys=True)),
            )
    return int(campaign_id)


def list_campaigns(db_path: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
              c.*,
              COUNT(r.id) AS recipient_count,
              SUM(CASE WHEN r.status = 'sent' THEN 1 ELSE 0 END) AS sent_count,
              SUM(CASE WHEN r.status = 'failed' THEN 1 ELSE 0 END) AS failed_count
            FROM campaigns c
            LEFT JOIN recipients r ON r.campaign_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_recipients(campaign_id: int, status: str | None = None, db_path: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    query = "SELECT * FROM recipients WHERE campaign_id = ?"
    params: list[Any] = [campaign_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id"
    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_recipient_to_dict(row) for row in rows]


def get_campaign(campaign_id: int, db_path: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if row is None:
        raise ValueError(f"Campaign {campaign_id} does not exist")
    return dict(row)


def get_recipient(recipient_id: int, db_path: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM recipients WHERE id = ?", (recipient_id,)).fetchone()
    if row is None:
        raise ValueError(f"Recipient {recipient_id} does not exist")
    return _recipient_to_dict(row)


def preview_email(recipient_id: int, db_path: str | None = None) -> dict[str, Any]:
    recipient = get_recipient(recipient_id, db_path)
    campaign = get_campaign(int(recipient["campaign_id"]), db_path)
    return {
        "recipient": recipient,
        "campaign": campaign,
        "to_email": recipient["email"],
        "subject": render(campaign["subject_template"], recipient["data"]),
        "body": render(campaign["body_template"], recipient["data"]),
    }


def mark_send_success(recipient_id: int, subject: str, body: str, db_path: str | None = None) -> None:
    recipient = get_recipient(recipient_id, db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE recipients
            SET status = 'sent', last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (recipient_id,),
        )
        conn.execute(
            """
            INSERT INTO send_log (recipient_id, campaign_id, to_email, subject, body, status)
            VALUES (?, ?, ?, ?, ?, 'sent')
            """,
            (recipient_id, recipient["campaign_id"], recipient["email"], subject, body),
        )


def mark_send_failure(recipient_id: int, subject: str, body: str, error: str, db_path: str | None = None) -> None:
    recipient = get_recipient(recipient_id, db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE recipients
            SET status = 'failed', last_error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error, recipient_id),
        )
        conn.execute(
            """
            INSERT INTO send_log (recipient_id, campaign_id, to_email, subject, body, status, error)
            VALUES (?, ?, ?, ?, ?, 'failed', ?)
            """,
            (recipient_id, recipient["campaign_id"], recipient["email"], subject, body, error),
        )


def history(campaign_id: int | None = None, db_path: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    query = "SELECT * FROM send_log"
    params: list[Any] = []
    if campaign_id is not None:
        query += " WHERE campaign_id = ?"
        params.append(campaign_id)
    query += " ORDER BY sent_at DESC"
    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _load_recipients(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and isinstance(data.get("recipients"), list):
        data = data["recipients"]
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("Recipient JSON must be a list of objects or an object with a recipients list")
    return data


def _recipient_to_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["data"] = json.loads(item.pop("data_json"))
    return item


def _normalize_key(value: str) -> str:
    from .rendering import _field_key

    return _field_key(value)
