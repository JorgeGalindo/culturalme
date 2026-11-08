"""
CulturalMe — pasada semanal: lee todas las fuentes, deduplica y escribe en SQLite.

Corre en el Mac mini (semanal.py, launchd los viernes). Cada fuente es una
llamada a `claude -p`; van de cuatro en cuatro en paralelo.

Regla de publicación, por fuente: un evento se publica si apareció en la
última pasada BUENA de su página. Que una web deje de listarlo es la señal de
que se acabó; que una web falle una semana no lo es, y sus eventos siguen.
"""

import hashlib
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "culturalme.db"

# Filas que llevan este tiempo sin verse en su fuente se borran.
RETENTION_DAYS = 60
WORKERS = 4

# Eventos que nunca deben entrar (instalaciones permanentes, etc.)
# Cada tupla: (substring en título, substring en source). Case-insensitive.
GLOBAL_EXCLUDE = [
    ("julia", "masaveu"),
    ("plensa", "masaveu"),
]

# Fuentes renombradas: se migran sus filas para no perder fechas de alta ni etiquetas.
RENAMED_SOURCES = {"CBA": "Círculo de Bellas Artes"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("pipeline")


def init_db(path=None):
    """Crea las tablas si no existen y migra columnas nuevas."""
    con = sqlite3.connect(path or DB_PATH)
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
            tags_hash TEXT,
            source_url TEXT
        )
    """)
    existing = {row[1] for row in con.execute("PRAGMA table_info(events)")}
    for col, ddl in [
        ("kids_friendly", "ALTER TABLE events ADD COLUMN kids_friendly INTEGER"),
        ("selective", "ALTER TABLE events ADD COLUMN selective INTEGER"),
        ("tags_hash", "ALTER TABLE events ADD COLUMN tags_hash TEXT"),
        ("source_url", "ALTER TABLE events ADD COLUMN source_url TEXT"),
    ]:
        if col not in existing:
            con.execute(ddl)
    # Una fila por página leída: cuándo dio su última lectura buena y cuántos eventos.
    con.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            url TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            last_ok DATE,
            last_count INTEGER,
            last_try DATE,
            last_error TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_last_seen ON events(last_seen)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_section_dates ON events(section, date_start, date_end)")
    _rename_sources(con)
    con.commit()
    return con


def _rename_sources(con: sqlite3.Connection) -> None:
    for old, new in RENAMED_SOURCES.items():
        rows = con.execute("SELECT id, title, venue FROM events WHERE source = ?", (old,)).fetchall()
        for eid, title, venue in rows:
            new_id = event_id(new, title, venue)
            if con.execute("SELECT 1 FROM events WHERE id = ?", (new_id,)).fetchone():
                con.execute("DELETE FROM events WHERE id = ?", (eid,))
            else:
                con.execute("UPDATE events SET id = ?, source = ? WHERE id = ?", (new_id, new, eid))


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
                 replace: bool = False, source_url: str | None = None):
    """Inserta o actualiza los eventos de una sección.

    replace=True retira lo que ya no aparece (de esa fuente si se da
    source_url; si no, de toda la sección), conservando first_seen y etiquetas
    de lo que sigue. La escritura es atómica: un error no deja nada a medias.
    En un evento ya conocido se refrescan fechas, descripción y URL: la
    fuente es la autoridad, y un date_end que se alarga es información nueva.
    """
    today = date.today().isoformat()
    events = [e for e in events if not _is_excluded(e)]

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

    with con:
        if replace:
            if source_url:
                existing = con.execute("SELECT id FROM events WHERE section = ? AND source_url = ?",
                                       (section, source_url))
            else:
                existing = con.execute("SELECT id FROM events WHERE section = ?", (section,))
            removed = [(eid,) for (eid,) in existing if eid not in fundidos]
            con.executemany("DELETE FROM events WHERE id = ?", removed)

        for eid, e in fundidos.items():
            row = (e["section"], e["title"], e.get("venue"), e.get("date_start"),
                   e.get("date_end"), e.get("description"), e.get("url"), e["source"],
                   e.get("source_url") or source_url)
            previous = con.execute(
                "SELECT title, section, venue, source, description FROM events WHERE id = ?", (eid,)
            ).fetchone()
            if previous:
                tagged_content = (e["title"], e["section"], e.get("venue"), e["source"], e.get("description"))
                if previous != tagged_content:
                    con.execute(
                        "UPDATE events SET kids_friendly=NULL, selective=NULL, tags_hash=NULL WHERE id=?", (eid,)
                    )
                con.execute(
                    """UPDATE events SET section=?, title=?, venue=?, date_start=?,
                       date_end=?, description=?, url=?, source=?, source_url=?, last_seen=?
                       WHERE id=?""",
                    (*row, today, eid),
                )
            else:
                con.execute(
                    """INSERT INTO events
                       (section, title, venue, date_start, date_end, description,
                        url, source, source_url, first_seen, last_seen, id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*row, today, today, eid),
                )


def store_source(con: sqlite3.Connection, fuente, events: list[dict]) -> None:
    """Guarda lo leído de una fuente y apunta su lectura buena."""
    today = date.today().isoformat()
    by_section: dict[str, list[dict]] = {}
    for e in events:
        by_section.setdefault(e["section"], []).append(e)
    for section, evs in by_section.items():
        store_events(con, section, evs, replace=(section == "cine"), source_url=fuente.url)
    with con:
        con.execute(
            """INSERT INTO sources (url, name, last_ok, last_count, last_try, last_error)
               VALUES (?, ?, ?, ?, ?, NULL)
               ON CONFLICT(url) DO UPDATE SET name=excluded.name, last_ok=excluded.last_ok,
               last_count=excluded.last_count, last_try=excluded.last_try, last_error=NULL""",
            (fuente.url, fuente.name, today, len(events), today),
        )


def mark_failed(con: sqlite3.Connection, fuente, error: str) -> None:
    today = date.today().isoformat()
    with con:
        con.execute(
            """INSERT INTO sources (url, name, last_try, last_error) VALUES (?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET name=excluded.name, last_try=excluded.last_try,
               last_error=excluded.last_error""",
            (fuente.url, fuente.name, today, error[:500]),
        )


def previous_count(con: sqlite3.Connection, url: str) -> int:
    row = con.execute("SELECT last_count FROM sources WHERE url = ?", (url,)).fetchone()
    return (row[0] or 0) if row else 0


PUBLISHED_SQL = """
    SELECT e.* FROM events e LEFT JOIN sources s ON s.url = e.source_url
    WHERE (s.last_ok IS NOT NULL AND e.last_seen = s.last_ok)
       OR (e.source_url IS NULL AND e.last_seen = (SELECT MAX(last_seen) FROM events))
"""


def published(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Lo que vio la última lectura buena de cada fuente (las filas antiguas, sin
    source_url, siguen la regla vieja: la última pasada global)."""
    cur = con.cursor()
    cur.row_factory = sqlite3.Row
    return cur.execute(PUBLISHED_SQL + " ORDER BY e.title").fetchall()


def purge_stale(con: sqlite3.Connection):
    """Borra lo que lleva RETENTION_DAYS sin aparecer en su fuente."""
    cutoff = (date.today() - timedelta(days=RETENTION_DAYS)).isoformat()
    n = con.execute("DELETE FROM events WHERE last_seen < ?", (cutoff,)).rowcount
    con.commit()
    if n:
        log.info("Purga: %d eventos sin verse desde antes de %s", n, cutoff)


def all_sources():
    from scrapers import museos, galerias, charlas, cine, teatro, musica
    return [f for mod in (museos, galerias, charlas, teatro, cine, musica) for f in mod.FUENTES]


def run(con: sqlite3.Connection | None = None) -> dict:
    """Una pasada completa. Devuelve el resumen; lanza si no funcionó ninguna fuente."""
    from scrapers.llm import extract

    log.info("=== CulturalMe pipeline — %s ===", date.today().isoformat())
    own = con is None
    con = con or init_db()
    fuentes = all_sources()

    def leer(f):
        try:
            return f, extract(f), None
        except Exception as exc:  # una fuente rota no para la pasada
            log.warning("  ✗ %s: %s: %s", f.name, type(exc).__name__, str(exc)[:200])
            return f, None, f"{type(exc).__name__}: {exc}"

    ok, failed = [], []
    with ThreadPoolExecutor(WORKERS) as pool:
        for f, events, error in pool.map(leer, fuentes):
            if events is not None and not events and previous_count(con, f.url):
                error = f"vacía (la semana anterior dio {previous_count(con, f.url)})"
                log.warning("  ? %s: %s; se conservan sus eventos", f.name, error)
            if error:
                mark_failed(con, f, error)
                failed.append((f.name, error))
                continue
            store_source(con, f, events)
            ok.append((f.name, len(events)))

    if not ok:
        if own:
            con.close()
        raise RuntimeError(f"Ninguna fuente funcionó. Primera: {failed[0][1][:300] if failed else '-'}")

    purge_stale(con)

    log.info("Tagging eventos (kids_friendly + selective)...")
    try:
        from scrapers.tagger import tag_events
        tag_events(con)
    except Exception:
        log.exception("  ✗ Error en tagger — eventos quedan sin etiquetar")

    total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    visibles = len(published(con))
    log.info("=== Done. %d fuentes bien, %d fallan; %d eventos en DB, %d publicados ===",
             len(ok), len(failed), total, visibles)
    if own:
        con.close()
    return {"ok": ok, "failed": failed, "published": visibles}


if __name__ == "__main__":
    run()
