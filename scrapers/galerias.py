"""
Scraper de galerías de arte en Madrid + ferias.
Modo: LLM (Claude Haiku) — 20 galerías heterogéneas.
"""

import logging
from datetime import date
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

GALERIAS = [
    ("Galería Elvira González", "https://www.elviragonzalez.com/"),
    ("Helga de Alvear", "https://www.helgadealvear.com/"),
    ("Juana de Aizpuru", "https://www.juanadeaizpuru.es/"),
    ("Travesía Cuatro", "https://www.travesiacuatro.com/"),
    ("Moisés Pérez de Albéniz", "https://www.mpazarte.com/"),
    ("Casa Sin Fin", "https://casasinfin.com/"),
    ("NoguerasBlanchard", "https://www.noguerasblanchard.com/"),
    ("Parra & Romero", "https://www.parraromero.com/"),
    ("F2 Galería", "https://www.f2galeria.com/"),
    ("Heinrich Ehrhardt", "https://heinrichehrhardt.com/"),
    ("Elba Benítez", "https://www.elbabenitez.com/"),
    ("Galería Cayón", "https://www.galeriacayon.com/"),
    ("Sabrina Amrani", "https://www.sabrinaamrani.com/"),
    ("Galería Marlborough", "https://www.galeriamarlborough.com/"),
    ("Max Estrella", "https://www.maxestrella.com/"),
    ("José de la Mano", "https://josedelamano.com/"),
    ("Albarrán Bourdais", "https://www.albarranbourdais.com/"),
    ("Galería Leandro Navarro", "https://www.leandronavarro.com/"),
    ("García Galería", "https://www.garciagaleria.com/"),
    ("Galería Fernández-Braso", "https://www.fernandez-braso.com/"),
]

FERIAS = [
    ("ARCO Madrid", 2, "https://www.ifema.es/arco-madrid"),
    ("Art Madrid", 2, "https://www.art-madrid.com/"),
    ("JustMAD", 2, "https://justmad.es/"),
    ("Estampa", 10, "https://www.estampa.org/"),
    ("Gallery Weekend Madrid", 9, "https://galleryweekendmadrid.com/"),
]


def scrape() -> list[dict]:
    all_events = []

    for name, url in GALERIAS:
        try:
            events = extract_events(url, source_name=name, section="galeria")
            all_events.extend(events)
        except Exception:
            log.exception("  ✗ Error scraping galería %s", name)

    # Ferias — solo comprobar si estamos cerca (±1 mes)
    current_month = date.today().month
    for name, month, url in FERIAS:
        if abs(current_month - month) <= 1 or abs(current_month - month) >= 11:
            try:
                events = extract_events(url, source_name=name, section="galeria")
                all_events.extend(events)
            except Exception:
                log.exception("  ✗ Error scraping feria %s", name)

    return all_events
