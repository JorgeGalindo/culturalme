"""
Scraper de exposiciones en museos y espacios de Madrid.
Modo: LLM (Claude Haiku).

Sólo fuentes con producción comprobada. Las que devuelven cero de forma
sostenida se retiran: cada una cuesta una llamada al modelo y 3s de throttle.
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

# Cada entrada: (nombre para mostrar, URL de exposiciones[, corte de texto])
# Revisadas 2026-08-20.
FUENTES = [
    ("CentroCentro", "https://www.centrocentro.org/exposiciones"),
    ("Museo Reina Sofía", "https://www.museoreinasofia.es/exposiciones"),
    ("Real Academia de San Fernando", "https://www.realacademiabellasartessanfernando.com/actividades/exposiciones/"),
    ("Matadero Madrid", "https://www.mataderomadrid.org/programacion"),
    ("Museo Thyssen", "https://www.museothyssen.org/exposiciones"),
    ("Fundación Telefónica", "https://espacio.fundaciontelefonica.com/exposiciones/", "Pasadas"),
    ("CBA", "https://www.circulobellasartes.com/exposiciones/"),
    ("Sala Canal de Isabel II", "https://www.comunidad.madrid/centros/sala-canal-isabel-ii"),
    ("Museo Lázaro Galdiano", "https://www.museolazarogaldiano.es/actividades/exposiciones"),
    ("Fundación Mapfre", "https://www.fundacionmapfre.org/arte-y-cultura/exposiciones/sala-recoletos/"),
    ("Conde Duque", "https://www.condeduquemadrid.es/programacion"),
    ("Fundación Masaveu", "https://www.fundacioncristinamasaveu.com/"),
    ("Alcalá 31", "https://www.comunidad.madrid/centros/sala-alcala-31"),
    # Estas tres sirven cadenas de certificado incompletas; fetch_html reintenta
    # sin verificar. Estaban muertas desde abril por eso, no por falta de contenido.
    ("Museo de Artes Decorativas", "https://www.culturaydeporte.gob.es/mnartesdecorativas/exposiciones/actuales.html"),
    ("Museo Cerralbo", "https://www.culturaydeporte.gob.es/mcerralbo/actividades/programacion-en-curso.html"),
    ("Fundación ICO", "https://www.fundacionico.es/arte"),
]


def scrape() -> list[dict]:
    """Scrape todas las fuentes de museos. Devuelve lista de eventos."""
    all_events = []
    for entry in FUENTES:
        name, url = entry[0], entry[1]
        truncate = entry[2] if len(entry) > 2 else None
        try:
            all_events.extend(extract_events(url, source_name=name, section="museo",
                                             truncate_before=truncate))
        except Exception:
            log.exception("  ✗ Error scraping %s", name)
    return all_events
