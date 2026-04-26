"""
Scraper de conciertos en Madrid — solo artistas que están en la lista del usuario.
Fuentes: Bandsintown (LLM) + DICE (API JSON) + 11 salas individuales (LLM).
"""

import logging
import os
import re
import unicodedata

import httpx

from scrapers.llm import (
    call_llm_for_json,
    clean_html,
    extract_events,
    fetch_html,
)

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
    ("Café Berlín", "https://www.cafeberlin.es/"),
    ("Galileo Galilei", "https://salagalileo.es/"),
    ("Teatro Barceló", "https://teatrobarcelo.com/"),
]

BANDSINTOWN_URL = "https://www.bandsintown.com/c/madrid-spain"
DICE_API_URL = "https://events-api.dice.fm/v1/events"

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
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    if name.startswith("the "):
        name = name[4:]
    return name


def _match_artists(events: list[dict], artists: set[str]) -> list[dict]:
    """Conserva sólo los eventos cuyo título coincide con un artista de la lista."""
    matched = []
    normalized = {_normalize(a): a for a in artists if len(_normalize(a)) >= 3}

    for e in events:
        title_norm = _normalize(e["title"])
        parts = re.split(r"[+,|/]|\bfeat\.?\b|\bvs\.?\b|\bx\b", title_norm)
        parts = [p.strip() for p in parts if p.strip()] + [title_norm]

        for norm, original in normalized.items():
            for part in parts:
                cleaned = re.sub(
                    r"\s*-?\s*(sold out|live|dj set|en directo|presenta).*$",
                    "", part,
                ).strip()
                if cleaned == norm:
                    e["artist_match"] = original
                    matched.append(e)
                    break
            else:
                continue
            break
    return matched


def _scrape_bandsintown(artists: set[str]) -> list[dict]:
    cleaned = clean_html(fetch_html(BANDSINTOWN_URL))[:30_000]
    events = call_llm_for_json(BANDSINTOWN_PROMPT.format(text=cleaned))

    for e in events:
        e["section"] = "concierto"
        e["source"] = e.get("venue") or "Bandsintown"

    log.info("  Bandsintown: %d conciertos en Madrid", len(events))
    matched = _match_artists(events, artists)
    log.info("  Bandsintown: %d matchean con la lista", len(matched))
    return matched


def _scrape_dice(artists: set[str]) -> list[dict]:
    api_key = os.environ.get("DICE_API_KEY")
    if not api_key:
        log.warning("  DICE_API_KEY no definida — saltando DICE")
        return []

    all_events: list[dict] = []
    page = 1
    while True:
        resp = httpx.get(
            DICE_API_URL,
            params={
                "filter[cities]": "madrid",
                "page[size]": 50,
                "page[number]": page,
            },
            headers={"x-api-key": api_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        events = data.get("data", [])
        if not events:
            break

        for ev in events:
            venue = ev.get("venue") or ""
            date_str = (ev.get("date") or "")[:10] or None
            all_events.append({
                "title": ev.get("name", ""),
                "source": venue or "DICE",
                "section": "concierto",
                "venue": venue,
                "date_start": date_str,
                "description": None,
                "url": ev.get("url") or f"https://dice.fm/event/{ev.get('perm_name', '')}",
            })

        if not data.get("links", {}).get("next"):
            break
        page += 1

    log.info("  DICE: %d conciertos en Madrid", len(all_events))
    matched = _match_artists(all_events, artists)
    log.info("  DICE: %d matchean con la lista", len(matched))
    return matched


def _dedup(events: list[dict]) -> list[dict]:
    """Mismo artista + misma fecha = mismo concierto."""
    seen, out = set(), []
    for e in events:
        key = (_normalize(e.get("artist_match") or e["title"]), e.get("date_start") or "")
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def scrape(artists: set[str]) -> list[dict]:
    all_events: list[dict] = []

    try:
        all_events.extend(_scrape_bandsintown(artists))
    except Exception:
        log.exception("  ✗ Error scraping Bandsintown")

    try:
        all_events.extend(_scrape_dice(artists))
    except Exception:
        log.exception("  ✗ Error scraping DICE")

    for name, url in SALAS:
        try:
            events = extract_events(url, source_name=name, section="concierto")
            matched = _match_artists(events, artists)
            all_events.extend(matched)
            log.info("  %s: %d eventos, %d match", name, len(events), len(matched))
        except Exception:
            log.exception("  ✗ Error scraping %s", name)

    before = len(all_events)
    all_events = _dedup(all_events)
    if before > len(all_events):
        log.info("  Dedup: %d → %d conciertos", before, len(all_events))

    return all_events
