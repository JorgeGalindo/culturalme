"""
Extracción de eventos via Claude Haiku.
Módulo compartido por todos los scrapers.
"""

import json
import logging
import os
import re
import ssl
import time
from datetime import date, timedelta

import anthropic
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
THROTTLE_SECONDS = 3  # 50K tokens/min en tier básico
MAX_HTML_CHARS = 30_000

# Ventana de fechas aceptables. Fuera de ella la fecha la ha puesto el modelo,
# no la web. Generosa hacia atrás a propósito: una exposición del Reina Sofía
# puede llevar año y medio abierta, y nular su inicio destruye un dato bueno.
# De filtrar lo que ya pasó se encarga la vista, no el extractor.
PAST_TOLERANCE_DAYS = 730
FUTURE_HORIZON_DAYS = 548  # ~18 meses: cabe una temporada teatral completa

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazy init: error claro si falta ANTHROPIC_API_KEY."""
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY no está definida. "
                "En local: export ANTHROPIC_API_KEY=sk-ant-... "
                "En GitHub Actions: añádela en Settings → Secrets and variables → Actions."
            )
        _client = anthropic.Anthropic()
    return _client


# Preámbulo común: ancla temporal. Sin esto el modelo inventa el año cuando la
# web escribe "del 9 de julio al 10 de enero" — origen de casi toda la basura.
DATE_RULES = """\
Hoy es {today}.

Reglas de fecha, sin excepciones:
- Formato exacto YYYY-MM-DD. Nunca "2026-07" ni texto.
- Si el texto no dice el año, elige el que sitúe la fecha en los próximos 12 meses.
- Si el texto no da fecha, devuelve null. NO la deduzcas ni la inventes.
- date_end siempre posterior a date_start.
"""

EXTRACTION_PROMPTS = {
    "default": """\
Extrae los eventos culturales principales del siguiente texto de una web.
NO incluyas: talleres, visitas guiadas, actividades infantiles, cursos, becas, \
conferencias de prensa, ni actividades educativas. Solo el evento/exposición/obra principal.
Elimina duplicados (mismo título = un solo resultado).

{date_rules}
JSON array. Cada objeto:
- "title": título
- "date_start": YYYY-MM-DD o null
- "date_end": YYYY-MM-DD o null
- "description": 2-3 frases descriptivas sobre de qué trata, o null
- "url": URL si aparece, o null
Si no hay eventos, devuelve []. Solo JSON.

Texto:
{html}""",

    "museo": """\
Extrae SOLO las exposiciones (temporales y permanentes) de este texto de un museo/centro de arte.
NO incluyas: talleres, visitas guiadas, actividades infantiles, cursos, conferencias, \
mesas redondas, conciertos, ni programas educativos. SOLO exposiciones.
Elimina duplicados.

{date_rules}
JSON array. Cada objeto:
- "title": título de la exposición
- "date_start": YYYY-MM-DD o null
- "date_end": YYYY-MM-DD o null
- "description": 1 frase o null
- "url": URL si aparece, o null

Solo JSON.

Texto:
{html}""",

    "charla": """\
Extrae SOLO charlas, conferencias, coloquios, mesas redondas y presentaciones de este texto.
NO incluyas: exposiciones, talleres, cursos, actividades infantiles ni becas.
Elimina duplicados.

{date_rules}
JSON array. Cada objeto:
- "title": título
- "date_start": YYYY-MM-DD o null (el día en que se celebra)
- "date_end": null salvo que sea un ciclo de varios días
- "description": 1 frase o null (tema/ponente si se menciona)
- "url": URL si aparece, o null

Solo JSON.

Texto:
{html}""",

    "teatro": """\
Extrae SOLO las obras de teatro, danza y espectáculos escénicos de este texto.
NO incluyas: talleres, visitas, cursos ni actividades educativas.
Elimina duplicados: una obra con varias funciones es UN solo resultado, con
date_start el primer día en cartel y date_end el último.

{date_rules}
JSON array. Cada objeto:
- "title": título de la obra
- "date_start": YYYY-MM-DD o null
- "date_end": YYYY-MM-DD o null
- "description": 1 frase o null (director/compañía si se menciona)
- "url": URL si aparece, o null

Solo JSON.

Texto:
{html}""",

    "galeria": """\
Extrae SOLO las exposiciones actuales o próximas de esta galería de arte.
NO incluyas: ferias pasadas, noticias, eventos sociales, exposiciones de sus
artistas en OTRAS instituciones, ni actividades no relacionadas con exposiciones.
Elimina duplicados.

{date_rules}
JSON array. Cada objeto:
- "title": título de la exposición (o nombre del artista si no hay título)
- "date_start": YYYY-MM-DD o null
- "date_end": YYYY-MM-DD o null
- "description": 1 frase o null
- "url": URL si aparece, o null

Solo JSON.

Texto:
{html}""",
}


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


def clean_html(raw_html: str) -> str:
    """Limpia HTML: quita scripts, styles, nav, footer, devuelve texto plano."""
    soup = BeautifulSoup(raw_html, "lxml")

    for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe",
                              "nav", "footer", "header"]):
        tag.decompose()

    main = (soup.find("main") or soup.find("article")
            or soup.find(id="content") or soup.find(class_="content"))
    text = (main or soup).get_text(separator="\n", strip=True)

    return re.sub(r"\n{3,}", "\n\n", text)


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
        end = bumped if bumped and _parse_date(bumped.isoformat()) else None

    event["date_start"] = start.isoformat() if start else None
    event["date_end"] = end.isoformat() if end else None
    return event


def call_llm_for_json(prompt: str, max_tokens: int = 8192) -> list[dict]:
    """Llama a Haiku con `prompt`, parsea la respuesta como JSON array.

    Robusto a respuestas envueltas en ```json ... ``` y a texto extra
    alrededor del array. Throttle de THROTTLE_SECONDS al final para no
    pegarle al rate limit.
    """
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Quita ```json ... ``` o ``` ... ``` envoltorios
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.S)
        if not match:
            log.warning("  No se pudo parsear JSON de la respuesta LLM")
            time.sleep(THROTTLE_SECONDS)
            return []
        try:
            result = json.loads(match.group())
        except json.JSONDecodeError:
            log.warning("  JSON malformado en la respuesta LLM")
            time.sleep(THROTTLE_SECONDS)
            return []

    time.sleep(THROTTLE_SECONDS)
    return [e for e in result if isinstance(e, dict)] if isinstance(result, list) else []


def extract_events(url: str, source_name: str, section: str,
                    truncate_before: str | None = None) -> list[dict]:
    """Descarga HTML, limpia, y usa Haiku para extraer eventos.

    truncate_before: corta el texto antes de la SEGUNDA aparición de la
    cadena (la primera suele ser un menú). Útil para webs que listan
    expos pasadas tras las actuales.
    """
    html = fetch_html(url)
    cleaned = clean_html(html)

    if truncate_before:
        first = cleaned.find(truncate_before)
        if first >= 0:
            second = cleaned.find(truncate_before, first + len(truncate_before))
            cut_at = second if second >= 0 else first
            if cut_at > 100:
                cleaned = cleaned[:cut_at]

    if len(cleaned) > MAX_HTML_CHARS:
        cleaned = cleaned[:MAX_HTML_CHARS]

    prompt_template = EXTRACTION_PROMPTS.get(section, EXTRACTION_PROMPTS["default"])
    events = call_llm_for_json(prompt_template.format(
        html=cleaned,
        date_rules=DATE_RULES.format(today=date.today().isoformat()),
    ))

    out = []
    for e in events:
        if not (e.get("title") or "").strip():
            continue
        e["title"] = e["title"].strip()
        e["source"] = source_name
        e["section"] = section
        if e.get("url") and not str(e["url"]).startswith("http"):
            base = url.rsplit("/", 1)[0]
            e["url"] = base + "/" + str(e["url"]).lstrip("/")
        if not e.get("url"):
            e["url"] = url
        out.append(sanitize_dates(e))

    log.info("  %s: %d eventos extraídos via LLM", source_name, len(out))
    return out
