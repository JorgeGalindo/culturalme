"""
Scraper de conciertos en Madrid — solo artistas que están en tu lista.
Fuente principal: Bandsintown (agregador con buena cobertura).
Complemento: salas individuales via LLM.
"""

import json
import logging
import re
import time
import unicodedata

from scrapers.llm import extract_events, fetch_html, _clean_html, client, FETCH_HEADERS

log = logging.getLogger(__name__)

SALAS = [
    ("Sala El Sol", "https://salaelsol.com/"),
    ("Moby Dick Club", "https://www.mobydickclub.com/"),
    ("La Riviera", "https://salariviera.com/"),
    ("Sala But", "https://www.salabut.es/"),
    ("Clamores", "https://www.salaclamores.es/"),
    ("Siroco", "https://siroco.es/"),
    ("Independance Club", "https://independanceclub.com/"),
    ("Shoko Madrid", "https://shokomadrid.com/"),
    # JS-rendered (poco texto pero intentamos):
    ("Café Berlín", "https://www.cafeberlin.es/"),
    ("Galileo Galilei", "https://salagalileo.es/"),
    ("Teatro Barceló", "https://teatrobarcelo.com/"),
]

BANDSINTOWN_URL = "https://www.bandsintown.com/c/madrid-spain"

BANDSINTOWN_PROMPT = """\
Extrae TODOS los conciertos y eventos musicales de este texto de Bandsintown.

JSON array. Cada objeto:
- "title": nombre del artista o evento
- "date_start": YYYY-MM-DD o null
- "venue": nombre del recinto/sala
- "description": hora y detalles extra si los hay, o null
- "url": null

Solo JSON.

Texto:
{text}"""


def _normalize(name: str) -> str:
    """Normaliza un nombre de artista para matching."""
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    if name.startswith("the "):
        name = name[4:]
    return name


def _match_artists(events: list[dict], artists: set[str]) -> list[dict]:
    """Filtra eventos que matcheen con la lista de artistas."""
    matched = []
    normalized_artists = {_normalize(a): a for a in artists if len(_normalize(a)) >= 3}
    for e in events:
        title_norm = _normalize(e["title"])
        # Partir el título por separadores
        title_parts = re.split(r'[+,|/]|\bfeat\.?\b|\bvs\.?\b|\bx\b', title_norm)
        title_parts = [p.strip() for p in title_parts if p.strip()]
        # Añadir el título completo también
        title_parts.append(title_norm)

        for norm, original in normalized_artists.items():
            for part in title_parts:
                part_clean = re.sub(
                    r'\s*-?\s*(sold out|live|dj set|en directo|presenta).*$', '', part
                ).strip()
                if part_clean == norm:
                    e["artist_match"] = original
                    matched.append(e)
                    break
            else:
                continue
            break
    return matched


def _scrape_bandsintown(artists: set[str]) -> list[dict]:
    """Scrape Bandsintown Madrid y filtra contra lista de artistas."""
    html = fetch_html(BANDSINTOWN_URL)
    cleaned = _clean_html(html)
    if len(cleaned) > 30_000:
        cleaned = cleaned[:30_000]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{"role": "user", "content": BANDSINTOWN_PROMPT.format(text=cleaned)}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        events = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', text, re.S)
        events = json.loads(match.group()) if match else []

    for e in events:
        e["source"] = "Bandsintown"
        e["section"] = "concierto"
        if e.get("venue"):
            e["source"] = e["venue"]

    log.info("  Bandsintown: %d conciertos totales en Madrid", len(events))

    matched = _match_artists(events, artists)
    log.info("  Bandsintown: %d matchean con tu lista de artistas", len(matched))

    time.sleep(3)
    return matched


def _dedup(events: list[dict]) -> list[dict]:
    """Deduplica por artista + fecha (normalizado)."""
    seen = set()
    out = []
    for e in events:
        key = (_normalize(e.get("artist_match") or e["title"]), e.get("date_start") or "")
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def scrape(artists: set[str]) -> list[dict]:
    all_events = []

    # Bandsintown — fuente principal (agregador con mejor cobertura)
    try:
        all_events.extend(_scrape_bandsintown(artists))
    except Exception:
        log.exception("  ✗ Error scraping Bandsintown")

    # Salas individuales — complemento, puede encontrar cosas que Bandsintown no tiene
    for name, url in SALAS:
        try:
            events = extract_events(url, source_name=name, section="concierto")
            matched = _match_artists(events, artists)
            all_events.extend(matched)
            log.info("  %s: %d eventos, %d match", name, len(events), len(matched))
        except Exception:
            log.exception("  ✗ Error scraping %s", name)

    # Deduplicar (mismo artista + misma fecha = mismo concierto)
    before = len(all_events)
    all_events = _dedup(all_events)
    if before > len(all_events):
        log.info("  Dedup: %d → %d conciertos", before, len(all_events))

    return all_events
