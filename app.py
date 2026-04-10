"""CulturalMe — Flask app."""

import sqlite3
from datetime import date
from pathlib import Path

from flask import Flask, render_template, request

DB_PATH = Path(__file__).parent / "data" / "culturalme.db"

app = Flask(__name__)

SECTIONS = ["museo", "concierto", "galeria", "charla", "cine", "teatro"]
SECTION_LABELS = {
    "museo": "Museos",
    "concierto": "Conciertos",
    "galeria": "Galerías",
    "charla": "Charlas",
    "cine": "Cine",
    "teatro": "Teatro",
}


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@app.route("/")
def index():
    section_filter = request.args.get("section", "all")
    sort = request.args.get("sort", "nuevo")
    venue_filter = request.args.get("venue", "")

    con = get_db()

    row = con.execute("SELECT MAX(last_seen) as latest FROM events").fetchone()
    latest_run = row["latest"] if row else None

    today = date.today().isoformat()

    # Filtrar eventos vigentes
    conditions = [
        """(
            section = 'cine'
            OR date_end >= ?
            OR (date_end IS NULL AND date_start >= ?)
            OR (date_end IS NULL AND date_start IS NULL)
        )"""
    ]
    params = [today, today]

    if section_filter != "all" and section_filter in SECTIONS:
        conditions.append("section = ?")
        params.append(section_filter)

    if venue_filter:
        conditions.append("(source = ? OR venue = ?)")
        params.extend([venue_filter, venue_filter])

    where = "WHERE " + " AND ".join(conditions)

    if sort == "fecha":
        order = "COALESCE(date_end, date_start) ASC NULLS LAST, first_seen DESC"
    else:
        order = "first_seen DESC, COALESCE(date_start, '9999-12-31') ASC"

    query = f"""
        SELECT *, (first_seen = ?) as is_new
        FROM events {where}
        ORDER BY {order}
    """
    all_params = [latest_run] + params
    events = con.execute(query, all_params).fetchall()

    # Lista de sedes para el dropdown — filtrada por sección si hay una activa
    venue_conditions = [
        """(
            section = 'cine'
            OR date_end >= ?
            OR (date_end IS NULL AND date_start >= ?)
            OR (date_end IS NULL AND date_start IS NULL)
        )"""
    ]
    venue_params = [today, today]
    if section_filter != "all" and section_filter in SECTIONS:
        venue_conditions.append("section = ?")
        venue_params.append(section_filter)

    venue_where = "WHERE " + " AND ".join(venue_conditions)
    venues = [r[0] for r in con.execute(
        f"SELECT DISTINCT source FROM events {venue_where} ORDER BY source",
        venue_params
    ).fetchall()]

    con.close()

    return render_template(
        "index.html",
        events=events,
        sections=SECTIONS,
        section_labels=SECTION_LABELS,
        current_section=section_filter,
        current_sort=sort,
        current_venue=venue_filter,
        venues=venues,
        latest_run=latest_run,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5002)
