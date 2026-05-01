from __future__ import annotations

import argparse
import getpass
import sys

from .db import init_db
from .mailer import send_email
from .store import (
    configure_smtp,
    create_campaign,
    get_smtp_account,
    history,
    list_campaigns,
    list_recipients,
    mark_send_failure,
    mark_send_success,
    preview_email,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outreach")
    parser.add_argument("--db", help="Path to SQLite database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize the local database")

    smtp_parser = subparsers.add_parser("smtp-config", help="Save SMTP settings and password")
    smtp_parser.add_argument("--email", required=True)
    smtp_parser.add_argument("--host", required=True)
    smtp_parser.add_argument("--port", type=int, default=587)
    smtp_parser.add_argument("--username", required=True)
    smtp_parser.add_argument("--no-tls", action="store_true")

    campaign_parser = subparsers.add_parser("campaign-create", help="Create a campaign from templates and JSON")
    campaign_parser.add_argument("--name", required=True)
    campaign_parser.add_argument("--subject", required=True)
    campaign_parser.add_argument("--body-file", required=True)
    campaign_parser.add_argument("--recipients", required=True)

    subparsers.add_parser("campaign-list", help="List campaigns")

    recipient_parser = subparsers.add_parser("recipient-list", help="List campaign recipients")
    recipient_parser.add_argument("campaign_id", type=int)
    recipient_parser.add_argument("--status", choices=["pending", "sent", "failed"])

    preview_parser = subparsers.add_parser("preview", help="Preview one rendered email")
    preview_parser.add_argument("recipient_id", type=int)

    send_parser = subparsers.add_parser("send", help="Send pending emails for a campaign")
    send_parser.add_argument("campaign_id", type=int)
    send_parser.add_argument("--limit", type=int)
    send_parser.add_argument("--yes", action="store_true", help="Do not ask for per-email confirmation")
    send_parser.add_argument("--retry-failed", action="store_true")

    history_parser = subparsers.add_parser("history", help="Show send history")
    history_parser.add_argument("--campaign-id", type=int)

    args = parser.parse_args(argv)

    if args.command == "init":
        print(f"Initialized {init_db(args.db)}")
        return 0
    if args.command == "smtp-config":
        password = getpass.getpass("SMTP password: ")
        configure_smtp(args.email, args.host, args.port, args.username, password, not args.no_tls, args.db)
        print("SMTP account saved")
        return 0
    if args.command == "campaign-create":
        body = _read_text(args.body_file)
        campaign_id = create_campaign(args.name, args.subject, body, args.recipients, args.db)
        print(f"Created campaign {campaign_id}")
        return 0
    if args.command == "campaign-list":
        for campaign in list_campaigns(args.db):
            print(
                f"{campaign['id']}: {campaign['name']} "
                f"({campaign['sent_count'] or 0}/{campaign['recipient_count']} sent, "
                f"{campaign['failed_count'] or 0} failed)"
            )
        return 0
    if args.command == "recipient-list":
        for recipient in list_recipients(args.campaign_id, args.status, args.db):
            print(f"{recipient['id']}: {recipient['email']} [{recipient['status']}] {recipient.get('last_error') or ''}")
        return 0
    if args.command == "preview":
        rendered = preview_email(args.recipient_id, args.db)
        print(f"To: {rendered['to_email']}")
        print(f"Subject: {rendered['subject']}")
        print()
        print(rendered["body"])
        return 0
    if args.command == "send":
        return _send_campaign(args.campaign_id, args.limit, args.yes, args.retry_failed, args.db)
    if args.command == "history":
        for item in history(args.campaign_id, args.db):
            suffix = f" error={item['error']}" if item["error"] else ""
            print(f"{item['sent_at']} {item['status']} campaign={item['campaign_id']} to={item['to_email']}{suffix}")
        return 0
    return 1


def _send_campaign(campaign_id: int, limit: int | None, yes: bool, retry_failed: bool, db_path: str | None) -> int:
    account = get_smtp_account(db_path)
    statuses = ["pending", "failed"] if retry_failed else ["pending"]
    recipients = []
    for status in statuses:
        recipients.extend(list_recipients(campaign_id, status, db_path))
    if limit is not None:
        recipients = recipients[:limit]

    sent = 0
    failed = 0
    for recipient in recipients:
        rendered = preview_email(recipient["id"], db_path)
        if not yes:
            print(f"\nTo: {rendered['to_email']}")
            print(f"Subject: {rendered['subject']}")
            print(rendered["body"])
            answer = input("Send this email? [y/N] ").strip().lower()
            if answer != "y":
                continue
        try:
            send_email(account, rendered["to_email"], rendered["subject"], rendered["body"])
            mark_send_success(recipient["id"], rendered["subject"], rendered["body"], db_path)
            sent += 1
            print(f"sent {recipient['id']} -> {rendered['to_email']}")
        except Exception as exc:
            failed += 1
            mark_send_failure(recipient["id"], rendered["subject"], rendered["body"], str(exc), db_path)
            print(f"failed {recipient['id']} -> {rendered['to_email']}: {exc}", file=sys.stderr)
    print(f"Complete: {sent} sent, {failed} failed")
    return 1 if failed else 0


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


if __name__ == "__main__":
    raise SystemExit(main())
