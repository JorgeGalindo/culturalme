"""
Scraper de teatro en Madrid.
Modo: LLM (Claude Haiku).
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

FUENTES = [
    # CDN / María Guerrero: dominio cdn.mcu.es no resuelve.
    # CNTC (Teatro de la Comedia): dominio caído también.
    # TODO: buscar nuevas URLs cuando resuelvan sus dominios.
    ("Teatros del Canal", "https://www.teatroscanal.com/"),
    ("Teatro Español", "https://www.teatroespanol.es/"),
    ("Teatro de la Abadía", "https://www.teatroabadia.com/"),
    ("Naves del Español", "https://www.mataderomadrid.org/programacion"),
    ("Teatro del Barrio", "https://teatrodelbarrio.com/"),
    ("Nave 73", "https://nave73.es/programacion/"),
    ("Sala Cuarta Pared", "https://www.cuartapared.es/"),
    ("Sala Triángulo", "https://www.salatriangulo.com/"),
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
