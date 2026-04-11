"""
CulturalMe — genera el sitio estático en docs/.
Lee la DB y genera docs/index.html con todos los datos incrustados como JSON.
Los filtros, orden y dropdown de sedes funcionan con JS vanilla en el cliente.
"""

import json
import shutil
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "culturalme.db"
DOCS_DIR = Path(__file__).parent / "docs"
STATIC_DIR = Path(__file__).parent / "static"

SECTIONS = ["museo", "concierto", "galeria", "charla", "cine", "teatro"]
SECTION_LABELS = {
    "museo": "Museos",
    "concierto": "Conciertos",
    "galeria": "Galerías",
    "charla": "Charlas",
    "cine": "Cine",
    "teatro": "Teatro",
}


def load_events() -> list[dict]:
    """Carga eventos vigentes de la DB."""
    today = date.today().isoformat()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    row = con.execute("SELECT MAX(last_seen) as latest FROM events").fetchone()
    latest_run = row["latest"] if row else today

    rows = con.execute("""
        SELECT *, (first_seen = ?) as is_new
        FROM events
        WHERE (
            section = 'cine'
            OR date_end >= ?
            OR (date_end IS NULL AND date_start >= ?)
            OR (date_end IS NULL AND date_start IS NULL)
        )
        ORDER BY first_seen DESC, COALESCE(date_start, '9999-12-31') ASC
    """, (latest_run, today, today)).fetchall()

    con.close()

    events = []
    for r in rows:
        events.append({
            "title": r["title"],
            "section": r["section"],
            "venue": r["venue"],
            "source": r["source"],
            "date_start": r["date_start"],
            "date_end": r["date_end"],
            "description": r["description"],
            "url": r["url"],
            "artist_match": r["artist_match"],
            "first_seen": r["first_seen"],
            "is_new": bool(r["is_new"]),
        })

    return events, latest_run


def generate():
    events, latest_run = load_events()

    DOCS_DIR.mkdir(exist_ok=True)

    # Copy CSS
    shutil.copy(STATIC_DIR / "style.css", DOCS_DIR / "style.css")

    # Build HTML
    events_json = json.dumps(events, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>CulturalMe — Madrid</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;0,9..144,800;1,9..144,300;1,9..144,400;1,9..144,700;1,9..144,800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1><span class="brand-c">Cultural</span><span class="brand-m">Me</span> <span class="meta">Madrid</span></h1>
  </header>

  <nav class="filter-bar" id="filterBar"></nav>

  <div class="controls-bar">
    <div class="sort-links">
      <a href="#" class="active" data-sort="nuevo" onclick="setSort('nuevo')">Más nuevo</a>
      <a href="#" data-sort="fecha" onclick="setSort('fecha')">Por fecha</a>
    </div>
    <div class="venue-filter">
      <select class="venue-select" id="venueSelect" onchange="render()">
        <option value="">Todas las sedes</option>
      </select>
    </div>
  </div>

  <main id="cards"></main>

  <footer>
    <p>Actualizado {latest_run}</p>
  </footer>

  <script>
  const EVENTS = {events_json};
  const SECTIONS = {json.dumps(SECTIONS)};
  const LABELS = {json.dumps(SECTION_LABELS, ensure_ascii=False)};

  const PICTOS = {{
    museo: '<svg viewBox="0 0 16 16"><path d="M2 14V7h12v7"/><path d="M1 7l7-5 7 5"/><path d="M5 14v-4h2v4m2 0v-4h2v4"/></svg>',
    concierto: '<svg viewBox="0 0 16 16"><circle cx="4" cy="12" r="2"/><circle cx="12" cy="10" r="2"/><path d="M6 12V4l8-2v8"/></svg>',
    galeria: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="10" rx="1"/><circle cx="6" cy="7" r="1.5"/><path d="M2 11l3-3 2 2 3-4 4 5"/></svg>',
    charla: '<svg viewBox="0 0 16 16"><path d="M3 3h10a1 1 0 011 1v6a1 1 0 01-1 1H7l-3 3v-3H3a1 1 0 01-1-1V4a1 1 0 011-1z"/></svg>',
    cine: '<svg viewBox="0 0 16 16"><rect x="2" y="4" width="12" height="9" rx="1"/><path d="M2 7h12M5 4v3m3-3v3m3-3v3"/><path d="M5 2h6"/></svg>',
    teatro: '<svg viewBox="0 0 16 16"><path d="M2 4c0 0 2 2 6 2s6-2 6-2"/><path d="M4 6c0 2.5 1.5 5 4 5s4-2.5 4-5"/><circle cx="6" cy="8" r="0.8"/><circle cx="10" cy="8" r="0.8"/><path d="M7 10.5c0 0 .5.5 1 .5s1-.5 1-.5"/></svg>'
  }};

  let currentSection = 'all';
  let currentSort = 'nuevo';

  function seenKey(e) {{ return e.title + '||' + e.section; }}
  function getSeen() {{ try {{ return JSON.parse(localStorage.getItem('culturalme_seen') || '[]'); }} catch {{ return []; }} }}
  function isSeen(e) {{ return getSeen().includes(seenKey(e)); }}
  function toggleSeen(e) {{
    let s = getSeen();
    const k = seenKey(e);
    if (s.includes(k)) s = s.filter(x => x !== k);
    else s.push(k);
    localStorage.setItem('culturalme_seen', JSON.stringify(s));
    render();
  }}

  function picto(s) {{ return '<span class="picto">' + PICTOS[s] + '</span>'; }}

  function buildFilters() {{
    const bar = document.getElementById('filterBar');
    bar.innerHTML = '<a href="#" class="filter-btn active" onclick="setSection(\\'all\\')">todo</a>';
    SECTIONS.forEach(s => {{
      bar.innerHTML += `<a href="#" class="filter-btn" data-section="${{s}}" onclick="setSection('${{s}}')">${{picto(s)}} ${{LABELS[s]}}</a>`;
    }});
  }}

  function setSection(s) {{
    currentSection = s;
    render();
  }}

  function setSort(s) {{
    currentSort = s;
    render();
  }}

  function render() {{
    const venue = document.getElementById('venueSelect').value;

    // Filter
    let filtered = EVENTS.filter(e => {{
      if (currentSection !== 'all' && e.section !== currentSection) return false;
      if (venue && e.source !== venue && e.venue !== venue) return false;
      return true;
    }});

    // Sort
    const seenSet = new Set(getSeen());
    if (currentSort === 'fecha') {{
      filtered.sort((a, b) => {{
        const sa = seenSet.has(seenKey(a)) ? 1 : 0;
        const sb = seenSet.has(seenKey(b)) ? 1 : 0;
        if (sa !== sb) return sa - sb;
        const da = a.date_end || a.date_start || '9999-12-31';
        const db = b.date_end || b.date_start || '9999-12-31';
        return da.localeCompare(db) || (b.first_seen || '').localeCompare(a.first_seen || '');
      }});
    }} else {{
      filtered.sort((a, b) => {{
        const sa = seenSet.has(seenKey(a)) ? 1 : 0;
        const sb = seenSet.has(seenKey(b)) ? 1 : 0;
        if (sa !== sb) return sa - sb;
        const fa = b.first_seen || '';
        const fb = a.first_seen || '';
        if (fa !== fb) return fa.localeCompare(fb);
        const da = a.date_start || '9999-12-31';
        const db = b.date_start || '9999-12-31';
        return da.localeCompare(db);
      }});
    }}

    // Update filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {{
      const s = btn.getAttribute('data-section') || 'all';
      btn.classList.toggle('active', s === (currentSection === 'all' && !btn.dataset.section ? 'all' : currentSection));
    }});
    // Fix: simpler active logic
    document.querySelectorAll('.filter-btn').forEach(btn => {{
      const isAll = !btn.dataset.section;
      btn.classList.toggle('active', isAll ? currentSection === 'all' : btn.dataset.section === currentSection);
    }});

    // Update sort links
    document.querySelectorAll('.sort-links a').forEach(a => {{
      a.classList.toggle('active', a.dataset.sort === currentSort);
    }});

    // Update venue dropdown
    const venueSet = new Set();
    EVENTS.forEach(e => {{
      if (currentSection === 'all' || e.section === currentSection) {{
        venueSet.add(e.source);
      }}
    }});
    const sel = document.getElementById('venueSelect');
    const curVenue = sel.value;
    sel.innerHTML = '<option value="">Todas las sedes</option>';
    [...venueSet].sort().forEach(v => {{
      sel.innerHTML += `<option value="${{v}}" ${{v === curVenue ? 'selected' : ''}}>${{v}}</option>`;
    }});

    // Render cards
    const main = document.getElementById('cards');
    if (!filtered.length) {{
      main.innerHTML = '<div class="empty"><p>No hay eventos con estos filtros.</p></div>';
      return;
    }}

    main.innerHTML = filtered.map(e => {{
      const where = e.venue || (e.source !== e.title ? e.source : '');
      const hasDate = e.date_start || e.date_end;
      let dateStr = '';
      if (e.date_start && e.date_end) dateStr = e.date_start + ' — ' + e.date_end;
      else if (e.date_start) dateStr = e.date_start;
      else if (e.date_end) dateStr = 'Hasta ' + e.date_end;

      const seen = isSeen(e);
      return `<article class="card${{seen ? ' seen' : ''}}">
        <div class="card-title-row">
          <h2>${{e.url ? '<a href="' + e.url + '" target="_blank" rel="noopener">' + e.title + '</a>' : e.title}}</h2>
          <div class="card-tag-badge">
            <span class="tag tag-${{e.section}}">${{picto(e.section)}} ${{LABELS[e.section]}}</span>
            ${{e.is_new ? '<span class="badge-new">nuevo</span>' : ''}}
          </div>
        </div>
        <div class="card-dates">
          ${{where ? '<span class="card-where">' + where + '</span>' : ''}}
          ${{where && hasDate ? '<span class="card-sep">&middot;</span>' : ''}}
          ${{dateStr}}
        </div>
        ${{e.artist_match ? '<p class="card-artist">' + e.artist_match + '</p>' : ''}}
        ${{e.description ? '<p class="card-description">' + e.description + '</p>' : ''}}
        <div class="card-bottom">
          <button class="btn-seen ${{seen ? 'active' : ''}}" onclick="toggleSeen(EVENTS[${{EVENTS.indexOf(e)}}])">Visto</button>
        </div>
      </article>`;
    }}).join('');
  }}

  buildFilters();
  render();
  </script>
</body>
</html>"""

    (DOCS_DIR / "index.html").write_text(html)
    print(f"Generated docs/index.html — {len(events)} events, {latest_run}")


if __name__ == "__main__":
    generate()
