"""Always-on Flask app: serves the interactive dashboard on the home LAN and
accepts annotation edits. Run via `python -m code.app` (see
house-bot-dashboard.service). Reads data/listings.csv (written nightly by the
bot) and reads/writes data/annotations.db.
"""
from pathlib import Path

import yaml
from flask import Flask, Response, jsonify, request

from code import annotations as ann
from code.html_writer import render_page

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(csv_path, db_path, tax_rates=None, min_price=None, max_price=None):
    app = Flask(__name__)
    csv_path, db_path = Path(csv_path), Path(db_path)
    ann.init_db(db_path)

    @app.get("/")
    def index():
        html = render_page(
            csv_path, tax_rates or {}, min_price, max_price,
            annotations=ann.get_all(db_path), interactive=True,
        )
        return Response(html or "<p>No listings yet.</p>", mimetype="text/html")

    @app.get("/api/annotations")
    def list_annotations():
        return jsonify(ann.get_all(db_path))

    @app.post("/api/annotations/<listing_id>")
    def set_annotation(listing_id):
        data = request.get_json(silent=True) or {}
        label = (data.get("status_label") or "").strip()
        note = (data.get("note") or "").strip()
        if label and label not in ann.STATUS_LABELS:
            return jsonify({"error": "invalid label"}), 400
        ann.upsert(db_path, listing_id, label, note)
        return jsonify({"ok": True})

    return app


def main():
    config = yaml.safe_load((BASE_DIR / "config" / "searches.yaml").read_text())
    tax_rates = {
        t["name"]: float(t.get("tax_rate_per_1000") or 0)
        for t in config.get("towns", [])
    }
    search_cfg = config.get("search", {})
    app = create_app(
        BASE_DIR / "data" / "listings.csv",
        BASE_DIR / "data" / "annotations.db",
        tax_rates,
        search_cfg.get("min_price"),
        search_cfg.get("max_price"),
    )
    port = int(config.get("dashboard", {}).get("port", 8000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
