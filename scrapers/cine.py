"""
Scraper de cartelera de cine en Madrid.
Modo: LLM (Claude Haiku) — Renoir.
Se reemplaza completamente en cada pasada (no acumula histórico).
"""

import json
import logging
import re
import time

import anthropic

from scrapers.llm import fetch_html, _clean_html, client

log = logging.getLogger(__name__)

CINE_PROMPT = """\
Extrae todas las películas en cartelera de este texto de una web de cines.

Devuelve un JSON array. Cada objeto debe tener:
- "title": título de la película
- "director": nombre del director (o null)
- "tags": etiquetas como "ESTRENO", "EVENTO ESPECIAL", "PASE CON COLOQUIO", etc. (o null)

Solo JSON, sin explicaciones. Si no hay películas, devuelve [].

Texto:
{text}"""


def _scrape_renoir() -> list[dict]:
    """Cines Renoir — cartelera general."""
    html = fetch_html("https://www.cinesrenoir.com/")
    cleaned = _clean_html(html)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": CINE_PROMPT.format(text=cleaned)}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        films = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', text, re.S)
        films = json.loads(match.group()) if match else []

    events = []
    for f in films:
        director = f.get("director") or ""
        tags = f.get("tags") or ""
        desc_parts = []
        if director:
            desc_parts.append(f"Dir: {director}")
        if tags:
            desc_parts.append(tags if isinstance(tags, str) else ", ".join(tags))

        events.append({
            "title": f["title"],
            "source": "Cines Renoir",
            "section": "cine",
            "venue": "Cines Renoir (Princesa / Retiro / Plaza de España / Floridablanca)",
            "description": " — ".join(desc_parts) if desc_parts else None,
            "url": "https://www.cinesrenoir.com/",
        })

    log.info("  Cines Renoir: %d películas", len(events))
    time.sleep(3)
    return events


def scrape() -> list[dict]:
    all_events = []
    try:
        all_events.extend(_scrape_renoir())
    except Exception:
        log.exception("  ✗ Error scraping Cines Renoir")
    return all_events
