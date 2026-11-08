"""
CulturalMe — la portada: qué merece la pena estos días.

Claude (con `claude -p`, sin API de pago) lee todo lo publicado que cae entre
hoy y el domingo de la semana que viene, el manifiesto de gusto de Jorge y el
de sus hijos, y elige:
  semana  6-8 planes, cada uno con una frase de por qué
  ninos   2-3 planes para ir con los niños
Escribe data/curation.json; generate.py lo pinta arriba de la página.

Si falla, se conserva la selección anterior: la página oculta sola lo que ya
haya terminado.

    python curate.py
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pipeline
from scrapers.llm import MODEL, claude_json

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "curation.json"
TASTE = ROOT / "data" / "jorge_taste.md"
KIDS = ROOT / "data" / "kids_taste.md"

WINDOW_DAYS = 9  # de viernes al domingo de la semana siguiente
MAX_SEMANA = 8
MAX_NINOS = 3
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

log = logging.getLogger("curate")

PICK = {
    "type": "object",
    "properties": {"id": {"type": "string"}, "por_que": {"type": "string"}},
    "required": ["id", "por_que"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {"semana": {"type": "array", "items": PICK}, "ninos": {"type": "array", "items": PICK}},
    "required": ["semana", "ninos"],
    "additionalProperties": False,
}

PROMPT = """\
Hoy es {dia} {today}. Eres el editor de la agenda cultural de Jorge en Madrid para los próximos días, del {today} al {end}.

Abajo tienes su manifiesto de gusto, el de sus dos hijos y la lista de lo que hay en cartel estos días
(id | tipo | título | sede | fechas | descripción | marcas). Las marcas "selecto" y "niños" son una
primera criba automática con esos manifiestos; puedes discrepar.

Elige:
- "semana": entre 6 y 8 planes que de verdad merezcan la pena estos días. Prioriza lo que encaja con su
  gusto y lo que solo se puede ver ahora (una charla de un día, un concierto, un estreno, una exposición
  que cierra pronto) frente a lo que seguirá ahí meses. Varía: no más de 3 del mismo tipo. Si no hay 6
  buenos, pon menos: mejor 4 buenos que 8 de relleno.
- "ninos": 2 o 3 planes para ir con sus hijos de 6 y 7 años, según su manifiesto. Que no repitan los de "semana".

Para cada uno, "por_que": una frase de 12 a 25 palabras con lo que tiene de especial en concreto: quién
es el artista, ponente o autor principal (nómbralo), qué se ve o se oye, por qué ahora. La sede y las fechas
ya salen al lado: repítelas solo si importan (una única fecha, último día). Escribe para Jorge sin hablar de
él ("encaja con tu gusto", "le interesa" sobran). Nada de adjetivos vacíos ("imprescindible", "fascinante",
"no te lo puedes perder") ni fórmulas de nota de prensa. Español de España, tono directo.
Hechos: puedes usar lo que sepas con seguridad de artistas y autores conocidos (quién es Arlo Parks, qué
pintaba Millares). No atribuyas a presentadores, ponentes o participantes oficios, premios o méritos que no
consten en su descripción, y no des por hecho que dos personas con el mismo nombre son la misma.
La página se lee durante toda la semana: nada de "hoy", "mañana" ni "este domingo"; di el día y el número
("el martes 10").
Usa solo ids de la lista, copiados tal cual.

--- MANIFIESTO DE JORGE ---
{taste}

--- MANIFIESTO DE LOS NIÑOS ---
{kids}

--- EN CARTEL ---
{lista}"""


def on_this_week(e, today: str, end: str) -> bool:
    """Si el evento se puede ver entre hoy y `end`."""
    if e["section"] == "cine":
        return True  # la cartelera es la de esta semana
    start, fin = e["date_start"], e["date_end"]
    if fin:
        return fin >= today and (start or today) <= end
    if start:
        return today <= start <= end
    return e["section"] in ("museo", "galeria")  # exposición sin fechas: abierta


def _fechas(e) -> str:
    a, b = e["date_start"], e["date_end"]
    if a and b and a != b:
        return f"{a} a {b}"
    return a or (f"hasta {b}" if b else "sin fecha")


def candidates(con, today: str, end: str) -> list:
    return [e for e in pipeline.published(con) if on_this_week(e, today, end)]


def build_prompt(events, today: date, end: date) -> str:
    lines = []
    for e in events:
        marcas = " ".join(m for m, on in (("selecto", e["selective"]), ("niños", e["kids_friendly"])) if on)
        desc = (e["description"] or "").replace("\n", " ")[:180]
        lines.append(" | ".join([e["id"], e["section"], e["title"], e["venue"] or e["source"] or "",
                                 _fechas(e), desc, marcas]))
    read = lambda p: p.read_text() if p.exists() else "(no hay)"
    return PROMPT.format(dia=DIAS[today.weekday()], today=today.isoformat(), end=end.isoformat(),
                         taste=read(TASTE), kids=read(KIDS), lista="\n".join(lines))


def validate(answer: dict, ids: set[str]) -> dict:
    """Quita ids inventados y repetidos y recorta a los máximos."""
    seen: set[str] = set()

    def clean(picks, limit):
        out = []
        for p in picks:
            pid, why = p.get("id", "").strip(), " ".join(p.get("por_que", "").split())
            if pid in ids and pid not in seen and why:
                seen.add(pid)
                out.append({"id": pid, "por_que": why})
        return out[:limit]

    semana = clean(answer.get("semana", []), MAX_SEMANA)
    ninos = clean(answer.get("ninos", []), MAX_NINOS)
    if not semana:
        raise ValueError("Claude no devolvió ningún plan válido para la semana")
    return {"semana": semana, "ninos": ninos}


def curate(con=None, today: date | None = None) -> dict:
    today = today or date.today()
    end = today + timedelta(days=WINDOW_DAYS)
    own = con is None
    con = con or pipeline.init_db()
    try:
        events = candidates(con, today.isoformat(), end.isoformat())
    finally:
        if own:
            con.close()
    if not events:
        raise ValueError("No hay nada publicado para estos días")
    answer = claude_json(build_prompt(events, today, end), SCHEMA, timeout=1200)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "desde": today.isoformat(),
        "hasta": end.isoformat(),
        "model": MODEL,
        **validate(answer, {e["id"] for e in events}),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    log.info("Portada: %d planes, %d con niños (de %d candidatos)",
             len(result["semana"]), len(result["ninos"]), len(events))
    return result


def load() -> dict | None:
    return json.loads(OUT.read_text()) if OUT.exists() else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    result = curate()
    for kind in ("semana", "ninos"):
        for p in result[kind]:
            print(f"{kind:6} {p['id']}  {p['por_que']}")
