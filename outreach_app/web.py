from __future__ import annotations

import os
from pathlib import Path
from secrets import token_urlsafe
from tempfile import NamedTemporaryFile

from flask import Flask, redirect, render_template, request, session, url_for

from .db import DB_PATH, init_db
from .mailer import make_web_flow, save_client_config, save_token, send_email
from .store import (
    create_campaign,
    get_gmail_account,
    history,
    list_campaigns,
    list_recipients,
    mark_send_failure,
    mark_send_success,
    preview_email,
    save_gmail_account,
)


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-dev-only-change-me")
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    init_db(db_path)

    @app.get("/")
    def index():
        return render_template("index.html", campaigns=list_campaigns(app.config["DB_PATH"]), db_path=DB_PATH)

    @app.route("/gmail", methods=["GET", "POST"])
    def gmail():
        error = None
        if request.method == "POST":
            try:
                upload = request.files.get("client_secret")
                if upload is None or not upload.filename:
                    raise ValueError("Upload a Google OAuth client JSON file")
                client_config_json = upload.read().decode("utf-8")
                save_client_config(client_config_json)
                session["gmail_email"] = request.form["email"]
                session["oauth_state"] = token_urlsafe(24)
                flow = make_web_flow(url_for("gmail_callback", _external=True), session["oauth_state"])
                auth_url, state = flow.authorization_url(
                    access_type="offline",
                    include_granted_scopes="true",
                    prompt="consent",
                )
                session["oauth_state"] = state
                return redirect(auth_url)
            except Exception as exc:
                error = str(exc)
        return render_template("gmail.html", error=error)

    @app.get("/gmail/callback")
    def gmail_callback():
        email = session.get("gmail_email")
        state = session.get("oauth_state")
        if not email or not state:
            return redirect(url_for("gmail"))
        flow = make_web_flow(url_for("gmail_callback", _external=True), state)
        flow.fetch_token(authorization_response=request.url)
        save_token(email, flow.credentials)
        save_gmail_account(email, app.config["DB_PATH"])
        session.pop("gmail_email", None)
        session.pop("oauth_state", None)
        return redirect(url_for("index"))

    @app.route("/campaigns/new", methods=["GET", "POST"])
    def new_campaign():
        error = None
        if request.method == "POST":
            upload = request.files.get("recipients")
            if upload is None or not upload.filename:
                error = "Upload a recipient JSON file"
            else:
                tmp_path = None
                try:
                    with NamedTemporaryFile("wb", suffix=".json", delete=False) as tmp:
                        upload.save(tmp)
                        tmp_path = tmp.name
                    campaign_id = create_campaign(
                        request.form["name"],
                        request.form["subject_template"],
                        request.form["body_template"],
                        tmp_path,
                        app.config["DB_PATH"],
                    )
                    return redirect(url_for("campaign_detail", campaign_id=campaign_id))
                except Exception as exc:
                    error = str(exc)
                finally:
                    if tmp_path:
                        Path(tmp_path).unlink(missing_ok=True)
        return render_template("new_campaign.html", error=error)

    @app.get("/campaigns/<int:campaign_id>")
    def campaign_detail(campaign_id: int):
        status = request.args.get("status") or None
        return render_template(
            "campaign.html",
            campaign_id=campaign_id,
            recipients=list_recipients(campaign_id, status, app.config["DB_PATH"]),
            selected_status=status,
        )

    @app.get("/recipients/<int:recipient_id>")
    def recipient_preview(recipient_id: int):
        return render_template(
            "preview.html",
            rendered=preview_email(recipient_id, app.config["DB_PATH"]),
            logs=history(None, app.config["DB_PATH"]),
        )

    @app.post("/recipients/<int:recipient_id>/send")
    def send_recipient(recipient_id: int):
        rendered = preview_email(recipient_id, app.config["DB_PATH"])
        try:
            account = get_gmail_account(app.config["DB_PATH"])
            send_email(account, rendered["to_email"], rendered["subject"], rendered["body"])
            mark_send_success(recipient_id, rendered["subject"], rendered["body"], app.config["DB_PATH"])
        except Exception as exc:
            mark_send_failure(recipient_id, rendered["subject"], rendered["body"], str(exc), app.config["DB_PATH"])
        return redirect(url_for("recipient_preview", recipient_id=recipient_id))

    @app.post("/campaigns/<int:campaign_id>/send")
    def send_batch(campaign_id: int):
        limit = int(request.form.get("limit") or 10)
        recipients = list_recipients(campaign_id, "pending", app.config["DB_PATH"])[:limit]
        account = get_gmail_account(app.config["DB_PATH"])
        for recipient in recipients:
            rendered = preview_email(recipient["id"], app.config["DB_PATH"])
            try:
                send_email(account, rendered["to_email"], rendered["subject"], rendered["body"])
                mark_send_success(recipient["id"], rendered["subject"], rendered["body"], app.config["DB_PATH"])
            except Exception as exc:
                mark_send_failure(recipient["id"], rendered["subject"], rendered["body"], str(exc), app.config["DB_PATH"])
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))

    @app.get("/history")
    def send_history():
        return render_template("history.html", logs=history(None, app.config["DB_PATH"]))

    return app


def main() -> None:
    app = create_app()
    app.run(debug=True)


if __name__ == "__main__":
    main()
