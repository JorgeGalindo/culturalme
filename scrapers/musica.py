"""
Conciertos en salas de Madrid (añadido 2026-11-08).

Hasta agosto de 2026 los conciertos se buscaban por artista (4.000 nombres
contra Bandsintown, que da 403): casi nunca salía nada. Ahora se lee la
programación de unas pocas salas y el manifiesto decide qué es "selecto".
Las fundaciones con ciclos de música (Juan March, BBVA) entran por charlas.py.
"""

from scrapers.llm import Fuente, extract

FUENTES = [
    Fuente("Sala El Sol", "https://www.salaelsol.com/", "musica"),
    Fuente("Siroco", "https://siroco.es/", "musica"),
    Fuente("La Riviera", "https://salariviera.com/", "musica"),
    Fuente("Café La Palma", "https://www.cafelapalma.com/", "musica"),
]


def scrape() -> list[dict]:
    return [e for f in FUENTES for e in extract(f)]
