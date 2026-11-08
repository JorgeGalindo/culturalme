"""
CulturalMe — genera el sitio estático en docs/ (lo sirve Vercel).

Arriba, la portada de la semana (curate.py): los planes que Claude elige con el
manifiesto de Jorge, cada uno con su por qué, y los de ir con los niños.
Debajo, las exposiciones que cierran en las dos próximas semanas. Y al final
todo lo demás para buscar: cinco pestañas por tipo, orden por fecha de cierre.

Lo publicado es lo que vio la última lectura buena de cada fuente
(pipeline.published). La página se genera una vez por semana, así que es el
navegador el que esconde, con la fecha de cada día, lo que ya ha terminado.
"""

import json
import re
import shutil
import sqlite3
from datetime import date
from pathlib import Path

import curate
import pipeline

DOCS_DIR = Path(__file__).parent / "docs"
STATIC_DIR = Path(__file__).parent / "static"

# (clave, rótulo, secciones que agrupa)
PLANOS = [
    ("expos", "exposiciones", ["museo", "galeria"]),
    ("teatro", "teatro", ["teatro"]),
    ("charlas", "charlas", ["charla"]),
    ("musica", "música", ["musica"]),
    ("cine", "cine", ["cine"]),
]
PLANO_DE = {sec: clave for clave, _, secs in PLANOS for sec in secs}

LABELS = {
    "museo": "Museos",
    "galeria": "Galerías",
    "charla": "Charlas",
    "cine": "Cine",
    "teatro": "Teatro",
    "musica": "Música",
}


# Rótulo de una sola pieza, para la línea de arriba de cada plan de la portada.
KICKER = {"museo": "Exposición", "galeria": "Galería", "charla": "Charla", "cine": "Cine",
          "teatro": "Teatro", "musica": "Concierto"}


def tidy_title(title: str, section: str = "") -> str:
    """Las webs que titulan EN MAYÚSCULAS pasan a minúsculas con mayúscula inicial
    (también tras punto, barra vertical o comillas); en música, que son nombres de
    artista, cada palabra con mayúscula. Lo que ya viene mezclado no se toca."""
    letters = [c for c in title if c.isalpha()]
    if len(letters) < 6 or sum(c.isupper() for c in letters) < 0.85 * len(letters):
        return title
    if section == "musica":
        return " ".join(w[:1].upper() + w[1:].lower() for w in title.split(" "))
    out = title.lower()
    return re.sub(r"(^|[.|:«\"]\s*|\s[-–—]\s*)(\w)", lambda m: m.group(1) + m.group(2).upper(), out)


def vigente(sec: str, ini: str | None, fin: str | None, hoy: str) -> bool:
    """Sigue vivo lo que aún no ha terminado.
      · cine: la cartelera es la de la última lectura, siempre vale
      · con fecha de fin: vale hasta que llega
      · exposición sólo con fecha de inicio: vale (no sabemos cuándo cierra; deja
        de publicarse cuando su web deja de listarla)
      · otra cosa sólo con fecha de inicio: vale si no ha pasado
      · sin fechas: se muestra, es lo único que podemos hacer con ello
    La página repite esta misma regla cada día en el navegador."""
    if sec == "cine" or (sec in ("museo", "galeria") and not fin):
        return True
    if fin:
        return fin >= hoy
    if ini:
        return ini >= hoy
    return True


def load_events(con: sqlite3.Connection | None = None):
    hoy = date.today().isoformat()
    own = con is None
    con = con or pipeline.init_db()
    try:
        rows = pipeline.published(con)
        latest = con.execute("SELECT MAX(last_ok) FROM sources").fetchone()[0]
        latest = latest or con.execute("SELECT MAX(last_seen) FROM events").fetchone()[0] or hoy
    finally:
        if own:
            con.close()

    eventos = []
    for r in rows:
        if r["section"] not in PLANO_DE or not vigente(r["section"], r["date_start"], r["date_end"], hoy):
            continue
        eventos.append({
            "id": r["id"],
            "title": tidy_title(r["title"], r["section"]),
            "section": r["section"],
            "plano": PLANO_DE[r["section"]],
            "venue": r["venue"],
            "source": r["source"],
            "date_start": r["date_start"],
            "date_end": r["date_end"],
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
    cura = curate.load() or {"semana": [], "ninos": []}

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
    cura_js = {k: cura.get(k, []) for k in ("semana", "ninos", "desde", "hasta")}

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>CulturalMe — Madrid</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#000000">
<meta name="description" content="Agenda cultural de Madrid: lo que merece la pena esta semana.">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<link rel="stylesheet" href="style.css">
</head>
<body>

<header id="cabecera">
  <h1>CulturalMe</h1>
  <p class="lema" id="lema">Madrid</p>
</header>

<section id="portada">
  <h2 class="bloque" id="t-semana">Esta semana</h2>
  <div id="semana"></div>
  <h2 class="bloque" id="t-ninos">Con los niños</h2>
  <div id="ninos"></div>
  <h2 class="bloque" id="t-pronto">Se acaba pronto</h2>
  <ul id="pronto"></ul>
</section>

<section id="todo">
  <h2 class="bloque">Todo</h2>
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
  <main id="lista"></main>
</section>

<footer><p>Actualizado el {latest}</p></footer>

<script>
const EVENTOS = {embed(eventos)};
const CURA = {embed(cura_js)};
const PLANOS = {embed([[c, r, secs] for c, r, secs in PLANOS])};
const LABELS = {embed(LABELS)};
const KICKER = {embed(KICKER)};
const MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
const DIAS = ['dom','lun','mar','mié','jue','vie','sáb'];
const PRONTO_DIAS = 14;

// La fecha de hoy en Madrid, la del día en que se abre la página (no la de la pasada).
function isoMadrid(d) {{ return d.toLocaleDateString('sv-SE', {{ timeZone: 'Europe/Madrid' }}); }}
const HOY = isoMadrid(new Date());
const ANIO = HOY.slice(0, 4);
const LIMITE_PRONTO = isoMadrid(new Date(Date.now() + PRONTO_DIAS * 864e5));

// Misma regla que vigente() en generate.py, pero con la fecha de hoy.
const EXPO = s => s === 'museo' || s === 'galeria';
function vigente(e) {{
  if (e.section === 'cine' || (EXPO(e.section) && !e.date_end)) return true;
  if (e.date_end) return e.date_end >= HOY;
  if (e.date_start) return e.date_start >= HOY;
  return true;
}}
const VIVOS = EVENTOS.filter(vigente);
const POR_ID = Object.fromEntries(VIVOS.map(e => [e.id, e]));

// Todo el contenido lo escribe un LLM sobre HTML ajeno. Nada entra en el DOM sin pasar por aquí.
function esc(s) {{
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

function partes(iso) {{ return iso.split('-').map(Number); }}
function dm(iso, conAnio) {{
  const [y, m, d] = partes(iso);
  return d + ' ' + MESES[m-1] + (conAnio ? ' ' + y : '');
}}
function dia(iso) {{
  const [y, m, d] = partes(iso);
  return DIAS[new Date(y, m-1, d).getDay()] + ' ' + dm(iso, y !== +ANIO);
}}
function cuando(e) {{
  const a = e.date_start, b = e.date_end;
  const otro = [a, b].filter(Boolean).some(s => s.slice(0,4) !== ANIO);
  if (a && !b && EXPO(e.section)) return a > HOY ? 'desde el ' + dm(a, otro) : '';  // expo sin cierre conocido
  if (a && (!b || a === b)) return dia(a);           // un solo día: con día de la semana
  if (b && (!a || a <= HOY)) return 'hasta el ' + dm(b, otro);  // ya abierta: lo que importa es el cierre
  if (a && b) return dm(a, otro) + ' – ' + dm(b, otro);
  return '';
}}
function cierre(e) {{
  if (e.date_end === HOY) return 'último día hoy';
  const [y, m, d] = partes(e.date_end);
  return 'cierra el ' + DIAS[new Date(y, m-1, d).getDay()] + ' ' + dm(e.date_end, false);
}}
function donde(e) {{ return e.venue || e.source || ''; }}
// La URL también la escribe el LLM: sólo http(s) llega a un href.
function enlace(e, texto) {{
  const href = /^https?:\\/\\//i.test(e.url || '') ? e.url : null;
  return href ? '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(texto) + '</a>' : esc(texto);
}}

// ---------- portada ----------
function destacada(p) {{
  const e = POR_ID[p.id];
  const kicker = [KICKER[e.section], donde(e), cuando(e)].filter(Boolean).map(esc).join(' · ');
  return '<article class="destacada">'
    + '<p class="kicker">' + kicker + '</p>'
    + '<h3>' + enlace(e, e.title) + '</h3>'
    + '<p class="porque">' + esc(p.por_que) + '</p>'
    + '</article>';
}}
function bloque(id, picks) {{
  const vivos = (picks || []).filter(p => POR_ID[p.id]);
  document.getElementById(id).innerHTML = vivos.map(destacada).join('');
  document.getElementById('t-' + id).hidden = !vivos.length;
}}
bloque('semana', CURA.semana);
bloque('ninos', CURA.ninos);

const pronto = VIVOS
  .filter(e => (e.section === 'museo' || e.section === 'galeria') && e.date_end && e.date_end <= LIMITE_PRONTO)
  .sort((a, b) => a.date_end.localeCompare(b.date_end) || (b.selecto - a.selecto));
document.getElementById('pronto').innerHTML = pronto.map(e =>
  '<li' + (e.selecto ? ' class="selecto"' : '') + '>' + enlace(e, e.title)
  + '<span class="meta"> · ' + esc(donde(e)) + ' · ' + esc(cierre(e)) + '</span></li>').join('');
document.getElementById('t-pronto').hidden = !pronto.length;

if (CURA.desde && CURA.hasta) {{
  const desde = HOY > CURA.desde ? HOY : CURA.desde;
  document.getElementById('lema').textContent = 'Madrid · del ' + dm(desde) + ' al ' + dm(CURA.hasta);
}}

// ---------- todo ----------
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
  const meta = [donde(e), cuando(e)].filter(Boolean).map(esc).join(' · ');
  return '<article class="ficha' + (visto ? ' visto' : '') + '">'
    + '<div class="et-fila"><span class="et">' + esc(LABELS[e.section]) + '</span>'
    + (e.is_new ? '<span class="et nuevo">nuevo</span>' : '')
    + (e.selecto ? '<span class="et selecto">selecto</span>' : '') + '</div>'
    + '<h3>' + enlace(e, e.title) + '</h3>'
    + (meta ? '<p class="meta">' + meta + '</p>' : '')
    + (e.description ? '<p class="nota">' + esc(e.description) + '</p>' : '')
    + '<button class="visto" data-k="' + esc(k) + '">' + (visto ? '✓ visto' : 'marcar visto') + '</button>'
    + '</article>';
}}

function pintar() {{
  const secs = PLANOS.find(p => p[0] === plano)[2];
  const enPlano = VIVOS.filter(e => e.plano === plano);

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

  document.querySelectorAll('#planos .chip').forEach(c => {{
    const n = VIVOS.filter(e => e.plano === c.dataset.plano).length;
    c.classList.toggle('on', c.dataset.plano === plano);
    c.hidden = !n;
  }});
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
    print(f"docs/index.html — {reparto} · portada {len(cura.get('semana', []))}+{len(cura.get('ninos', []))}"
          f" · datos del {latest}")


if __name__ == "__main__":
    generate()
