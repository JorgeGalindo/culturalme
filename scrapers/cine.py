"""
Scraper de cartelera de cine en Madrid.
Modo: LLM (Claude Haiku). Se reemplaza completamente en cada pasada (no acumula).
"""

import logging

from scrapers.llm import call_llm_for_json, clean_html, fetch_html

log = logging.getLogger(__name__)

CINE_PROMPT = """\
Extrae todas las películas en cartelera de este texto de una web de cines.

Devuelve un JSON array. Cada objeto debe tener:
- "title": título de la película
- "director": nombre del director (o null)
- "tags": etiquetas como "ESTRENO", "EVENTO ESPECIAL", "PASE CON COLOQUIO", etc. (o null)

Solo JSON, sin explicaciones. Si no hay películas, devuelve [].

Texto:
{text}"""

CINES = [
    ("Cines Renoir", "https://www.cinesrenoir.com/",
     "Cines Renoir (Princesa / Retiro / Plaza de España / Floridablanca)"),
    ("Cines Embajadores", "https://cinesembajadores.es/madrid/", "Cines Embajadores"),
]


def _format_description(film: dict) -> str | None:
    director = film.get("director") or ""
    tags = film.get("tags") or ""
    parts = []
    if director:
        parts.append(f"Dir: {director}")
    if tags:
        parts.append(tags if isinstance(tags, str) else ", ".join(tags))
    return " — ".join(parts) if parts else None


def _scrape_cinema(name: str, url: str, venue: str) -> list[dict]:
    cleaned = clean_html(fetch_html(url))
    films = call_llm_for_json(CINE_PROMPT.format(text=cleaned), max_tokens=4096)

    events = [
        {
            "title": f["title"],
            "source": name,
            "section": "cine",
            "venue": venue,
            "description": _format_description(f),
            "url": url,
        }
        for f in films if f.get("title")
    ]
    log.info("  %s: %d películas", name, len(events))
    return events


def scrape() -> list[dict]:
    all_events = []
    for name, url, venue in CINES:
        try:
            all_events.extend(_scrape_cinema(name, url, venue))
        except Exception:
            log.exception("  ✗ Error scraping %s", name)
    return all_events
