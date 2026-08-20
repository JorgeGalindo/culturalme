"""
CulturalMe — pipeline de actualización semanal.
Ejecuta todos los scrapers, deduplica, y escribe en SQLite.
"""

import hashlib
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "culturalme.db"

# Filas que llevan este tiempo sin verse en su fuente se borran.
RETENTION_DAYS = 60

# Eventos que nunca deben entrar (instalaciones permanentes, etc.)
# Cada tupla: (substring en título, substring en source). Case-insensitive.
GLOBAL_EXCLUDE = [
    ("julia", "masaveu"),
    ("plensa", "masaveu"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("pipeline")


def init_db():
    """Crea la tabla events si no existe y migra columnas nuevas."""
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
            first_seen DATE NOT NULL,
            last_seen DATE NOT NULL,
            kids_friendly INTEGER,
            selective INTEGER,
            tags_hash TEXT
        )
    """)
    existing = {row[1] for row in con.execute("PRAGMA table_info(events)")}
    for col, ddl in [
        ("kids_friendly", "ALTER TABLE events ADD COLUMN kids_friendly INTEGER"),
        ("selective", "ALTER TABLE events ADD COLUMN selective INTEGER"),
        ("tags_hash", "ALTER TABLE events ADD COLUMN tags_hash TEXT"),
    ]:
        if col not in existing:
            con.execute(ddl)
    # generate.py filtra por last_seen y ordena por fecha en cada pasada.
    con.execute("CREATE INDEX IF NOT EXISTS idx_last_seen ON events(last_seen)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_section_dates ON events(section, date_start, date_end)")
    con.commit()
    return con


def event_id(source: str, title: str, venue: str | None) -> str:
    """ID determinista de un evento.

    Sin fecha a propósito: la fecha es el dato que el LLM extrae peor, y
    meterla en la clave convertía cada relectura errónea en una fila nueva
    (el mismo montaje llegó a estar cuatro veces con cuatro años distintos).
    Título + sede identifican el evento; las fechas se actualizan encima.
    """
    raw = f"{source}|{title.strip().lower()}|{(venue or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_excluded(e: dict) -> bool:
    """Comprueba si un evento está en la lista de exclusión global (substring match)."""
    t = (e.get("title") or "").lower()
    s = (e.get("source") or "").lower()
    return any(ts in t and ss in s for ts, ss in GLOBAL_EXCLUDE)


def store_events(con: sqlite3.Connection, section: str, events: list[dict],
                  replace: bool = False):
    """Inserta o actualiza los eventos de una sección.

    replace=True vacía la sección primero (cine: la cartelera no acumula).
    En un evento ya conocido se refrescan fechas, descripción y URL: la
    fuente es la autoridad, y un date_end que se alarga es información nueva.
    """
    today = date.today().isoformat()
    events = [e for e in events if not _is_excluded(e)]

    if replace:
        con.execute("DELETE FROM events WHERE section = ?", (section,))

    # Una misma página suele listar el mismo evento varias veces, y no siempre
    # con los mismos datos: una lectura trae las fechas y otra no. Se funden
    # quedándose con el primer valor no vacío de cada campo.
    CAMPOS = ("venue", "date_start", "date_end", "description", "url")
    fundidos: dict[str, dict] = {}
    for e in events:
        eid = event_id(e["source"], e["title"], e.get("venue"))
        if eid in fundidos:
            base = fundidos[eid]
            for c in CAMPOS:
                if not base.get(c) and e.get(c):
                    base[c] = e[c]
        else:
            fundidos[eid] = dict(e)

    for eid, e in fundidos.items():
        row = (e["section"], e["title"], e.get("venue"), e.get("date_start"),
               e.get("date_end"), e.get("description"), e.get("url"), e["source"])
        if con.execute("SELECT 1 FROM events WHERE id = ?", (eid,)).fetchone():
            con.execute(
                """UPDATE events SET section=?, title=?, venue=?, date_start=?,
                   date_end=?, description=?, url=?, source=?, last_seen=?
                   WHERE id=?""",
                (*row, today, eid),
            )
        else:
            con.execute(
                """INSERT INTO events
                   (section, title, venue, date_start, date_end, description,
                    url, source, first_seen, last_seen, id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*row, today, today, eid),
            )
    con.commit()


def purge_stale(con: sqlite3.Connection):
    """Borra lo que lleva RETENTION_DAYS sin aparecer en su fuente."""
    cutoff = (date.today() - timedelta(days=RETENTION_DAYS)).isoformat()
    n = con.execute("DELETE FROM events WHERE last_seen < ?", (cutoff,)).rowcount
    con.commit()
    if n:
        log.info("Purga: %d eventos sin verse desde antes de %s", n, cutoff)


def run():
    log.info("=== CulturalMe pipeline — %s ===", date.today().isoformat())
    con = init_db()

    from scrapers import museos, galerias, charlas, cine, teatro

    scrapers = [
        ("museo", museos.scrape, False),
        ("galeria", galerias.scrape, False),
        ("charla", charlas.scrape, False),
        ("cine", cine.scrape, True),  # True = replace, la cartelera no acumula
        ("teatro", teatro.scrape, False),
    ]

    for section, scrape_fn, replace in scrapers:
        try:
            log.info("Scraping %s...", section)
            events = scrape_fn()
            log.info("  → %d eventos", len(events))
            store_events(con, section, events, replace=replace)
        except Exception:
            log.exception("  ✗ Error en %s — skipping", section)

    purge_stale(con)

    log.info("Tagging eventos (kids_friendly + selective)...")
    try:
        from scrapers.tagger import tag_events
        tag_events(con)
    except Exception:
        log.exception("  ✗ Error en tagger — eventos quedan sin etiquetar")

    total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    fresh = con.execute("SELECT COUNT(*) FROM events WHERE last_seen = ?",
                        (date.today().isoformat(),)).fetchone()[0]
    log.info("=== Done. %d eventos en DB, %d vistos hoy ===", total, fresh)
    con.close()


if __name__ == "__main__":
    run()
