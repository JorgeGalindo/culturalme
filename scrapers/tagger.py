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
KIDS_PATH = Path(__file__).parent.parent / "data" / "kids_taste.md"
TAGGER_VERSION = "v3"
BATCH_SIZE = 40


def _kids_rules(kids_manifesto: str | None) -> str:
    if not kids_manifesto:
        return (
            '"kids_friendly": 0 siempre (no hay data/kids_taste.md cargado).'
        )
    return (
        'Decide "kids_friendly" según el siguiente manifiesto, que describe a DOS '
        'niños concretos (no un niño genérico). Aplica estrictamente la "Regla de '
        'decisión". Mapeo binario para "kids_friendly":\n'
        '  - "kids: sí" del manifiesto → 1\n'
        '  - "kids: depende" del manifiesto → 1 (lo dejamos visible para que el '
        'lector decida en la tarjeta)\n'
        '  - "kids: no" del manifiesto → 0\n\n'
        f"--- MANIFIESTO KIDS ---\n{kids_manifesto}\n--- FIN MANIFIESTO ---"
    )


def _selective_rules(taste: str | None) -> str:
    if not taste:
        return '"selective": 0 siempre (no hay manifiesto cargado).'
    return (
        '"selective": 1 si el evento encaja con el siguiente manifiesto de gusto; '
        '0 en cualquier otro caso. Aplica estrictamente la "Regla de decisión" del manifiesto.\n\n'
        f"--- MANIFIESTO ---\n{taste}\n--- FIN MANIFIESTO ---"
    )


def _build_prompt(events: list[dict], taste: str | None,
                   kids_manifesto: str | None) -> str:
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
{_kids_rules(kids_manifesto)}

SELECTIVE:
{_selective_rules(taste)}

Devuelve un JSON array con un objeto por evento, en el MISMO ORDEN, con la misma "i":
[{{"i": 0, "kids_friendly": 0|1, "selective": 0|1}}, ...]

Sólo el array, sin explicaciones.

Eventos:
{json.dumps(payload, ensure_ascii=False)}
"""


def _signature(taste: str | None, kids_manifesto: str | None) -> str:
    """Hash de versión + ambos manifiestos. Si cambia algo → re-tag."""
    payload = f"{TAGGER_VERSION}|{taste or ''}|{kids_manifesto or ''}"
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


def _tag_batch(events: list[dict], taste: str | None,
                kids_manifesto: str | None) -> list[dict]:
    """Etiqueta un batch. Devuelve lista alineada por índice; rellena con 0/0 si falta."""
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": _build_prompt(events, taste, kids_manifesto)}],
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


def _load(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def tag_events(con: sqlite3.Connection) -> None:
    """Re-etiqueta filas cuyo tags_hash no coincide con la firma actual."""
    taste = _load(TASTE_PATH)
    kids_manifesto = _load(KIDS_PATH)
    sig = _signature(taste, kids_manifesto)

    if not taste:
        log.info("Tagger: sin data/jorge_taste.md → selective siempre 0")
    if not kids_manifesto:
        log.info("Tagger: sin data/kids_taste.md → kids_friendly siempre 0")

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
            tags = _tag_batch(events, taste, kids_manifesto)
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
