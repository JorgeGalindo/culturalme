"""
Extracción de eventos via Claude Haiku.
Módulo compartido por museos, galerías y salas de conciertos.
"""

import json
import logging
import re
import time

import anthropic
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

client = anthropic.Anthropic()

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
            resp = httpx.get(url, follow_redirects=True, timeout=45, verify=False,
                             headers=FETCH_HEADERS)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
            last_err = e
            if attempt < retries - 1:
                wait = 5 * (attempt + 1)
                log.warning("  Retry %d/%d para %s (%s), esperando %ds",
                            attempt + 1, retries - 1, url, e, wait)
                time.sleep(wait)
    raise last_err


def _clean_html(raw_html: str) -> str:
    """Limpia HTML: quita scripts, styles, nav, footer, y devuelve texto útil con URLs de imagen."""
    soup = BeautifulSoup(raw_html, "lxml")

    # Eliminar elementos que no aportan contenido
    for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe",
                              "nav", "footer", "header"]):
        tag.decompose()

    # Intentar extraer solo el contenido principal
    main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.find(class_="content")
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Colapsar líneas vacías
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_events(url: str, source_name: str, section: str,
                    truncate_before: str | None = None) -> list[dict]:
    """Descarga HTML, limpia, y usa Haiku para extraer eventos.

    truncate_before: si se especifica, corta el texto justo antes de esta cadena.
        Útil para webs que listan expos pasadas después de las actuales.
        Se busca la SEGUNDA ocurrencia (la primera suele ser un menú/nav).
    """
    html = fetch_html(url)

    # Limpiar HTML antes de enviar a Haiku — reduce tokens drásticamente
    cleaned = _clean_html(html)

    # Cortar antes de una sección no deseada (ej. "Pasadas")
    if truncate_before:
        # Buscar la segunda ocurrencia (la primera suele ser menú)
        first = cleaned.find(truncate_before)
        if first >= 0:
            second = cleaned.find(truncate_before, first + len(truncate_before))
            cut_at = second if second >= 0 else first
            if cut_at > 100:  # solo cortar si hay contenido antes
                cleaned = cleaned[:cut_at]

    # Truncar si aún es muy largo
    if len(cleaned) > 30_000:
        cleaned = cleaned[:30_000]

    # Seleccionar prompt específico por sección
    prompt_template = EXTRACTION_PROMPTS.get(section, EXTRACTION_PROMPTS["default"])

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt_template.format(html=cleaned)}],
    )

    text = response.content[0].text.strip()
    # Limpiar posible markdown wrapping
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        events = json.loads(text)
    except json.JSONDecodeError:
        # Intentar extraer el primer array JSON válido del texto
        match = re.search(r'\[.*\]', text, re.S)
        if match:
            events = json.loads(match.group())
        else:
            log.warning("  %s: no se pudo parsear JSON de la respuesta LLM", source_name)
            events = []

    for e in events:
        e["source"] = source_name
        e["section"] = section
        # Asegurar que url sea absoluta si es relativa
        if e.get("url") and not e["url"].startswith("http"):
            base = url.rsplit("/", 1)[0]
            e["url"] = base + "/" + e["url"].lstrip("/")
        # Fallback: si no hay URL del evento, usar la URL de la fuente
        if not e.get("url"):
            e["url"] = url

    log.info("  %s: %d eventos extraídos via LLM", source_name, len(events))
    # Throttle para no pegarle al rate limit (50K tokens/min en tier básico)
    time.sleep(3)
    return events
