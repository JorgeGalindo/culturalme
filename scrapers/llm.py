"""
Extracción de eventos con Claude, sin API de pago.

Cada llamada es `claude -p` en el Mac mini con la suscripción de Jorge (no
hace falta ANTHROPIC_API_KEY). La salida se valida con --json-schema, así que
llega como objeto y no hay que pescar JSON en texto libre.

Módulo compartido por todos los scrapers: descarga (httpx o Chrome headless
para las webs que pintan con JavaScript), limpieza a texto con los enlaces
marcados, prompts por tipo de fuente y saneado de fechas y URLs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urldefrag, urljoin

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = os.environ.get("CLAUDE_BIN", str(Path.home() / ".local/bin/claude"))
MODEL = os.environ.get("CULTURALME_MODEL", "claude-sonnet-5-5")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MAX_TEXT_CHARS = 60_000

# Ventana de fechas aceptables. Fuera de ella la fecha la ha puesto el modelo,
# no la web. Generosa hacia atrás a propósito: una exposición del Reina Sofía
# puede llevar año y medio abierta, y nular su inicio destruye un dato bueno.
# De filtrar lo que ya pasó se encarga la vista, no el extractor.
PAST_TOLERANCE_DAYS = 730
FUTURE_HORIZON_DAYS = 548  # ~18 meses: cabe una temporada teatral completa

# Una fuente "agenda" mezcla tipos; el modelo clasifica y esto decide la sección.
TIPO_A_SECCION = {"exposicion": "museo", "teatro": "teatro", "charla": "charla",
                  "cine": "cine", "musica": "musica"}


@dataclass(frozen=True)
class Fuente:
    """Una página que se lee cada semana.

    kind: museo, galeria, charla, teatro, cine, musica o agenda (varios tipos).
    render: abrirla con Chrome headless porque pinta los eventos con JavaScript.
    cut: corta el texto antes de la segunda aparición de esta cadena (la
         primera suele ser un menú); útil cuando la web lista lo pasado detrás.
    venue: sede que se muestra si no es el nombre de la fuente.
    """
    name: str
    url: str
    kind: str
    render: bool = False
    cut: str | None = None
    venue: str | None = None


# ---------------------------------------------------------------- claude -p

class ClaudeError(RuntimeError):
    pass


def claude_json(prompt: str, schema: dict, *, model: str = MODEL, timeout: int = 900) -> dict:
    """`claude -p` sin herramientas; devuelve la salida estructurada validada por `schema`."""
    cmd = [CLAUDE, "-p", "--model", model, "--output-format", "json",
           "--json-schema", json.dumps(schema), "--tools", "", "--strict-mcp-config",
           "--no-session-persistence"]
    run = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                         timeout=timeout, cwd=ROOT)
    if run.returncode:
        raise ClaudeError(f"claude -p falló ({run.returncode}): {(run.stderr or run.stdout)[-500:]}")
    reply = json.loads(run.stdout)
    out = reply.get("structured_output")
    if reply.get("is_error") or not isinstance(out, dict):
        raise ClaudeError(f"claude -p sin salida estructurada: {str(reply.get('result'))[:500]}")
    return out


EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date_start": {"type": ["string", "null"]},
                    "date_end": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "url": {"type": ["string", "null"]},
                    "tipo": {"type": "string", "enum": list(TIPO_A_SECCION)},
                },
                "required": ["title", "date_start", "date_end", "description", "url", "tipo"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- prompts

PROMPT = """\
Hoy es {today}. Abajo está el texto de la página «{source}» ({url}), una web de Madrid.
Extrae {que}.
{reglas}

Fechas, sin excepciones:
- Formato exacto YYYY-MM-DD. Nunca "2026-07" ni texto.
- Si el texto no dice el año, elige el que sitúe la fecha en los próximos 12 meses.
- Si el texto no da fecha, null. No la deduzcas ni la inventes.
- date_end, si existe, posterior o igual a date_start.

Enlaces: el texto marca cada enlace como «texto ⟨URL⟩». En "url" copia tal cual el enlace
propio del evento (su ficha, su página de entradas) si aparece; si no, null. Nunca inventes una URL.

"description": una frase concreta (quién lo firma, de qué trata) o null. Sin adjetivos promocionales.
"title": el título tal cual, sin el nombre de la sede ni fechas.
Un mismo evento listado varias veces es un solo resultado.
Si no hay ninguno, devuelve "events": [].

--- TEXTO ---
{text}"""

KINDS = {
    "museo": ("las exposiciones temporales de este museo o centro (no la colección permanente)",
              "No incluyas talleres, visitas guiadas, actividades infantiles, cursos, conferencias, "
              "conciertos ni programas educativos. tipo: \"exposicion\"."),
    "galeria": ("las exposiciones actuales o próximas de esta galería en su sede de Madrid",
                "No incluyas ferias, noticias ni exposiciones de sus artistas en otras instituciones. "
                "Si la exposición no tiene título, usa el nombre del artista. tipo: \"exposicion\"."),
    "charla": ("las charlas, conferencias, coloquios, mesas redondas y presentaciones de libros",
               "No incluyas exposiciones, talleres, cursos, actividades infantiles ni becas. "
               "date_start es el día en que se celebra; date_end null salvo ciclos de varios días. "
               "tipo: \"charla\"."),
    "teatro": ("las obras de teatro, danza y espectáculos escénicos",
               "No incluyas talleres, visitas, cursos ni actividades educativas. Una obra con varias "
               "funciones es UN resultado, con date_start el primer día en cartel y date_end el último. "
               "tipo: \"teatro\"."),
    "musica": ("los conciertos",
               "En title, el artista o cartel principal; los teloneros van en description. "
               "date_start es el día del concierto. No incluyas sesiones de DJ genéricas ni fiestas "
               "sin artista anunciado. tipo: \"musica\"."),
    "cine": ("las películas en cartelera",
             "description: director y etiquetas como estreno, VOSE o pase con coloquio, si aparecen. "
             "Fechas: null salvo que sea un pase o un ciclo con días concretos. tipo: \"cine\"."),
    "agenda": ("las actividades culturales que programa: exposiciones, teatro y danza, charlas y "
               "presentaciones, cine (pases y ciclos) y conciertos",
               "Clasifica cada una en tipo. No incluyas talleres, cursos, visitas guiadas, "
               "actividades educativas, becas ni convocatorias."),
}


# ---------------------------------------------------------------- descarga

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def _es_error_de_certificado(exc: BaseException) -> bool:
    """httpx envuelve el ssl.SSLError dos niveles abajo; hay que bajar a buscarlo."""
    visto = set()
    while exc is not None and id(exc) not in visto:
        if isinstance(exc, ssl.SSLError):
            return True
        visto.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def fetch_html(url: str, retries: int = 2) -> str:
    """Descarga el HTML de una URL con reintentos.

    Ante error de certificado reintenta una vez sin verificar: varias sedes
    públicas (culturaydeporte.gob.es, fundacionico.es, cinesembajadores.es)
    sirven cadenas incompletas y llevaban meses caídas por eso. Sólo leemos
    HTML público y no mandamos credenciales a ningún sitio, así que lo peor
    que puede pasar es leer una página manipulada.
    """
    last_err = None
    sin_verificar = False
    for attempt in range(retries):
        try:
            return httpx.get(url, follow_redirects=True, timeout=45,
                             headers=FETCH_HEADERS,
                             verify=not sin_verificar).raise_for_status().text
        except (httpx.HTTPError, ssl.SSLError) as e:
            last_err = e
            if not sin_verificar and _es_error_de_certificado(e):
                log.warning("  %s: certificado inválido, reintento sin verificar", url)
                sin_verificar = True
                continue  # no cuenta como reintento: es otra estrategia
            if attempt < retries - 1:
                time.sleep(3)
    raise last_err


def render_html(url: str, wait_ms: int = 15_000) -> str:
    """DOM final de una página que pinta sus eventos con JavaScript (Chrome headless)."""
    with tempfile.TemporaryDirectory(prefix="culturalme-chrome-") as profile:
        run = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
             f"--user-data-dir={profile}", f"--virtual-time-budget={wait_ms}", "--dump-dom", url],
            capture_output=True, text=True, timeout=120)
    if run.returncode or not run.stdout.strip():
        raise RuntimeError(f"Chrome no pudo abrir {url}: {run.stderr[-300:]}")
    return run.stdout


def page_text(raw_html: str, base_url: str | None = None) -> tuple[str, dict[str, str]]:
    """Texto plano de la página con cada enlace marcado como «texto ⟨URL⟩».

    Devuelve también los enlaces que quedan en el texto (normalizados → URL),
    para comprobar después que la URL que elige el modelo existe en la página.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe",
                              "nav", "footer", "header"]):
        tag.decompose()

    root = (soup.find("main") or soup.find("article")
            or soup.find(id="content") or soup.find(class_="content") or soup)

    links: dict[str, str] = {}
    if base_url:
        for a in root.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = urldefrag(urljoin(base_url, href))[0]
            key = _norm(absolute)
            if not absolute.startswith("http") or key == _norm(base_url) or key in links:
                continue  # cada URL se marca una vez, en el primer enlace con texto
            label = a.get_text(" ", strip=True)
            if len(label) < 3:
                continue
            links[key] = absolute
            a.replace_with(f"{label} ⟨{absolute}⟩")  # en la misma línea que su texto

    text = root.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text), links


def clean_html(raw_html: str) -> str:
    """Texto plano sin marcas de enlace."""
    return page_text(raw_html)[0]


def _norm(url: str) -> str:
    return url.strip().rstrip("/").lower()


def own_url(candidate, links: dict[str, str], page_url: str) -> str:
    """La URL del evento si de verdad está en la página; si no, la de la página."""
    if isinstance(candidate, str) and candidate.strip():
        absolute = urldefrag(urljoin(page_url, candidate.strip()))[0]
        found = links.get(_norm(absolute))
        if found:
            return found
    return page_url


# ---------------------------------------------------------------- fechas

def _parse_date(value) -> date | None:
    """YYYY-MM-DD estricto dentro de la ventana aceptable. Si no, None."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return None
    try:
        d = date.fromisoformat(v)
    except ValueError:
        return None
    today = date.today()
    if not (today - timedelta(days=PAST_TOLERANCE_DAYS) <= d
            <= today + timedelta(days=FUTURE_HORIZON_DAYS)):
        return None
    return d


def sanitize_dates(event: dict) -> dict:
    """Sanea date_start/date_end. Una fecha mala se descarta; el evento sobrevive."""
    start = _parse_date(event.get("date_start"))
    end = _parse_date(event.get("date_end"))

    # "del 9 de julio al 10 de enero": el cierre es del año siguiente.
    if start and end and end < start:
        try:
            bumped = end.replace(year=end.year + 1)
        except ValueError:  # 29 de febrero
            bumped = None
        end = bumped if bumped and bumped >= start and _parse_date(bumped.isoformat()) else None

    event["date_start"] = start.isoformat() if start else None
    event["date_end"] = end.isoformat() if end else None
    return event


# ---------------------------------------------------------------- extracción

def build_prompt(fuente: Fuente, text: str) -> str:
    que, reglas = KINDS[fuente.kind]
    return PROMPT.format(today=date.today().isoformat(), source=fuente.name, url=fuente.url,
                         que=que, reglas=reglas, text=text)


def _cut(text: str, marker: str) -> str:
    """Corta antes de la segunda aparición de `marker` (la primera suele ser un menú)."""
    first = text.find(marker)
    if first < 0:
        return text
    second = text.find(marker, first + len(marker))
    cut_at = second if second >= 0 else first
    return text[:cut_at] if cut_at > 100 else text


def to_events(fuente: Fuente, raw: list[dict], links: dict[str, str]) -> list[dict]:
    """Respuesta del modelo → filas para la base de datos."""
    out = []
    for e in raw:
        title = (e.get("title") or "").strip()
        if not title:
            continue
        section = TIPO_A_SECCION.get(e.get("tipo"), "museo") if fuente.kind == "agenda" else fuente.kind
        out.append(sanitize_dates({
            "title": title,
            "section": section,
            "source": fuente.name,
            "source_url": fuente.url,
            "venue": fuente.venue,
            "date_start": e.get("date_start"),
            "date_end": e.get("date_end"),
            "description": (e.get("description") or "").strip() or None,
            "url": own_url(e.get("url"), links, fuente.url),
        }))
    return out


def extract(fuente: Fuente) -> list[dict]:
    """Descarga la página de una fuente y devuelve sus eventos."""
    raw_html = render_html(fuente.url) if fuente.render else fetch_html(fuente.url)
    text, links = page_text(raw_html, fuente.url)
    if fuente.cut:
        text = _cut(text, fuente.cut)
    text = text[:MAX_TEXT_CHARS]
    answer = claude_json(build_prompt(fuente, text), EVENT_SCHEMA)
    events = to_events(fuente, answer.get("events", []), links)
    log.info("  %s: %d eventos", fuente.name, len(events))
    return events
