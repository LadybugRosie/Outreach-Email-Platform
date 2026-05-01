# Mass Template Email Sender

A small local-first application for sending one Gmail template to many recipients. It supports:

- Email templates with variables like `{Club Name}` and `{Contact Name}`.
- JSON recipient uploads that fill those template variables.
- Gmail sending through OAuth and the Gmail API.
- A web UI for previewing, confirming, batch sending, and viewing history.
- A CLI for creating campaigns and sending batches.
- SQLite persistence across sessions.
- OAuth client config and refresh tokens stored through the operating system keychain via `keyring`.

## Install

Recommended setup with Python's built-in virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

If you use `uv`, install the editable project this way:

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

If the editable install succeeds, the console commands `outreach` and `outreach-web` may be available in your active virtual environment. If they are not available, use the module commands shown below; they work directly from the source tree as long as dependencies are installed.

Check the setup:

```bash
python -m outreach_app.cli --help
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
python -m outreach_app.web
```

If your editable install generated console scripts, this shorter command is equivalent:

```bash
outreach-web
```

Then open:

```text
http://127.0.0.1:5000
```

Recommended first-time flow:

1. Create a Google OAuth client JSON file in Google Cloud Console.
2. Go to `Gmail`, enter your Gmail address, upload the OAuth client JSON file, and approve Gmail send access.
3. Go to `New Batch`.
4. Enter a subject template, body template, and upload the recipient JSON file.
4. Open a recipient to preview the rendered email.
5. Click `Send email` for one email, or use `Send pending` from the batch page.
6. Use `Log` to review sent and failed attempts.

## Gmail OAuth Setup

Create an OAuth client in Google Cloud Console before connecting Gmail:

1. Create or select a Google Cloud project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Create an OAuth client ID.
5. For CLI use, choose a desktop app client.
6. For web UI use, choose a web app client and add this authorized redirect URI:

```text
http://127.0.0.1:5000/gmail/callback
```

Download the OAuth client JSON file. The app requests only this Gmail scope:

```text
https://www.googleapis.com/auth/gmail.send
```

## CLI Usage

The examples below use `python -m outreach_app.cli` because it works directly from the source tree. If your editable install generated console scripts, you can replace `python -m outreach_app.cli` with `outreach`.

Initialize the database:

```bash
python -m outreach_app.cli init
```

Connect Gmail with OAuth. This opens a browser for Google approval and stores the refresh token in the OS keychain:

```bash
python -m outreach_app.cli gmail-connect \
  --email you@example.com \
  --client-secret client_secret.json
```

Create a campaign from a subject, body file, and recipient JSON:

```bash
python -m outreach_app.cli campaign-create \
  --name "Spring outreach" \
  --subject "Partnership with {Club Name}" \
  --body-file body.txt \
  --recipients recipients.json
```

List campaigns:

```bash
python -m outreach_app.cli campaign-list
```

Preview one rendered email:

```bash
python -m outreach_app.cli preview 1
```

Send pending emails for a campaign with confirmation before each send:

```bash
python -m outreach_app.cli send 1 --limit 10
```

Send without per-email confirmation:

```bash
python -m outreach_app.cli send 1 --limit 10 --yes
```

Retry failed recipients:

```bash
python -m outreach_app.cli send 1 --retry-failed --yes
```

View send history:

```bash
python -m outreach_app.cli history
```

## Data Storage

By default, the SQLite database is stored at:

```text
~/.outreach_email_platform/outreach.sqlite3
```

Gmail OAuth tokens are not stored in that database. The OAuth client config and refresh token are saved using your operating system keychain through the Python `keyring` package.

For testing or separate environments, pass a database path:

```bash
python -m outreach_app.cli --db ./dev.sqlite3 campaign-list
```

## Current Scope

This is intentionally a small local application. It does not include multi-user authentication, unsubscribe management, bounce tracking, rate limiting, or deliverability tooling. Add those before using it as a production email system.
