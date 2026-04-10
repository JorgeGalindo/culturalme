# CulturalMe — Madrid

Agenda cultural personalizada para Madrid. Se actualiza cada viernes via GitHub Actions y se sirve como sitio estatico en GitHub Pages. Sin servidor.

**https://jorgegalindo.github.io/culturalme/**

## Que es

Un unico lugar para ver que hay en Madrid esta semana en museos, conciertos, galerias, charlas, cine y teatro. Solo muestra conciertos de artistas que me gustan (lista de ~4000 artistas de mi proyecto musicalme).

## Como funciona

```
viernes 7AM CET
  GitHub Actions ejecuta pipeline.py
    → scrapers descargan HTML de ~50 fuentes
    → Claude Haiku 4.5 extrae eventos del texto
    → SQLite se actualiza (upsert, dedup)
  GitHub Actions ejecuta generate.py
    → lee SQLite, genera docs/index.html estatico
    → commit + push
  GitHub Pages se actualiza automaticamente
```

No hay servidor. No hay Flask en produccion. Todo es un HTML estatico con JS vanilla para los filtros.

## Fuentes

### Museos y exposiciones (17)
Prado, Reina Sofia, Thyssen, Matadero, F. Telefonica, La Casa Encendida, F. Mapfre, Canal de Isabel II, Conde Duque, CBA, F. ICO, Real Academia de San Fernando, CentroCentro, Alcala 31, F. Masaveu, Artes Decorativas, Cerralbo, F. Juan March

### Conciertos (12 salas + Bandsintown)
**Bandsintown** como agregador principal (filtra contra lista de 4000 artistas).
Salas: El Sol, Moby Dick, La Riviera, Sala But, Clamores, Siroco, Independance, Shoko, Cafe Berlin, Galileo Galilei, Teatro Barcelo.
Deduplicacion por artista + fecha.

### Galerias (20 + ferias)
Elvira Gonzalez, Helga de Alvear, Juana de Aizpuru, Travesia Cuatro, Moises Perez de Albeniz, Casa Sin Fin, NoguerasBlanchard, Parra & Romero, F2, Heinrich Ehrhardt, Elba Benitez, Cayon, Sabrina Amrani, Marlborough, Max Estrella, Jose de la Mano, Albarran Bourdais, Leandro Navarro, Garcia Galeria, Fernandez-Braso.
Ferias: ARCO, Art Madrid, JustMAD, Estampa, Gallery Weekend.

### Charlas (8)
F. Rafael del Pino, F. Ramon Areces, F. Juan March, Ateneo, CBA, Casa Arabe, IE Foundation, F. Telefonica.

### Cine
Cines Renoir (todas las sedes Madrid). Director y etiquetas (ESTRENO, OSCAR...).

### Teatro (8)
Teatros del Canal, Teatro Espanol, Teatro de la Abadia, Naves del Espanol (Matadero), Teatro del Barrio, Nave 73, Sala Cuarta Pared, Sala Triangulo.

## Stack

- **Python 3.13** — scrapers + generador estatico
- **Claude Haiku 4.5** via API — extraccion de eventos del HTML (prompts especificos por seccion)
- **SQLite** — almacenamiento
- **GitHub Actions** — cron semanal
- **GitHub Pages** — hosting (gratis)
- **Fraunces** — tipografia
- Paleta pastel rainbow

## Estructura

```
culturalme/
├── scrapers/
│   ├── llm.py          # Modulo compartido: fetch, clean HTML, call Haiku
│   ├── museos.py       # 17 fuentes, modo LLM
│   ├── conciertos.py   # Bandsintown + 11 salas, filtro artistas, dedup
│   ├── galerias.py     # 20 galerias + ferias, modo LLM
│   ├── charlas.py      # 8 fuentes, modo LLM
│   ├── cine.py         # Renoir, prompt especifico para cartelera
│   └── teatro.py       # 8 teatros, modo LLM
├── pipeline.py         # Orquesta scrapers, upsert en SQLite
├── generate.py         # Lee SQLite, genera docs/index.html estatico
├── data/
│   ├── culturalme.db   # SQLite con todos los eventos
│   └── artists.json    # 4000 artistas de musicalme (filtro conciertos)
├── docs/
│   ├── index.html      # Sitio estatico generado (GitHub Pages)
│   └── style.css
├── static/
│   └── style.css       # CSS fuente (se copia a docs/)
├── .github/workflows/
│   └── update.yml      # Cron viernes 7AM CET
├── requirements.txt
└── runtime.txt
```

## Coste

~$2-4/mes en API de Anthropic (Haiku 4.5, ~50 llamadas/semana). Hosting gratis.

## Setup local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python pipeline.py    # scrape todo
python generate.py    # genera docs/index.html
open docs/index.html  # ver resultado
```

## Pendiente

- Playwright para webs JS-rendered: CaixaForum, Lazaro Galdiano, Cine Embajadores, DICE
- CDN y CNTC cuando arreglen sus dominios
- Mas galerias (muchas son muy minimalistas y dan 0)
