"""
Scraper de charlas y conferencias en Madrid.
Modo: LLM (Claude Haiku).
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

# Revisadas 2026-08-20. Ateneo, IE Foundation, Juan March y Casa Árabe salen:
# las tres primeras nunca produjeron nada, Casa Árabe dejó de hacerlo en julio.
FUENTES = [
    ("Fundación Ramón Areces", "https://www.fundacionareces.es/fundacionareces/es/actividades/"),
    ("Fundación Rafael del Pino", "https://frdelpino.es/eventos/todos-los-eventos/"),
    ("CBA", "https://www.circulobellasartes.com/agenda/"),
    ("Fundación Telefónica", "https://espacio.fundaciontelefonica.com/agenda/"),
]


def scrape() -> list[dict]:
    all_events = []
    for name, url in FUENTES:
        try:
            all_events.extend(extract_events(url, source_name=name, section="charla"))
        except Exception:
            log.exception("  ✗ Error scraping %s", name)
    return all_events
