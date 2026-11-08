"""
Cartelera de cine en Madrid.

Lo que sale de cartel deja de publicarse en cuanto su cine lo retira (regla de
publicación por fuente en pipeline.py); las etiquetas de lo que sigue se conservan.
"""

from scrapers.llm import Fuente, extract

# Embajadores sirve un certificado con cadena incompleta; fetch_html reintenta
# sin verificar. Cineteca y Verdi añadidas 2026-11-08. Filmoteca (Cine Doré):
# su web no publica la programación en HTML legible.
FUENTES = [
    Fuente("Cines Renoir", "https://www.cinesrenoir.com/", "cine",
           venue="Cines Renoir (Princesa / Retiro / Plaza de España / Floridablanca)"),
    Fuente("Cines Embajadores", "https://cinesembajadores.es/madrid/", "cine"),
    Fuente("Cineteca Madrid", "https://www.cinetecamadrid.com/programacion", "cine"),
    Fuente("Cines Verdi", "https://www.cines-verdi.com/madrid/", "cine", render=True),
]


def scrape() -> list[dict]:
    return [e for f in FUENTES for e in extract(f)]
