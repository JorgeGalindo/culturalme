# CulturalMe — Plan de desarrollo

App de agenda cultural personalizada para Madrid.
Se actualiza 1x/semana (viernes AM) via GitHub Actions.
Frontend estático servido en Render. Estética heredada de readerme.

---

## Arquitectura general

```
culturalme/
├── scrapers/           # Un módulo por fuente o grupo de fuentes
│   ├── museos.py
│   ├── conciertos.py
│   ├── galerias.py
│   ├── charlas.py
│   ├── cine.py
│   └── teatro.py
├── pipeline.py         # Orquesta todos los scrapers, deduplica, escribe DB
├── data/
│   ├── culturalme.db   # SQLite — toda la info
│   └── artists.json    # Copia de la lista de artistas de musicalme (filtro conciertos)
├── app.py              # Flask — sirve el frontend
├── templates/
│   └── index.html      # Jinja2 — una sola página con secciones
├── static/
│   └── style.css       # Estilo readerme (Roboto Mono, warm off-white, cards, pills)
├── .github/
│   └── workflows/
│       └── update.yml  # Cron: viernes 7:00 AM CET → ejecuta pipeline.py, commit, push
├── requirements.txt
├── Procfile            # gunicorn app:app
└── PLAN.md             # Este archivo
```

### Stack

- **Python 3.13** + **Flask** + **Jinja2** (igual que readerme)
- **SQLite** como DB (fichero en repo, se actualiza via commit semanal)
- **httpx** para descargar HTML de las fuentes
- **BeautifulSoup4** para scraping clásico (fuentes estables/estructuradas)
- **Anthropic SDK** (Claude Haiku 4.5) para extracción LLM (fuentes heterogéneas/frágiles)
- **GitHub Actions** para el cron del viernes
- **Render** para servir (static site o web service con gunicorn)
- **Sin framework JS** — vanilla JS, vanilla CSS, Roboto Mono

### Estrategia de extracción: híbrida (scraping clásico + LLM)

No todas las fuentes se tratan igual. Dos modos:

**Modo LLM** (Claude Haiku 4.5 via API): para fuentes donde el HTML es heterogéneo,
cambiante, o simplemente demasiadas webs distintas como para mantener un parser por cada una.
Se descarga el HTML con httpx y se le pasa a Haiku con un prompt genérico tipo
"extrae los eventos culturales de esta página y devuélvelos como JSON".
Un solo prompt cubre decenas de webs distintas sin código específico por fuente.

**Modo scraping clásico** (BeautifulSoup): para fuentes con estructura estable, limpia,
y que cambian poco — o donde hay una API/JSON disponible.

| Sección | Modo | Razón |
|---|---|---|
| Museos (20 webs) | **LLM** | 20 HTMLs distintos, cambian con rediseños. Un prompt genérico las cubre todas |
| Galerías (20 webs) | **LLM** | Mismo caso: muchas webs heterogéneas |
| Conciertos — salas | **LLM** | Webs de salas varían mucho |
| Conciertos — agregadores | **Scraping / API** | Songkick, Bandsintown, DICE tienen estructura estable o APIs |
| Charlas (5 fundaciones) | **Scraping** | Webs institucionales estables, HTML limpio, cambian poco |
| Teatro (5 teatros) | **Scraping** | Webs públicas bien estructuradas, estables |
| Cine (Renoir + Embajadores) | **Scraping** | Carteleras con estructura repetitiva y predecible |

**Coste estimado del modo LLM** (~45 llamadas/semana a Haiku 4.5):
- ~2-5K tokens input + ~500 tokens output por llamada
- ~$0.01-0.02 por llamada → **~$0.50-1.00/semana → ~$2-4/mes**

**Prompt genérico para extracción LLM** (se reutiliza para todas las fuentes LLM):

```
Extrae todos los eventos culturales visibles en esta página web.
Devuelve un JSON array. Cada objeto debe tener:
- "title": título del evento/exposición/obra
- "date_start": fecha de inicio (YYYY-MM-DD o null)
- "date_end": fecha de fin (YYYY-MM-DD o null)
- "description": descripción corta (1-2 frases, o null)
- "url": URL del evento si aparece (o null)
- "image_url": URL de imagen si aparece (o null)

Si no hay eventos visibles, devuelve [].
Solo JSON, sin explicaciones.

HTML de la página:
{html}
```

**Implementación en el pipeline**:

```python
import anthropic
import httpx
from bs4 import BeautifulSoup
import json

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY en env / GitHub secret

def extract_via_llm(url: str, source_name: str, section: str) -> list[dict]:
    """Descarga HTML y usa Haiku para extraer eventos."""
    html = httpx.get(url, follow_redirects=True, timeout=30).text
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(html=html)}]
    )
    events = json.loads(response.content[0].text)
    # Añadir metadatos
    for e in events:
        e["source"] = source_name
        e["section"] = section
    return events

def extract_via_scraping(url: str, parser_fn, source_name: str, section: str) -> list[dict]:
    """Descarga HTML y usa un parser BeautifulSoup específico."""
    html = httpx.get(url, follow_redirects=True, timeout=30).text
    soup = BeautifulSoup(html, "lxml")
    events = parser_fn(soup)
    for e in events:
        e["source"] = source_name
        e["section"] = section
    return events
```

### Modelo de datos (SQLite)

```sql
CREATE TABLE events (
    id TEXT PRIMARY KEY,           -- hash de (source + title + venue + date_start)
    section TEXT NOT NULL,         -- 'museo', 'concierto', 'galeria', 'charla', 'cine', 'teatro'
    title TEXT NOT NULL,
    venue TEXT,
    date_start DATE,              -- fecha de inicio o de la función
    date_end DATE,                -- fecha de fin (expos, obras en cartel)
    description TEXT,
    url TEXT,                     -- link a la página fuente
    source TEXT,                  -- nombre de la fuente (ej. "Museo del Prado")
    image_url TEXT,               -- opcional, si la sacamos
    first_seen DATE NOT NULL,     -- fecha en la que el scraper lo detectó por primera vez
    last_seen DATE NOT NULL,      -- última pasada en la que seguía activo
    artist_match TEXT             -- solo conciertos: nombre del artista si matchea con tu lista
);
```

### Lógica de ordenación (frontend)

- Por defecto: **más nuevo primero** (ordenar por `first_seen` DESC — lo que no estaba en la pasada anterior sube)
- Alternativa: **por fecha** (ordenar por `date_start` ASC, o por `date_end` ASC si la tiene)
- Los eventos pasados NO se borran, simplemente quedan más abajo

---

## Fase 1 — Esqueleto del proyecto

1. Crear estructura de carpetas y ficheros vacíos
2. Crear `requirements.txt` (flask, httpx, beautifulsoup4, gunicorn, lxml, anthropic)
3. Crear `app.py` con Flask básico que sirve index.html con datos de SQLite
4. Crear `templates/index.html` con layout readerme (secciones, cards, filtros)
5. Crear `static/style.css` adaptado de readerme (colores por sección cultural)
6. Crear `pipeline.py` con estructura base (llama a cada scraper, escribe DB)
7. Crear `data/culturalme.db` con el schema
8. Copiar lista de artistas de musicalme para el filtro de conciertos

---

## Fase 2 — Scrapers (uno por uno, en este orden)

### 2.1 Museos y exposiciones

Fuentes (20):

| Museo / Espacio | URL probable de programación |
|---|---|
| Museo del Prado | museodelprado.es/actualidad/exposiciones |
| Museo Reina Sofía | museoreinasofia.es/exposiciones |
| Museo Thyssen | museothyssen.org/exposiciones |
| Matadero Madrid | mataderomadrid.org/programacion |
| CaixaForum Madrid | caixaforum.org/es/madrid |
| Fundación Telefónica | fundaciontelefonica.com/exposiciones |
| La Casa Encendida | lacasaencendida.es/exposiciones |
| Fundación Mapfre | fundacionmapfre.org/exposiciones |
| Sala Canal de Isabel II | comunidad.madrid/actividades (filtrar) |
| Conde Duque | condeduquemadrid.es/programacion |
| Imprenta Municipal | madrid.es/imprenta (verificar) |
| CBA (Círculo de Bellas Artes) | circulobellasartes.com/exposiciones |
| Fundación ICO | fundacionico.es/exposiciones |
| Real Academia de San Fernando | realacademiabellasartessanfernando.com |
| CentroCentro | centrocentro.org/exposiciones |
| Alcalá 31 | comunidad.madrid/actividades (filtrar sala Alcalá 31) |
| Fundación María Cristina Masaveu | fundacionmasaveu.com |
| Museo de Artes Decorativas | culturaydeporte.gob.es/mnad |
| Museo Cerralbo | culturaydeporte.gob.es/mcerralbo |
| Museo Lázaro Galdiano | flg.es/exposiciones |

**Estrategia**: **modo LLM**. 20 webs con HTML muy distinto entre sí — no tiene sentido
mantener 20 parsers. Un solo prompt genérico de Haiku extrae los eventos de todas.

**Paso a paso**:
1. Recopilar y verificar las URLs reales de programación/exposiciones de cada museo
2. En `scrapers/museos.py`: lista de dicts `{name, url}` para cada museo
3. Para cada museo: `extract_via_llm(url, name, "museo")`
4. Testear con 2-3 museos, verificar que el JSON sale bien
5. Escalar a los 20, ajustar prompt si alguno da problemas
6. Integrar en pipeline

---

### 2.2 Conciertos (solo artistas que te gustan)

Fuentes:

| Fuente | Tipo | URL |
|---|---|---|
| Songkick | Agregador + API | songkick.com |
| Bandsintown | Agregador + API | bandsintown.com |
| DICE | Agregador | dice.fm/madrid |
| Sala El Sol | Sala | salaelsol.com |
| Moby Dick Club | Sala | mobydickclub.com |
| WiZink Center | Sala | wizinkcenter.es |

**Filtro de artistas**: se carga `data/artists.json` (extraído de `/musicalme/data/artist-reviews.json` — 4.011 artistas). Solo se guardan en DB conciertos cuyo artista haga match (fuzzy) con la lista.

**Estrategia**: **híbrida**.
- Agregadores (Songkick, Bandsintown, DICE): **scraping clásico / API** — datos estructurados
- Salas individuales (El Sol, Moby Dick, WiZink): **modo LLM** — webs heterogéneas
- Match fuzzy: normalizar nombres (lowercase, sin acentos, sin "the") y comparar

**Paso a paso**:
1. Extraer lista de artistas de musicalme → `data/artists.json`
2. Investigar APIs de Songkick y Bandsintown (¿siguen abiertas?)
3. Si hay API: buscar por localización Madrid → todos los conciertos → filtrar contra lista
4. DICE: scraping de dice.fm/madrid (suele tener estructura limpia)
5. Salas individuales: `extract_via_llm()` para cada sala
6. Fuzzy match de todo contra lista de artistas
7. Solo guardar los que matcheen

---

### 2.3 Galerías de arte

Fuentes: las 20 galerías más relevantes de Madrid + ferias.

**Galerías** (top 20 — lista inicial, ajustable):

Elvira González, Helga de Alvear, Juana de Aizpuru, Travesía Cuatro,
Moisés Pérez de Albéniz, Casa Sin Fin, NoguerasBlanchard (Madrid),
Parra & Romero, F2 Galería, Heinrich Ehrhardt, Elba Benítez,
Galería Cayón, Sabrina Amrani, Galería Marlborough, Max Estrella,
José de la Mano, Albarrán Bourdais, Galería Leandro Navarro,
García Galería, Galería Fernández-Braso

**Ferias gordas** a monitorizar:
- **ARCO** (febrero)
- **Art Madrid** (febrero)
- **JustMAD** (febrero)
- **Estampa** (otoño)
- **Gallery Weekend Madrid** (septiembre)

**Estrategia**: **modo LLM**. 20 galerías con webs totalmente distintas (WordPress, custom,
Squarespace...). Mismo caso que museos: un prompt genérico cubre todas.
Para ferias: fechas hardcodeadas + comprobación de web oficial con LLM.

**Paso a paso**:
1. Recopilar y verificar URLs de cada galería (página de expo actual)
2. En `scrapers/galerias.py`: lista de dicts `{name, url}` para cada galería
3. Para cada galería: `extract_via_llm(url, name, "galeria")`
4. Ferias: lista hardcodeada de fechas aproximadas + URL oficial de cada feria
5. Si estamos cerca de las fechas, `extract_via_llm()` sobre la web de la feria
6. Integrar en pipeline

---

### 2.4 Charlas y conferencias

Fuentes (5):

| Institución | URL |
|---|---|
| Fundación Rafael del Pino | frdelpino.es/actividades |
| Fundación Ramón Areces | fundacionareces.es/actividades |
| Fundación Juan March | march.es/actividades |
| Ateneo de Madrid | ateneodemadrid.com/actividades |
| CBA (Círculo de Bellas Artes) | circulobellasartes.com/actividades |

**Estrategia**: **scraping clásico**. Son solo 5 webs institucionales, con estructura
estable y limpia. Merece la pena escribir un parser por cada una — durarán.

**Paso a paso**:
1. Inspeccionar cada web, identificar selectores CSS
2. Escribir parser BeautifulSoup por cada una en `scrapers/charlas.py`
3. Extraer: título, fecha, ponente/tema, link
4. Testear cada parser
5. Integrar en pipeline

---

### 2.5 Cine (cartelera actual)

Fuentes (2 cadenas, varias sedes):

| Cine | Sedes en Madrid |
|---|---|
| Cines Renoir | Princesa, Retiro, Plaza de España, Floridablanca |
| Cine Embajadores | Embajadores |

**Estrategia**: **scraping clásico**. Las carteleras tienen estructura muy repetitiva
(lista de películas con horarios). Solo 2 fuentes. Fácil de mantener.
- Aquí NO se acumula histórico útil — lo relevante es qué hay AHORA
- Cada viernes se borran las películas anteriores y se refresca la cartelera completa

**Paso a paso**:
1. Inspeccionar webs de Renoir y Embajadores, identificar selectores
2. Parser BeautifulSoup por cada una en `scrapers/cine.py`
3. Extraer: película, sala/sede, horarios si los hay, link
4. Integrar en pipeline (con lógica de reemplazo total, no acumulativa)

---

### 2.6 Teatro

Fuentes (5):

| Teatro | URL |
|---|---|
| Centro Dramático Nacional | cdn.mcu.es/programacion |
| Teatros del Canal | teatroscanal.com/programacion |
| Teatro María Guerrero | cdn.mcu.es (es sede del CDN) |
| Teatro Español | teatroespanol.es/programacion |
| Teatro de la Abadía | teatroabadia.com/programacion |

**Nota**: el María Guerrero es una de las sedes del CDN, así que puede que compartan web.

**Estrategia**: **scraping clásico**. Son teatros públicos con webs bien hechas y estables.
Solo 4-5 fuentes (María Guerrero comparte web con CDN). Parsers duraderos.

**Paso a paso**:
1. Inspeccionar cada web, identificar selectores CSS
2. Parser BeautifulSoup por cada uno en `scrapers/teatro.py`
3. Extraer: título obra, fechas (rango), sala, link
4. Testear cada parser
5. Integrar en pipeline

---

## Fase 3 — Pipeline y GitHub Actions

1. `pipeline.py`:
   - Carga artistas de `data/artists.json`
   - Ejecuta cada scraper en orden
   - Para cada evento nuevo: genera `id` (hash), marca `first_seen = hoy`
   - Para cada evento existente: actualiza `last_seen = hoy`
   - Escribe todo en `data/culturalme.db`
   - Log de errores por fuente (no rompe si una fuente falla)

2. `.github/workflows/update.yml`:
   ```yaml
   name: Weekly update
   on:
     schedule:
       - cron: '0 5 * * 5'  # Viernes 05:00 UTC = 07:00 CET
     workflow_dispatch: {}    # Poder lanzarlo a mano
   jobs:
     update:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: '3.13'
         - run: pip install -r requirements.txt
         - run: python pipeline.py
           env:
             ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
         - run: |
             git config user.name "culturalme-bot"
             git config user.email "bot@culturalme"
             git add data/culturalme.db
             git diff --cached --quiet || git commit -m "update $(date +%Y-%m-%d)"
             git push
   ```

3. Render detecta el push y redeploya automáticamente.

---

## Fase 4 — Frontend

Heredar estética de readerme:

- **Flask + Jinja2**, sin framework JS
- **Roboto Mono** en todo
- **Fondo**: `#FAFAF7` (warm off-white)
- **Cards**: fondo blanco, border-radius 12px, sombra sutil
- **Max-width**: 720px
- **Pills/tags** por sección con color propio:
  - Museos: verde (como readerme default)
  - Conciertos: morado/violeta
  - Galerías: azul oscuro
  - Charlas: ocre/dorado
  - Cine: rojo oscuro
  - Teatro: granate
- **Dark mode** via `prefers-color-scheme`
- **Cada card**: título, venue, fechas, badge de sección, link a fuente
- **Filtros**: por sección (pills arriba), ordenación (nuevo / fecha)
- **Badge "NUEVO"** en eventos con `first_seen = última pasada`

### Layout de index.html

```
[Header: CulturalMe — Madrid]
[Filtros: Todos | Museos | Conciertos | Galerías | Charlas | Cine | Teatro]
[Orden: Más nuevo | Por fecha]

[Cards de eventos, agrupadas o mezcladas según filtro activo]
  - Cada card:
    [Badge sección]  [Badge NUEVO si aplica]
    Título del evento
    Venue — Fechas
    [→ Ver en fuente]  (link externo)

[Footer: Última actualización: 2026-04-10]
```

---

## Fase 5 — Deploy y pulido

1. Crear repo en GitHub
2. Configurar Render (web service, auto-deploy desde main)
3. Primer run manual del pipeline
4. Verificar que el cron del viernes funciona
5. Ajustar scrapers que fallen (las webs cambian)
6. Pulir CSS responsive (iPad-first como readerme)

---

## Orden de trabajo recomendado

| Paso | Qué | Depende de |
|---|---|---|
| 1 | Esqueleto (estructura, DB, Flask vacío) | Nada |
| 2 | Frontend base (HTML/CSS con datos fake) | Paso 1 |
| 3 | Scraper museos (el más numeroso) | Paso 1 |
| 4 | Scraper charlas (el más sencillo) | Paso 1 |
| 5 | Scraper teatro | Paso 1 |
| 6 | Scraper cine | Paso 1 |
| 7 | Scraper conciertos (necesita filtro artistas) | Paso 1 |
| 8 | Scraper galerías (el más tedioso: 20 webs distintas) | Paso 1 |
| 9 | Pipeline completo | Pasos 3-8 |
| 10 | GitHub Actions | Paso 9 |
| 11 | Deploy Render | Paso 2 + 10 |
| 12 | Pulido y ajustes | Todo |

---

## Notas

- Cada scraper debe ser robusto: si una web falla, log + skip, no romper el pipeline
- Las URLs de fuentes hay que verificarlas una a una antes de escribir el scraper
- Algunas webs pueden tener protección anti-bot — si pasa, evaluar alternativas (APIs, RSS)
- La lista de galerías top 20 es orientativa — se puede ajustar
- `artists.json` se sincroniza manualmente desde musicalme cuando cambie
- `ANTHROPIC_API_KEY` debe estar como secret en el repo de GitHub (para GitHub Actions) y como variable de entorno en local (para desarrollo)
- Si Haiku da respuestas inconsistentes para alguna fuente concreta, se puede: (a) ajustar el prompt con instrucciones específicas para esa fuente, o (b) degradar esa fuente a scraping clásico
- Coste total estimado del pipeline LLM: **~$2-4/mes** (Haiku 4.5, ~45 llamadas/semana)
