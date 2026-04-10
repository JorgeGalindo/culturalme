"""
CulturalMe — pipeline de actualización semanal.
Ejecuta todos los scrapers, deduplica, y escribe en SQLite.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "culturalme.db"
ARTISTS_PATH = Path(__file__).parent / "data" / "artists.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("pipeline")


def init_db():
    """Crea la tabla events si no existe."""
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            section TEXT NOT NULL,
            title TEXT NOT NULL,
            venue TEXT,
            date_start DATE,
            date_end DATE,
            description TEXT,
            url TEXT,
            source TEXT,
            image_url TEXT,
            first_seen DATE NOT NULL,
            last_seen DATE NOT NULL,
            artist_match TEXT
        )
    """)
    con.commit()
    return con


def event_id(source: str, title: str, venue: str | None, date_start: str | None) -> str:
    """Genera un ID determinista para un evento."""
    raw = f"{source}|{title}|{venue or ''}|{date_start or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def upsert_events(con: sqlite3.Connection, events: list[dict]):
    """Inserta eventos nuevos o actualiza last_seen de los existentes."""
    today = date.today().isoformat()
    for e in events:
        eid = event_id(e["source"], e["title"], e.get("venue"), e.get("date_start"))
        existing = con.execute("SELECT id FROM events WHERE id = ?", (eid,)).fetchone()
        if existing:
            con.execute("UPDATE events SET last_seen = ? WHERE id = ?", (today, eid))
        else:
            con.execute(
                """INSERT INTO events
                   (id, section, title, venue, date_start, date_end, description,
                    url, source, image_url, first_seen, last_seen, artist_match)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    eid,
                    e["section"],
                    e["title"],
                    e.get("venue"),
                    e.get("date_start"),
                    e.get("date_end"),
                    e.get("description"),
                    e.get("url"),
                    e["source"],
                    e.get("image_url"),
                    today,
                    today,
                    e.get("artist_match"),
                ),
            )
    con.commit()


def replace_section(con: sqlite3.Connection, section: str, events: list[dict]):
    """Reemplaza todos los eventos de una sección (para cine, que no acumula)."""
    today = date.today().isoformat()
    con.execute("DELETE FROM events WHERE section = ?", (section,))
    for e in events:
        eid = event_id(e["source"], e["title"], e.get("venue"), e.get("date_start"))
        con.execute(
            """INSERT INTO events
               (id, section, title, venue, date_start, date_end, description,
                url, source, image_url, first_seen, last_seen, artist_match)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                eid,
                e["section"],
                e["title"],
                e.get("venue"),
                e.get("date_start"),
                e.get("date_end"),
                e.get("description"),
                e.get("url"),
                e["source"],
                e.get("image_url"),
                today,
                today,
                e.get("artist_match"),
            ),
        )
    con.commit()


def load_artists() -> set[str]:
    """Carga la lista de artistas normalizados para filtro de conciertos."""
    if not ARTISTS_PATH.exists():
        log.warning("No se encontró artists.json — conciertos no se filtrarán")
        return set()
    with open(ARTISTS_PATH) as f:
        artists = json.load(f)
    return {a.lower().strip() for a in artists}


def run():
    log.info("=== CulturalMe pipeline — %s ===", date.today().isoformat())
    con = init_db()
    artists = load_artists()

    from scrapers import museos, conciertos, galerias, charlas, cine, teatro

    scrapers = [
        ("museos", museos.scrape, False),
        ("conciertos", lambda: conciertos.scrape(artists), False),
        ("galerias", galerias.scrape, False),
        ("charlas", charlas.scrape, False),
        ("cine", cine.scrape, True),  # True = replace, no accumulate
        ("teatro", teatro.scrape, False),
    ]

    for name, scrape_fn, replace in scrapers:
        try:
            log.info("Scraping %s...", name)
            events = scrape_fn()
            log.info("  → %d eventos", len(events))
            if replace:
                replace_section(con, name, events)
            else:
                upsert_events(con, events)
        except Exception:
            log.exception("  ✗ Error en %s — skipping", name)

    total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    log.info("=== Done. %d eventos en DB ===", total)
    con.close()


if __name__ == "__main__":
    run()
