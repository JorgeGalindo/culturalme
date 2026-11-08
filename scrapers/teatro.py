"""
Teatro y danza en Madrid.

Fuera por protección antibots (Imperva; no se intenta saltar): Centro Dramático
Nacional, Compañía Nacional de Teatro Clásico y Teatro de la Zarzuela.
"""

from scrapers.llm import Fuente, extract

# Revisadas 2026-08-20. Naves del Español ya no está aquí: apuntaba a la misma
# URL que "Matadero Madrid" y duplicaba cada evento con otro nombre.
# Fernán Gómez añadido 2026-11-08 (programa también música y cine: es agenda).
FUENTES = [
    Fuente("Teatros del Canal", "https://www.teatroscanal.com/cartelera-madrid/", "teatro"),
    Fuente("Teatro Calderón", "https://teatrocalderonmadrid.com/es/cartelera", "teatro"),
    Fuente("Nave 73", "https://nave73.es/programacion/", "teatro"),
    Fuente("Teatro del Barrio", "https://teatrodelbarrio.com/", "teatro"),
    Fuente("Teatro Bellas Artes", "https://www.teatrobellasartes.es/", "teatro"),
    Fuente("Teatro de la Abadía", "https://www.teatroabadia.com/", "teatro"),
    Fuente("Teatro Español", "https://www.teatroespanol.es/", "teatro"),
    Fuente("Sala Cuarta Pared", "https://www.cuartapared.es/", "teatro"),
    Fuente("Teatro Fernán Gómez", "https://www.teatrofernangomez.es/programacion", "agenda"),
]


def scrape() -> list[dict]:
    return [e for f in FUENTES for e in extract(f)]
