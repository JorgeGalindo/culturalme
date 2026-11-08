"""
Exposiciones en museos y centros de Madrid.

Sólo fuentes con producción comprobada. Las que devuelven cero de forma
sostenida se retiran: cada una cuesta una llamada al modelo.
Fuera por protección antibots (no se intenta saltar): Museo del Prado (403).
"""

from scrapers.llm import Fuente, extract

# Revisadas 2026-08-20; Casa Encendida, Museo ABC y BNE añadidas 2026-11-08.
FUENTES = [
    Fuente("CentroCentro", "https://www.centrocentro.org/exposiciones", "museo"),
    Fuente("Museo Reina Sofía", "https://www.museoreinasofia.es/exposiciones", "museo"),
    Fuente("Real Academia de San Fernando", "https://www.realacademiabellasartessanfernando.com/actividades/exposiciones/", "museo"),
    Fuente("Matadero Madrid", "https://www.mataderomadrid.org/programacion", "agenda"),
    Fuente("Museo Thyssen", "https://www.museothyssen.org/exposiciones", "museo"),
    Fuente("Fundación Telefónica", "https://espacio.fundaciontelefonica.com/exposiciones/", "museo", cut="Pasadas"),
    Fuente("Círculo de Bellas Artes", "https://www.circulobellasartes.com/exposiciones/", "museo"),
    Fuente("Sala Canal de Isabel II", "https://www.comunidad.madrid/centros/sala-canal-isabel-ii", "museo"),
    Fuente("Museo Lázaro Galdiano", "https://www.museolazarogaldiano.es/actividades/exposiciones", "museo"),
    Fuente("Fundación Mapfre", "https://www.fundacionmapfre.org/arte-y-cultura/exposiciones/sala-recoletos/", "museo"),
    Fuente("Conde Duque", "https://www.condeduquemadrid.es/programacion", "agenda"),
    Fuente("Fundación Masaveu", "https://www.fundacioncristinamasaveu.com/", "museo"),
    Fuente("Alcalá 31", "https://www.comunidad.madrid/centros/sala-alcala-31", "museo"),
    # Estas tres sirven cadenas de certificado incompletas; fetch_html reintenta
    # sin verificar. Estaban muertas desde abril por eso, no por falta de contenido.
    Fuente("Museo de Artes Decorativas", "https://www.culturaydeporte.gob.es/mnartesdecorativas/exposiciones/actuales.html", "museo"),
    Fuente("Museo Cerralbo", "https://www.culturaydeporte.gob.es/mcerralbo/actividades/programacion-en-curso.html", "museo"),
    Fuente("Fundación ICO", "https://www.fundacionico.es/arte", "museo"),
    Fuente("La Casa Encendida", "https://www.lacasaencendida.es/exposiciones", "museo"),
    Fuente("Museo ABC", "https://museo.abc.es/exposiciones", "museo"),
    Fuente("Biblioteca Nacional", "https://www.bne.es/es/agenda", "agenda"),
]


def scrape() -> list[dict]:
    return [e for f in FUENTES for e in extract(f)]
