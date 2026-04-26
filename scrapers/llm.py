"""
Extracción de eventos via Claude Haiku.
Módulo compartido por todos los scrapers.
"""

import json
import logging
import os
import re
import time

import anthropic
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
THROTTLE_SECONDS = 3  # 50K tokens/min en tier básico
MAX_HTML_CHARS = 30_000

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


EXTRACTION_PROMPTS = {
    "default": """\
Extrae los eventos culturales principales del siguiente texto de una web.
NO incluyas: talleres, visitas guiadas, actividades infantiles, cursos, becas, \
conferencias de prensa, ni actividades educativas. Solo el evento/exposición/obra principal.
Elimina duplicados (mismo título = un solo resultado).

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

JSON array. Cada objeto:
- "title": título
- "date_start": YYYY-MM-DD o null
- "date_end": YYYY-MM-DD o null
- "description": 1 frase o null (tema/ponente si se menciona)
- "url": URL si aparece, o null

Solo JSON.

Texto:
{html}""",

    "teatro": """\
Extrae SOLO las obras de teatro, danza y espectáculos escénicos de este texto.
NO incluyas: talleres, visitas, cursos ni actividades educativas.
Elimina duplicados.

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
NO incluyas: ferias pasadas, noticias, eventos sociales ni actividades no relacionadas con exposiciones.
Elimina duplicados.

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


def fetch_html(url: str, retries: int = 3) -> str:
    """Descarga el HTML de una URL con reintentos."""
    last_err = None
    for attempt in range(retries):
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=45,
                             headers=FETCH_HEADERS)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError) as e:
            last_err = e
            if attempt < retries - 1:
                wait = 5 * (attempt + 1)
                log.warning("  Retry %d/%d para %s (%s), esperando %ds",
                            attempt + 1, retries - 1, url, e, wait)
                time.sleep(wait)
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
        result = json.loads(match.group())

    time.sleep(THROTTLE_SECONDS)
    return result if isinstance(result, list) else []


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
    events = call_llm_for_json(prompt_template.format(html=cleaned))

    for e in events:
        e["source"] = source_name
        e["section"] = section
        if e.get("url") and not e["url"].startswith("http"):
            base = url.rsplit("/", 1)[0]
            e["url"] = base + "/" + e["url"].lstrip("/")
        if not e.get("url"):
            e["url"] = url

    log.info("  %s: %d eventos extraídos via LLM", source_name, len(events))
    return events
