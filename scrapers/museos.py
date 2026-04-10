"""
Scraper de exposiciones en museos y espacios de Madrid.
Modo: LLM (Claude Haiku) — 20 webs heterogéneas.
"""

import logging
from scrapers.llm import extract_events

log = logging.getLogger(__name__)

# Cada entrada: (nombre para mostrar, URL de la página de exposiciones)
# URLs verificadas 2026-04-10
FUENTES = [
    ("Museo del Prado", "https://www.museodelprado.es/en/whats-on/exhibitions"),
    ("Museo Reina Sofía", "https://www.museoreinasofia.es/exposiciones"),
    ("Museo Thyssen", "https://www.museothyssen.org/exposiciones"),
    ("Matadero Madrid", "https://www.mataderomadrid.org/programacion"),
    # CaixaForum: Cloudflare bloquea todo acceso sin navegador real.
    # TODO: resolver con playwright.
    # ("CaixaForum Madrid", "https://caixaforum.org/es/madrid"),
    ("Fundación Telefónica", "https://espacio.fundaciontelefonica.com/exposiciones/", "Pasadas"),
    ("La Casa Encendida", "https://www.lacasaencendida.es/exposiciones"),
    ("Fundación Mapfre", "https://www.fundacionmapfre.org/arte-y-cultura/exposiciones/sala-recoletos/"),
    ("Sala Canal de Isabel II", "https://www.comunidad.madrid/centros/sala-canal-isabel-ii"),
    ("Conde Duque", "https://www.condeduquemadrid.es/programacion"),
    # Imprenta Municipal: madrid.es bloquea bots (403). Revisar periódicamente.
    # ("Imprenta Municipal", "https://www.madrid.es/..."),
    ("CBA", "https://www.circulobellasartes.com/exposiciones/"),
    ("Fundación ICO", "https://www.fundacionico.es/arte"),
    ("Real Academia de San Fernando", "https://www.realacademiabellasartessanfernando.com/actividades/exposiciones/"),
    ("CentroCentro", "https://www.centrocentro.org/exposiciones"),
    ("Alcalá 31", "https://www.comunidad.madrid/centros/sala-alcala-31"),
    ("Fundación Masaveu", "https://www.fundacioncristinamasaveu.com/"),
    ("Museo de Artes Decorativas", "https://www.culturaydeporte.gob.es/mnartesdecorativas/exposiciones/actuales.html"),
    ("Museo Cerralbo", "https://www.culturaydeporte.gob.es/mcerralbo/actividades/programacion-en-curso.html"),
    ("Fundación Juan March", "https://www.march.es/es/madrid/exposiciones"),
    # Lázaro Galdiano: web JS-rendered, httpx no puede extraer contenido.
    # TODO: probar con playwright si se añade, o buscar feed/API.
    # ("Museo Lázaro Galdiano", "https://www.museolazarogaldiano.es/actividades"),
]


# Títulos a excluir siempre (instalaciones permanentes, etc.)
EXCLUDE_TITLES = {"Julia"}


def scrape() -> list[dict]:
    """Scrape todas las fuentes de museos. Devuelve lista de eventos."""
    all_events = []
    for entry in FUENTES:
        name, url = entry[0], entry[1]
        truncate = entry[2] if len(entry) > 2 else None
        try:
            events = extract_events(url, source_name=name, section="museo",
                                    truncate_before=truncate)
            events = [e for e in events if e["title"] not in EXCLUDE_TITLES]
            all_events.extend(events)
        except Exception:
            log.exception("  ✗ Error scraping %s", name)
    return all_events
