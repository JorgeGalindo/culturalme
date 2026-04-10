"""
Scraper de charlas y conferencias en Madrid.
Modo: LLM (Claude Haiku) — 5 fuentes.
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

FUENTES = [
    ("Fundación Rafael del Pino", "https://frdelpino.es/"),
    ("Fundación Ramón Areces", "https://www.fundacionareces.es/fundacionareces/es/actividades/"),
    ("Fundación Juan March", "https://www.march.es/es/madrid/actividades"),
    ("Ateneo de Madrid", "https://www.ateneodemadrid.com/actividades"),
    ("CBA", "https://www.circulobellasartes.com/agenda/"),
    ("Casa Árabe", "https://casaarabe.es/eventos"),
    ("IE Foundation", "https://www.ie.edu/es/fundacion-ie/"),
    ("Fundación Telefónica", "https://espacio.fundaciontelefonica.com/agenda/"),
]


def scrape() -> list[dict]:
    all_events = []
    for name, url in FUENTES:
        try:
            events = extract_events(url, source_name=name, section="charla")
            all_events.extend(events)
        except Exception:
            log.exception("  ✗ Error scraping %s", name)
    return all_events
