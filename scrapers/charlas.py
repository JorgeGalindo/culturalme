"""
Charlas, conferencias y agendas mixtas (fundaciones que programan de todo).

Las fuentes "agenda" traen exposiciones, charlas, conciertos o cine en la
misma página; el modelo clasifica cada actividad y cae en su pestaña.
"""

from scrapers.llm import Fuente, extract

# Revisadas 2026-08-20. Ateneo, IE Foundation y Casa Árabe salen: nunca
# produjeron nada o dejaron de hacerlo. Juan March vuelve el 2026-11-08 con su
# página de actividades (la de 2026-08 era otra URL). Real Instituto Elcano y
# Residencia de Estudiantes probadas el 2026-11-08: casi sin texto.
FUENTES = [
    Fuente("Fundación Ramón Areces", "https://www.fundacionareces.es/fundacionareces/es/actividades/", "charla"),
    Fuente("Fundación Rafael del Pino", "https://frdelpino.es/eventos/todos-los-eventos/", "charla"),
    Fuente("Círculo de Bellas Artes", "https://www.circulobellasartes.com/agenda/", "agenda"),
    Fuente("Fundación Telefónica", "https://espacio.fundaciontelefonica.com/agenda/", "charla"),
    Fuente("Fundación Juan March", "https://www.march.es/es/madrid/actividades", "agenda"),
    Fuente("Casa de América", "https://www.casamerica.es/agenda", "agenda"),
    Fuente("Fundación BBVA", "https://www.fbbva.es/agenda/", "agenda", render=True),
    Fuente("CaixaForum Madrid", "https://caixaforum.org/es/madrid/actividades", "agenda"),
]


def scrape() -> list[dict]:
    return [e for f in FUENTES for e in extract(f)]
