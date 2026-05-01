"""
Etiquetado post-scrape de eventos.
- kids_friendly: criterio universal (apto para llevar críos, 5-10 años).
- selective: usa data/jorge_taste.md si existe; si no, queda en 0.

Sólo re-etiqueta filas cuyo tags_hash ya no coincide con el manifiesto/versión actual.
"""

import hashlib
import json
import logging
import re
import sqlite3
import time
from pathlib import Path

from scrapers.llm import MODEL, THROTTLE_SECONDS, _get_client

log = logging.getLogger(__name__)

TASTE_PATH = Path(__file__).parent.parent / "data" / "jorge_taste.md"
TAGGER_VERSION = "v2"
BATCH_SIZE = 40


KIDS_RULES = """\
Piensa en un niño de 7-12 años con curiosidad por el arte y la cultura.
"kids_friendly": 1 si el evento puede disfrutarlo sin aburrirse y sin contenido inadecuado.
Incluye:
  - Cualquier evento explícitamente "infantil", "familiar", "todos los públicos".
  - Cuentacuentos, talleres familiares, espectáculos infantiles.
  - Exposiciones de pintura figurativa, retrato, paisaje, escena urbana, ilustración
    (Hopper, Sorolla, Goya, Picasso, Velázquez, Antonio López, Hockney, Banksy y similares).
  - Exposiciones de fotografía documental, retrato, naturaleza, viajes (Cartier-Bresson,
    Salgado, National Geographic, etc.).
  - Exposiciones de escultura, arquitectura, diseño, moda, cómic, ilustración, cine
    (props, storyboards), juguetes históricos, civilizaciones antiguas, dinosaurios,
    arte oriental, máscaras, instrumentos.
  - Cine de autor con marca "todos los públicos" o claramente apto.
  - Conciertos diurnos al aire libre, música clásica para todos los públicos.
"kids_friendly": 0 si:
  - Arte contemporáneo conceptual, instalación de vídeo/sonido sin estímulo visual claro,
    performance, abstracción radical sin narrativa.
  - Contenido adulto (desnudo erótico explícito, violencia gráfica, drogas, política
    militante).
  - Charlas técnicas, mesas redondas, debates de policy/economía/filosofía.
  - Conciertos en sala de noche (rock, indie, rap, electrónica en club).
  - Teatro adulto, cine de autor "no recomendada" o con tema duro.
  - Cualquier evento que un niño de 10 años no podría seguir ni media hora.
Ante duda razonable a favor: marca 1. La duda fuerte: 0.
Este criterio NO depende del manifiesto."""


def _selective_rules(taste: str | None) -> str:
    if not taste:
        return '"selective": 0 siempre (no hay manifiesto cargado).'
    return (
        '"selective": 1 si el evento encaja con el siguiente manifiesto de gusto; '
        '0 en cualquier otro caso. Aplica estrictamente la "Regla de decisión" del manifiesto.\n\n'
        f"--- MANIFIESTO ---\n{taste}\n--- FIN MANIFIESTO ---"
    )


def _build_prompt(events: list[dict], taste: str | None) -> str:
    payload = [
        {
            "i": i,
            "title": e.get("title") or "",
            "section": e.get("section") or "",
            "venue": e.get("venue") or e.get("source") or "",
            "description": (e.get("description") or "")[:300],
        }
        for i, e in enumerate(events)
    ]
    return f"""\
Para cada evento del array, devuelve un objeto con dos flags binarios.

KIDS_FRIENDLY:
{KIDS_RULES}

SELECTIVE:
{_selective_rules(taste)}

Devuelve un JSON array con un objeto por evento, en el MISMO ORDEN, con la misma "i":
[{{"i": 0, "kids_friendly": 0|1, "selective": 0|1}}, ...]

Sólo el array, sin explicaciones.

Eventos:
{json.dumps(payload, ensure_ascii=False)}
"""


def _signature(taste: str | None) -> str:
    """Hash de manifiesto + versión del tagger. Si cambia → re-tag."""
    payload = f"{TAGGER_VERSION}|{taste or ''}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _parse_response(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.S)
        if not match:
            return []
        return json.loads(match.group())


def _tag_batch(events: list[dict], taste: str | None) -> list[dict]:
    """Etiqueta un batch. Devuelve lista alineada por índice; rellena con 0/0 si falta."""
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": _build_prompt(events, taste)}],
    )
    raw = _parse_response(response.content[0].text)
    by_i = {r.get("i"): r for r in raw if isinstance(r, dict)}

    result = []
    for i in range(len(events)):
        r = by_i.get(i, {})
        result.append({
            "kids_friendly": 1 if r.get("kids_friendly") else 0,
            "selective": 1 if r.get("selective") else 0,
        })
    time.sleep(THROTTLE_SECONDS)
    return result


def _load_taste() -> str | None:
    return TASTE_PATH.read_text() if TASTE_PATH.exists() else None


def tag_events(con: sqlite3.Connection) -> None:
    """Re-etiqueta filas cuyo tags_hash no coincide con la firma actual."""
    taste = _load_taste()
    sig = _signature(taste)

    if not taste:
        log.info("Tagger: sin manifiesto (data/jorge_taste.md) → selective siempre 0")

    rows = con.execute(
        "SELECT id, title, section, venue, source, description "
        "FROM events WHERE tags_hash IS NULL OR tags_hash != ?",
        (sig,),
    ).fetchall()

    if not rows:
        log.info("Tagger: nada que etiquetar (todo al día)")
        return

    log.info("Tagger: %d eventos para etiquetar (sig=%s)", len(rows), sig)

    total_kids = total_selective = 0
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        events = [
            {
                "title": r[1], "section": r[2], "venue": r[3],
                "source": r[4], "description": r[5],
            }
            for r in batch
        ]
        try:
            tags = _tag_batch(events, taste)
        except Exception:
            log.exception("  Tagger: batch %d-%d fallido", start, start + len(batch))
            continue

        for row, tag in zip(batch, tags):
            con.execute(
                "UPDATE events SET kids_friendly = ?, selective = ?, tags_hash = ? "
                "WHERE id = ?",
                (tag["kids_friendly"], tag["selective"], sig, row[0]),
            )
            total_kids += tag["kids_friendly"]
            total_selective += tag["selective"]
        con.commit()
        log.info("  Tagger: %d/%d", start + len(batch), len(rows))

    log.info("Tagger: → %d kids_friendly, %d selective de %d",
             total_kids, total_selective, len(rows))
