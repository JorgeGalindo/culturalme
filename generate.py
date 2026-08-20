"""
CulturalMe — genera el sitio estático en docs/.

Dos planos, porque son dos preguntas distintas:
  · "Esta semana": lo que tiene día — charlas, teatro y cine.
  · "Exposiciones": museos y galerías, que duran meses, ordenadas por cierre.

Nada se publica si no se ha visto en la última pasada del pipeline: una fuente
que deja de listar un evento es la señal de que el evento se acabó.
"""

import json
import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "culturalme.db"
DOCS_DIR = Path(__file__).parent / "docs"
STATIC_DIR = Path(__file__).parent / "static"

VENTANA_DIAS = 7
PROXIMOS_MAX = 12  # cuántos eventos futuros enseñar cuando la semana está vacía

AGENDA = ["charla", "teatro", "cine"]
EXPOS = ["museo", "galeria"]
LABELS = {
    "museo": "Museos",
    "galeria": "Galerías",
    "charla": "Charlas",
    "cine": "Cine",
    "teatro": "Teatro",
}


def load_events():
    """Carga lo vigente y lo reparte en los dos planos."""
    today = date.today()
    hoy = today.isoformat()
    fin = (today + timedelta(days=VENTANA_DIAS)).isoformat()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT MAX(last_seen) AS latest FROM events").fetchone()
    latest = row["latest"] if row and row["latest"] else hoy

    rows = con.execute(
        "SELECT * FROM events WHERE last_seen = ? ORDER BY title", (latest,)
    ).fetchall()
    con.close()

    agenda, expos = [], []
    for r in rows:
        e = {
            "title": r["title"],
            "section": r["section"],
            "venue": r["venue"],
            "source": r["source"],
            "date_start": r["date_start"],
            "date_end": r["date_end"],
            "description": r["description"],
            "url": r["url"],
            "is_new": r["first_seen"] == latest,
            "kids": bool(r["kids_friendly"]),
            "selecto": bool(r["selective"]),
        }
        ini, end = e["date_start"], e["date_end"]

        if e["section"] == "cine":
            e["grupo"] = "cine"          # la cartelera es, por definición, la de esta semana
            agenda.append(e)
        elif e["section"] in AGENDA:
            if ini and hoy <= ini <= fin:
                e["grupo"] = "dia"       # empieza estos días
                agenda.append(e)
            elif ini and ini < hoy and (end or ini) >= hoy:
                e["grupo"] = "cartel"    # ya abierto y sigue toda la semana
                agenda.append(e)
            elif ini and ini > fin:
                e["grupo"] = "proximo"   # sólo se pinta si la semana sale vacía
                agenda.append(e)
        elif e["section"] in EXPOS:
            abierta = (not ini or ini <= hoy) and (not end or end >= hoy)
            if abierta:
                expos.append(e)

    agenda.sort(key=lambda e: (e["date_start"] or "9999", e["title"]))
    # En agosto Madrid cierra: sin este recorte "próximamente" arrastraría
    # media temporada 2026/27 hasta junio.
    proximos = [e for e in agenda if e["grupo"] == "proximo"][:PROXIMOS_MAX]
    agenda = [e for e in agenda if e["grupo"] != "proximo"] + proximos
    agenda.sort(key=lambda e: (e["date_start"] or "9999", e["title"]))
    expos.sort(key=lambda e: (e["date_end"] or "9999", e["title"]))
    return agenda, expos, latest


def generate():
    agenda, expos, latest = load_events()

    DOCS_DIR.mkdir(exist_ok=True)
    shutil.copy(STATIC_DIR / "style.css", DOCS_DIR / "style.css")
    if (STATIC_DIR / "fonts").is_dir():
        shutil.copytree(STATIC_DIR / "fonts", DOCS_DIR / "fonts", dirs_exist_ok=True)

    def embed(obj):
        # `</script>` dentro de una cadena cerraría el bloque antes de tiempo.
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    anio = str(date.today().year)
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>CulturalMe — Madrid</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#000000">
<meta name="description" content="La agenda cultural de esta semana en Madrid.">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<link rel="stylesheet" href="style.css">
</head>
<body>

<header id="cabecera">
  <h1>CulturalMe</h1>
  <p class="lema">Madrid, esta semana</p>

  <nav class="chips" id="planos">
    <button class="chip on" data-plano="semana">esta semana</button>
    <button class="chip" data-plano="expos">exposiciones</button>
  </nav>

  <nav class="chips" id="modos">
    <button class="chip" data-modo="selecto">selecto</button>
    <button class="chip" data-modo="kids">niños</button>
  </nav>

  <nav class="chips" id="secciones"></nav>
</header>

<main id="lista"></main>

<footer><p>Actualizado el {latest}</p></footer>

<script>
const AGENDA = {embed(agenda)};
const EXPOS  = {embed(expos)};
const LABELS = {embed(LABELS)};

const ANIO = '{anio}';
const DIAS = ['dom','lun','mar','mié','jue','vie','sáb'];
const MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];

// Todo el contenido de las tarjetas lo escribe un LLM sobre HTML ajeno.
// Nada entra en el DOM sin pasar por aquí.
function esc(s) {{
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

function dmy(iso, conAnio) {{
  if (!iso) return '';
  const [y,m,d] = iso.split('-').map(Number);
  return d + ' ' + MESES[m-1] + (conAnio ? ' ' + y : '');
}}
function diaLargo(iso) {{
  const [y,m,d] = iso.split('-').map(Number);
  const f = new Date(Date.UTC(y, m-1, d));
  return DIAS[f.getUTCDay()] + ' ' + d + ' ' + MESES[m-1];
}}
function cuando(e) {{
  const a = e.date_start, b = e.date_end;
  // Una muestra de "1 dic 2025 – 31 oct 2026" sin años se lee al revés.
  const otro = [a, b].filter(Boolean).some(s => s.slice(0,4) !== ANIO);
  if (a && b) return a === b ? dmy(a, otro) : dmy(a, otro) + ' – ' + dmy(b, otro);
  if (a) return dmy(a, otro);
  if (b) return 'hasta el ' + dmy(b, otro);
  return '';
}}

let plano = 'semana';
let seccion = 'todo';
let modos = leer('culturalme_modos', {{}});
let vistos = new Set(leer('culturalme_seen', []));

function leer(k, def) {{
  try {{ return JSON.parse(localStorage.getItem(k)) ?? def; }} catch {{ return def; }}
}}
function clave(e) {{ return e.title + '||' + e.section; }}

function alternarVisto(k) {{
  vistos.has(k) ? vistos.delete(k) : vistos.add(k);
  localStorage.setItem('culturalme_seen', JSON.stringify([...vistos]));
  pintar();
}}

function tarjeta(e) {{
  const k = clave(e);
  const visto = vistos.has(k);
  const donde = e.venue || (e.source !== e.title ? e.source : '');
  const fecha = cuando(e);
  const meta = [donde, fecha].filter(Boolean).map(esc).join(' · ');
  // La URL también la escribe el LLM: sólo http(s) llega a un href.
  const href = /^https?:\\/\\//i.test(e.url || '') ? e.url : null;
  const titulo = href
    ? '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(e.title) + '</a>'
    : esc(e.title);
  return '<article class="ficha' + (visto ? ' visto' : '') + '">'
    + '<div class="et-fila"><span class="et">' + esc(LABELS[e.section]) + '</span>'
    + (e.is_new ? '<span class="et nuevo">nuevo</span>' : '') + '</div>'
    + '<h2>' + titulo + '</h2>'
    + (meta ? '<p class="meta">' + meta + '</p>' : '')
    + (e.description ? '<p class="nota">' + esc(e.description) + '</p>' : '')
    + '<button class="visto" data-k="' + esc(k) + '">' + (visto ? '✓ visto' : 'visto') + '</button>'
    + '</article>';
}}

function grupo(titulo, eventos) {{
  if (!eventos.length) return '';
  return '<section class="grupo"><h3>' + esc(titulo) + '</h3>'
       + eventos.map(tarjeta).join('') + '</section>';
}}

function pintar() {{
  const fuente = plano === 'semana' ? AGENDA : EXPOS;
  const secs = [...new Set(fuente.map(e => e.section))];

  document.getElementById('secciones').innerHTML =
    (secs.length > 1
      ? ['todo', ...secs].map(s =>
          '<button class="chip' + (s === seccion ? ' on' : '') + '" data-sec="' + s + '">'
          + (s === 'todo' ? 'todo' : esc(LABELS[s]).toLowerCase()) + '</button>').join('')
      : '');

  let ev = fuente.filter(e =>
    (seccion === 'todo' || e.section === seccion)
    && (!modos.kids || e.kids)
    && (!modos.selecto || e.selecto));

  // Los vistos se van al final sin desaparecer.
  const orden = a => vistos.has(clave(a)) ? 1 : 0;
  ev.sort((a,b) => orden(a) - orden(b));

  let html = '';
  if (!ev.length) {{
    html = '<p class="vacio">Nada con estos filtros.</p>';
  }} else if (plano === 'semana') {{
    const conDia = ev.filter(e => e.grupo === 'dia');
    const porDia = {{}};
    conDia.forEach(e => (porDia[e.date_start] ??= []).push(e));
    Object.keys(porDia).sort().forEach(d => {{ html += grupo(diaLargo(d), porDia[d]); }});
    html += grupo('en cartel', ev.filter(e => e.grupo === 'cartel'));
    html += grupo('cine', ev.filter(e => e.grupo === 'cine'));
    // Sólo cuando no hay nada con día propio: en agosto la ciudad cierra y una
    // agenda vacía se lee como una app rota.
    if (!conDia.length) {{
      const prox = ev.filter(e => e.grupo === 'proximo');
      if (prox.length) {{
        const porDiaProx = {{}};
        prox.forEach(e => (porDiaProx[e.date_start] ??= []).push(e));
        html += '<section class="grupo aparte"><h3>próximamente</h3></section>';
        Object.keys(porDiaProx).sort().forEach(d => {{
          html += grupo(diaLargo(d), porDiaProx[d]);
        }});
      }}
    }}
  }} else {{
    html = grupo('abiertas ahora', ev);
  }}
  document.getElementById('lista').innerHTML = html;

  document.querySelectorAll('#planos .chip').forEach(c =>
    c.classList.toggle('on', c.dataset.plano === plano));
  document.querySelectorAll('#modos .chip').forEach(c =>
    c.classList.toggle('on', !!modos[c.dataset.modo]));
}}

document.addEventListener('click', ev => {{
  const c = ev.target.closest('button');
  if (!c) return;
  if (c.dataset.plano) {{ plano = c.dataset.plano; seccion = 'todo'; pintar(); }}
  else if (c.dataset.modo) {{
    modos[c.dataset.modo] = !modos[c.dataset.modo];
    localStorage.setItem('culturalme_modos', JSON.stringify(modos));
    pintar();
  }}
  else if (c.dataset.sec) {{ seccion = c.dataset.sec; pintar(); }}
  else if (c.dataset.k) {{ alternarVisto(c.dataset.k); }}
}});

pintar();
</script>
</body>
</html>"""

    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"docs/index.html — {len(agenda)} esta semana, {len(expos)} exposiciones, datos del {latest}")


if __name__ == "__main__":
    generate()
