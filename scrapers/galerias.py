"""
Scraper de galerías de arte en Madrid.
Modo: LLM (Claude Haiku).

Las ferias (ARCO, Art Madrid, JustMAD, Estampa, Gallery Weekend) se retiraron:
no produjeron un solo evento en ninguna de sus ventanas de fecha.
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

# Revisadas 2026-08-20. Fuera las que no resuelven DNS (mpazarte, parraromero,
# albarranbourdais, fernandez-braso), las que dan 404/500 (Helga de Alvear,
# García Galería) y las SPAs que sirven menos de 600 caracteres de texto.
GALERIAS = [
    ("Travesía Cuatro", "https://www.travesiacuatro.com/"),
    ("NoguerasBlanchard", "https://www.noguerasblanchard.com/"),
    ("Max Estrella", "https://www.maxestrella.com/"),
    ("Galería Marlborough", "https://www.galeriamarlborough.com/"),
    ("José de la Mano", "https://josedelamano.com/"),
    ("F2 Galería", "https://www.f2galeria.com/"),
    ("Heinrich Ehrhardt", "https://heinrichehrhardt.com/"),
    ("Elba Benítez", "https://www.elbabenitez.com/"),
    ("Sabrina Amrani", "https://www.sabrinaamrani.com/"),
]


def scrape() -> list[dict]:
    all_events = []
    for name, url in GALERIAS:
        try:
            all_events.extend(extract_events(url, source_name=name, section="galeria"))
        except Exception:
            log.exception("  ✗ Error scraping galería %s", name)
    return all_events
