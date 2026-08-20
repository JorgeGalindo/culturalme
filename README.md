# CulturalMe — Madrid

La agenda cultural de **esta semana** en Madrid. Se actualiza sola cada viernes por la mañana y se sirve
como sitio estático en GitHub Pages. Sin servidor.

**https://jorgegalindo.github.io/culturalme/**

## Qué es

Dos planos, porque son dos preguntas distintas:

- **Esta semana** — lo que tiene día: charlas, teatro y la cartelera de cine. Agrupado por día, con un
  bloque "en cartel" para lo que ya está abierto y sigue toda la semana.
- **Exposiciones** — museos y galerías, que duran meses. Ordenadas por **fecha de cierre ascendente**:
  arriba lo que se acaba antes, que es lo accionable.

Encima, dos modos que filtran cualquiera de los planos: **⭐ Selecto** (encaja con `data/jorge_taste.md`)
y **👶 Niños** (encaja con `data/kids_taste.md`). Ambos los etiqueta el LLM tras cada pasada.

## Cómo funciona

```
viernes 7:00 CET
  GitHub Actions ejecuta pipeline.py
    → scrapers descargan HTML de 39 fuentes
    → Claude Haiku 4.5 extrae eventos del texto
    → SQLite se actualiza (upsert por título+sede, purga lo que lleva 60 días sin verse)
    → el tagger marca kids_friendly y selective
  GitHub Actions ejecuta generate.py
    → lee SQLite, genera docs/index.html estático
    → commit + push
  GitHub Pages se actualiza automáticamente
```

**Nada se publica si no se ha visto en la última pasada.** Que una fuente deje de listar un evento es la
señal de que el evento se acabó. Sin esa regla el sitio acumulaba fantasmas: llegó a publicar 106 eventos
(el 44% de la portada) que llevaban meses sin aparecer en ninguna web.

## Fuentes (39)

**Museos y espacios (16)** — CentroCentro, Reina Sofía, Real Academia de San Fernando, Matadero,
Thyssen, F. Telefónica, CBA, Canal de Isabel II, Lázaro Galdiano, F. Mapfre, Conde Duque, F. Masaveu,
Alcalá 31, Artes Decorativas, Cerralbo, F. ICO.

**Galerías (9)** — Travesía Cuatro, NoguerasBlanchard, Max Estrella, Marlborough, José de la Mano,
F2, Heinrich Ehrhardt, Elba Benítez, Sabrina Amrani.

**Charlas (4)** — F. Ramón Areces, F. Rafael del Pino, CBA, F. Telefónica.

**Teatro (8)** — Teatros del Canal, Calderón, Nave 73, Teatro del Barrio, Bellas Artes, La Abadía,
Teatro Español, Cuarta Pared.

**Cine (2)** — Cines Renoir y Cines Embajadores.

El criterio para estar en la lista es haber producido algo en las últimas cuatro pasadas. En agosto de 2026
se pasó de 76 fuentes a 39: 26 no habían producido **nunca** un solo evento (el Prado da 403, cinco dominios
de galería ya no resuelven DNS, las cinco ferias nunca dieron nada) y las demás llevaban meses en cero.
Cada fuente muerta costaba una llamada al modelo y hasta 15s de reintentos.

## Decisiones que no son obvias

- **`event_id` = `source|title|venue`, sin fecha.** La fecha es el dato que el LLM extrae peor; con ella en
  la clave, cada lectura errónea creaba una fila nueva (el mismo montaje llegó a estar cuatro veces con
  cuatro años distintos). Ahora las fechas se actualizan encima de la fila que ya existe.
- **Las fechas se validan en Python, no se le confían al modelo.** La fecha de hoy va en el prompt, y luego
  se exige `YYYY-MM-DD` dentro de una ventana de `[hoy−2 años, hoy+18 meses]`. Un `date_end` anterior al
  `date_start` se interpreta como cruce de año ("del 9 de julio al 10 de enero") y salta al año siguiente.
  Una fecha inválida se descarta sola; el evento sobrevive sin ella.
- **Ante error de certificado se reintenta sin verificar.** Varias sedes públicas
  (`culturaydeporte.gob.es`, `fundacionico.es`, `cinesembajadores.es`) sirven cadenas incompletas y
  llevaban meses caídas por eso. Sólo leemos HTML público y no mandamos credenciales.
- **Todo lo que entra en el DOM pasa por `esc()`.** El contenido lo escribe un LLM sobre HTML ajeno.
- **No hay conciertos.** Los hubo: 18 eventos en cuatro meses con 4.000 artistas en lista, y 4 minutos de
  cada pasada para encontrar uno. Bandsintown devuelve 403. Si vuelven, será por API estructurada
  (Songkick, Ticketmaster Discovery), no por LLM.

## Estructura

```
culturalme/
├── scrapers/
│   ├── llm.py          # fetch (con fallback TLS), limpieza, prompts, saneado de fechas
│   ├── museos.py  galerias.py  charlas.py  cine.py  teatro.py
│   └── tagger.py       # kids_friendly + selective contra los manifiestos
├── pipeline.py         # orquesta scrapers, upsert y purga en SQLite
├── generate.py         # lee SQLite, genera docs/index.html
├── data/
│   ├── culturalme.db   # SQLite
│   ├── jorge_taste.md  # manifiesto del modo Selecto
│   └── kids_taste.md   # manifiesto del modo Niños
├── static/
│   ├── style.css       # fuente (se copia a docs/)
│   └── fonts/          # Poiret One + EB Garamond, autoalojadas
├── docs/               # lo que publica GitHub Pages
└── .github/workflows/update.yml
```

## Coste

~$1-2 al mes en API de Anthropic (Haiku 4.5, 39 llamadas por semana más el tagger). Hosting gratis.

## Setup local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python pipeline.py    # scrape + tag
python generate.py    # genera docs/index.html
open docs/index.html
```

## Setup CI

El cron necesita el secret `ANTHROPIC_API_KEY` (Settings → Secrets and variables → Actions) y permiso de
escritura para las Actions, que ya está declarado en el workflow.

## Pendiente

- El **Prado** da 403 en todas sus rutas y el **Thyssen** y once webs más son SPAs que sirven JS: harían
  falta Playwright y un runner distinto. Es su propio trabajo.
- Seis de las 39 fuentes devuelven menos de 600 caracteres de texto y sólo producen de vez en cuando
  (Teatro Español, José de la Mano, Cuarta Pared, Sabrina Amrani, Masaveu, F. Telefónica/agenda).
  Están a prueba: si siguen en cero, fuera.
