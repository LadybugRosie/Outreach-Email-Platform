from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from flask import Flask, redirect, render_template, request, url_for

from .db import DB_PATH, init_db
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


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    init_db(db_path)

    @app.get("/")
    def index():
        return render_template("index.html", campaigns=list_campaigns(app.config["DB_PATH"]), db_path=DB_PATH)

    @app.route("/smtp", methods=["GET", "POST"])
    def smtp():
        error = None
        if request.method == "POST":
            try:
                configure_smtp(
                    request.form["email"],
                    request.form["host"],
                    int(request.form["port"]),
                    request.form["username"],
                    request.form["password"],
                    request.form.get("use_tls") == "on",
                    app.config["DB_PATH"],
                )
                return redirect(url_for("index"))
            except Exception as exc:
                error = str(exc)
        return render_template("smtp.html", error=error)

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
            account = get_smtp_account(app.config["DB_PATH"])
            send_email(account, rendered["to_email"], rendered["subject"], rendered["body"])
            mark_send_success(recipient_id, rendered["subject"], rendered["body"], app.config["DB_PATH"])
        except Exception as exc:
            mark_send_failure(recipient_id, rendered["subject"], rendered["body"], str(exc), app.config["DB_PATH"])
        return redirect(url_for("recipient_preview", recipient_id=recipient_id))

    @app.post("/campaigns/<int:campaign_id>/send")
    def send_batch(campaign_id: int):
        limit = int(request.form.get("limit") or 10)
        recipients = list_recipients(campaign_id, "pending", app.config["DB_PATH"])[:limit]
        account = get_smtp_account(app.config["DB_PATH"])
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
