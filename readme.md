# Outreach Email Platform

A small local-first application for personalized email outreach. It supports:

- Email templates with variables like `{Club Name}` and `{Contact Name}`.
- JSON recipient uploads that fill those template variables.
- SMTP email sending from your own email account.
- A web UI for previewing, confirming, batch sending, and viewing history.
- A CLI for creating campaigns and sending batches.
- SQLite persistence across sessions.
- Safer credential storage through the operating system keychain via `keyring`.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Recipient JSON Format

The upload can be either a list of recipient objects:

```json
[
  {
    "email": "coach@example.com",
    "Club Name": "Northside Rowing",
    "Contact Name": "Alex"
  }
]
```

Or an object with a `recipients` list:

```json
{
  "recipients": [
    {
      "email": "coach@example.com",
      "Club Name": "Northside Rowing",
      "Contact Name": "Alex"
    }
  ]
}
```

Each recipient must include `email`, `Email`, `to`, or `To`. Every variable used in the subject or body template must exist on each recipient object.

## Web UI

Start the web app:

```bash
outreach-web
```

Then open:

```text
http://127.0.0.1:5000
```

Recommended first-time flow:

1. Go to `Email Account` and enter SMTP settings.
2. Go to `New Campaign`.
3. Enter a subject template, body template, and upload the recipient JSON file.
4. Open a recipient to preview the rendered email.
5. Click `Confirm and Send` for one email, or use `Send Pending Batch` from the campaign page.
6. Use `History` to review sent and failed attempts.

## CLI Usage

Initialize the database:

```bash
outreach init
```

Save SMTP settings. The command prompts for the password and stores it in the OS keychain:

```bash
outreach smtp-config \
  --email you@example.com \
  --host smtp.example.com \
  --port 587 \
  --username you@example.com
```

Create a campaign from a subject, body file, and recipient JSON:

```bash
outreach campaign-create \
  --name "Spring outreach" \
  --subject "Partnership with {Club Name}" \
  --body-file body.txt \
  --recipients recipients.json
```

List campaigns:

```bash
outreach campaign-list
```

Preview one rendered email:

```bash
outreach preview 1
```

Send pending emails for a campaign with confirmation before each send:

```bash
outreach send 1 --limit 10
```

Send without per-email confirmation:

```bash
outreach send 1 --limit 10 --yes
```

Retry failed recipients:

```bash
outreach send 1 --retry-failed --yes
```

View send history:

```bash
outreach history
```

## Data Storage

By default, the SQLite database is stored at:

```text
~/.outreach_email_platform/outreach.sqlite3
```

SMTP passwords are not stored in that database. They are saved using your operating system keychain through the Python `keyring` package.

For testing or separate environments, pass a database path:

```bash
outreach --db ./dev.sqlite3 campaign-list
```

## Email Provider Notes

Most providers require an app password or SMTP-specific password instead of your normal login password. For example, Gmail accounts usually require 2-Step Verification and an app password for SMTP access.

Common SMTP defaults:

- Gmail: `smtp.gmail.com`, port `587`, STARTTLS enabled.
- Outlook / Microsoft 365: `smtp.office365.com`, port `587`, STARTTLS enabled.

## Current Scope

This is intentionally a small local application. It does not include multi-user authentication, OAuth email provider flows, unsubscribe management, bounce tracking, rate limiting, or deliverability tooling. Add those before using it as a production outreach system.
