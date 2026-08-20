"""
CulturalMe — genera el sitio estático en docs/.

Cuatro pestañas por tipo de actividad: exposiciones, cine, teatro y charlas.
No hay ventana temporal: se muestra todo lo vigente. La v2 probó a recortar a
"esta semana" y en agosto la agenda salía vacía — en Madrid la temporada
arranca en septiembre, así que el recorte escondía el catálogo entero.

Orden por defecto: fecha de fin ascendente, lo que cierra antes arriba.
Alternativa a un toque: lo recién detectado por el scraper.

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

# (clave, rótulo, secciones que agrupa)
PLANOS = [
    ("expos", "exposiciones", ["museo", "galeria"]),
    ("cine", "cine", ["cine"]),
    ("teatro", "teatro", ["teatro"]),
    ("charlas", "charlas", ["charla"]),
]
PLANO_DE = {sec: clave for clave, _, secs in PLANOS for sec in secs}

LABELS = {
    "museo": "Museos",
    "galeria": "Galerías",
    "charla": "Charlas",
    "cine": "Cine",
    "teatro": "Teatro",
}


def load_events():
    """Carga lo vigente de la última pasada y lo reparte por pestañas."""
    hoy = date.today().isoformat()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    fila = con.execute("SELECT MAX(last_seen) AS latest FROM events").fetchone()
    latest = fila["latest"] if fila and fila["latest"] else hoy

    rows = con.execute(
        "SELECT * FROM events WHERE last_seen = ? ORDER BY title", (latest,)
    ).fetchall()
    con.close()

    eventos = []
    for r in rows:
        ini_f, fin_f, sec = r["date_start"], r["date_end"], r["section"]

        # Vigencia: sigue vivo lo que aún no ha terminado.
        #   · cine: la cartelera se reemplaza entera cada pasada, siempre vale
        #   · con fecha de fin: vale hasta que llega
        #   · sólo con fecha de inicio: vale si no ha pasado
        #   · sin fechas: se muestra, es lo único que podemos hacer con ello
        if sec == "cine":
            vigente = True
        elif fin_f:
            vigente = fin_f >= hoy
        elif ini_f:
            vigente = ini_f >= hoy
        else:
            vigente = True
        if not vigente:
            continue

        eventos.append({
            "title": r["title"],
            "section": sec,
            "plano": PLANO_DE[sec],
            "venue": r["venue"],
            "source": r["source"],
            "date_start": ini_f,
            "date_end": fin_f,
            "description": r["description"],
            "url": r["url"],
            "first_seen": r["first_seen"],
            "is_new": r["first_seen"] == latest,
            "kids": bool(r["kids_friendly"]),
            "selecto": bool(r["selective"]),
        })

    return eventos, latest


def generate():
    eventos, latest = load_events()

    DOCS_DIR.mkdir(exist_ok=True)
    shutil.copy(STATIC_DIR / "style.css", DOCS_DIR / "style.css")
    if (STATIC_DIR / "fonts").is_dir():
        shutil.copytree(STATIC_DIR / "fonts", DOCS_DIR / "fonts", dirs_exist_ok=True)

    def embed(obj):
        # `</script>` dentro de una cadena cerraría el bloque antes de tiempo.
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    chips = "".join(
        f'<button class="chip{" on" if i == 0 else ""}" data-plano="{clave}">{rotulo}</button>'
        for i, (clave, rotulo, _) in enumerate(PLANOS)
    )
    anio = str(date.today().year)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>CulturalMe — Madrid</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#000000">
<meta name="description" content="Agenda cultural de Madrid: exposiciones, cine, teatro y charlas.">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<link rel="stylesheet" href="style.css">
</head>
<body>

<header id="cabecera">
  <h1>CulturalMe</h1>
  <p class="lema">Madrid</p>

  <nav class="chips" id="planos">{chips}</nav>
  <nav class="chips" id="modos">
    <button class="chip" data-modo="selecto">selecto</button>
    <button class="chip" data-modo="kids">niños</button>
  </nav>
  <nav class="chips" id="secciones"></nav>

  <nav class="orden" id="orden">
    <button class="on" data-orden="fecha">por fecha</button>
    <button data-orden="nuevo">más nuevo</button>
  </nav>
</header>

<main id="lista"></main>

<footer><p>Actualizado el {latest}</p></footer>

<script>
const EVENTOS = {embed(eventos)};
const PLANOS = {embed([[c, r, secs] for c, r, secs in PLANOS])};
const LABELS = {embed(LABELS)};
const ANIO = '{anio}';
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
function cuando(e) {{
  const a = e.date_start, b = e.date_end;
  // Una muestra de "1 dic 2025 – 31 oct 2026" sin años se lee al revés.
  const otro = [a, b].filter(Boolean).some(s => s.slice(0,4) !== ANIO);
  if (a && b) return a === b ? dmy(a, otro) : dmy(a, otro) + ' – ' + dmy(b, otro);
  if (a) return dmy(a, otro);
  if (b) return 'hasta el ' + dmy(b, otro);
  return '';
}}

// El orden por defecto es la fecha de fin: lo que cierra antes, arriba.
function fin(e) {{ return e.date_end || e.date_start || '9999-12-31'; }}

let plano = PLANOS[0][0];
let seccion = 'todo';
let orden = 'fecha';
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
  const meta = [donde, cuando(e)].filter(Boolean).map(esc).join(' · ');
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

function pintar() {{
  const secs = PLANOS.find(p => p[0] === plano)[2];
  const enPlano = EVENTOS.filter(e => e.plano === plano);

  // Los chips de sección sólo tienen sentido donde la pestaña agrupa varias.
  const presentes = secs.filter(s => enPlano.some(e => e.section === s));
  if (!presentes.includes(seccion)) seccion = 'todo';
  document.getElementById('secciones').innerHTML = presentes.length > 1
    ? ['todo', ...presentes].map(s =>
        '<button class="chip' + (s === seccion ? ' on' : '') + '" data-sec="' + s + '">'
        + (s === 'todo' ? 'todo' : esc(LABELS[s]).toLowerCase()) + '</button>').join('')
    : '';

  let ev = enPlano.filter(e =>
    (seccion === 'todo' || e.section === seccion)
    && (!modos.kids || e.kids)
    && (!modos.selecto || e.selecto));

  ev.sort((a, b) => {{
    // Lo ya visto se va al final sin desaparecer.
    const va = vistos.has(clave(a)) ? 1 : 0, vb = vistos.has(clave(b)) ? 1 : 0;
    if (va !== vb) return va - vb;
    if (orden === 'nuevo') {{
      const c = (b.first_seen || '').localeCompare(a.first_seen || '');
      if (c) return c;
    }}
    return fin(a).localeCompare(fin(b)) || a.title.localeCompare(b.title, 'es');
  }});

  document.getElementById('lista').innerHTML = ev.length
    ? ev.map(tarjeta).join('')
    : '<p class="vacio">Nada con estos filtros.</p>';

  document.querySelectorAll('#planos .chip').forEach(c =>
    c.classList.toggle('on', c.dataset.plano === plano));
  document.querySelectorAll('#modos .chip').forEach(c =>
    c.classList.toggle('on', !!modos[c.dataset.modo]));
  document.querySelectorAll('#orden button').forEach(b =>
    b.classList.toggle('on', b.dataset.orden === orden));
}}

document.addEventListener('click', ev => {{
  const c = ev.target.closest('button');
  if (!c) return;
  if (c.dataset.plano) {{ plano = c.dataset.plano; seccion = 'todo'; pintar(); }}
  else if (c.dataset.orden) {{ orden = c.dataset.orden; pintar(); }}
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
    reparto = ", ".join(
        f"{rotulo} {sum(1 for e in eventos if e['plano'] == clave)}"
        for clave, rotulo, _ in PLANOS
    )
    print(f"docs/index.html — {reparto} · datos del {latest}")


if __name__ == "__main__":
    generate()
