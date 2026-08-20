"""
Scraper de teatro en Madrid.
Modo: LLM (Claude Haiku).
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

# Revisadas 2026-08-20. Naves del Español ya no está aquí: apuntaba a la misma
# URL que "Matadero Madrid" en museos.py y duplicaba cada evento con otro nombre.
FUENTES = [
    ("Teatros del Canal", "https://www.teatroscanal.com/cartelera-madrid/"),
    ("Teatro Calderón", "https://teatrocalderonmadrid.com/es/cartelera"),
    ("Nave 73", "https://nave73.es/programacion/"),
    ("Teatro del Barrio", "https://teatrodelbarrio.com/"),
    ("Teatro Bellas Artes", "https://www.teatrobellasartes.es/"),
    ("Teatro de la Abadía", "https://www.teatroabadia.com/"),
    ("Teatro Español", "https://www.teatroespanol.es/"),
    ("Sala Cuarta Pared", "https://www.cuartapared.es/"),
]


def scrape() -> list[dict]:
    all_events = []
    for name, url in FUENTES:
        try:
            all_events.extend(extract_events(url, source_name=name, section="teatro"))
        except Exception:
            log.exception("  ✗ Error scraping %s", name)
    return all_events
