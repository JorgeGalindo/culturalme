"""
Scraper de teatro en Madrid.
Modo: LLM (Claude Haiku) — 4 teatros.

Nota: el CDN (Centro Dramático Nacional) tiene el dominio cdn.mcu.es caído.
El María Guerrero es sede del CDN, así que comparten programación.
Usamos las webs que funcionan.
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

FUENTES = [
    # CDN / María Guerrero: dominio cdn.mcu.es no resuelve.
    # TODO: buscar nueva URL del CDN cuando resuelvan su dominio.
    ("Teatros del Canal", "https://www.teatroscanal.com/"),
    ("Teatro Español", "https://www.teatroespanol.es/"),
    ("Teatro de la Abadía", "https://www.teatroabadia.com/"),
]


def scrape() -> list[dict]:
    all_events = []
    for name, url in FUENTES:
        try:
            events = extract_events(url, source_name=name, section="teatro")
            all_events.extend(events)
        except Exception:
            log.exception("  ✗ Error scraping %s", name)
    return all_events
