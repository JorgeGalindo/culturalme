"""
Galerías de arte en Madrid.

Las ferias (ARCO, Art Madrid, JustMAD, Estampa, Gallery Weekend) se retiraron:
no produjeron un solo evento en ninguna de sus ventanas de fecha.
"""

from scrapers.llm import Fuente, extract

# Revisadas 2026-08-20. Fuera las que no resuelven DNS (mpazarte, parraromero,
# albarranbourdais, fernandez-braso), las que dan 404/500 (Helga de Alvear,
# García Galería) y las SPAs que sirven menos de 600 caracteres de texto.
FUENTES = [
    Fuente("Travesía Cuatro", "https://www.travesiacuatro.com/", "galeria"),
    Fuente("NoguerasBlanchard", "https://www.noguerasblanchard.com/", "galeria"),
    Fuente("Max Estrella", "https://www.maxestrella.com/", "galeria"),
    Fuente("Galería Marlborough", "https://www.galeriamarlborough.com/", "galeria"),
    Fuente("José de la Mano", "https://josedelamano.com/", "galeria"),
    Fuente("F2 Galería", "https://www.f2galeria.com/", "galeria"),
    Fuente("Heinrich Ehrhardt", "https://heinrichehrhardt.com/", "galeria"),
    Fuente("Elba Benítez", "https://www.elbabenitez.com/", "galeria"),
    Fuente("Sabrina Amrani", "https://www.sabrinaamrani.com/", "galeria"),
]


def scrape() -> list[dict]:
    return [e for f in FUENTES for e in extract(f)]
