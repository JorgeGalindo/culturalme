# CulturalMe — Madrid

Agenda cultural de Madrid. Se actualiza sola cada viernes por la mañana en el Mac mini y se sirve como
sitio estático en Vercel. Sin servidor y sin API de pago.

**https://culturalme.vercel.app**

## Qué es

Arriba, **la portada de la semana**: entre seis y ocho planes que Claude elige con el manifiesto de gusto
(`data/jorge_taste.md`), cada uno con una frase de por qué, y dos o tres para ir **con los niños**
(`data/kids_taste.md`). Debajo, **se acaba pronto**: las exposiciones que cierran en las dos próximas semanas.

Al final, **todo** lo demás para buscar: cinco pestañas (exposiciones, teatro, charlas, música, cine), orden
por fecha de cierre o por lo más nuevo, y los filtros ⭐ Selecto y 👶 Niños.

La página se genera una vez por semana, pero es el navegador el que esconde cada día lo que ya ha
terminado: una exposición que cierra el martes deja de verse el miércoles.

## Cómo funciona

```
viernes 7:00, Mac mini (launchd com.jorge.culturalme-semanal → semanal.py)
  pipeline.py   descarga cada fuente (httpx, o Chrome headless si pinta con JavaScript),
                Claude extrae los eventos con su enlace propio, SQLite se actualiza
                y el tagger marca selecto y niños
  curate.py     Claude elige la portada de la semana → data/curation.json
  generate.py   docs/index.html
  git push      Vercel publica docs/ en cada push a main
```

Cada llamada al modelo es `claude -p` con la suscripción de Jorge (Sonnet por defecto, `CULTURALME_MODEL`
para cambiarlo), con la salida validada por `--json-schema`. Hasta noviembre de 2026 era Haiku por API en
GitHub Actions; se quitó cuando se acabó el saldo y la pasada del 6 de noviembre falló entera en silencio.

Si la pasada no puede leer nada, si no puede publicar o si falla más de un tercio de las fuentes, llega
un aviso al Mac y un correo. La web se queda como estaba.

## Regla de publicación

**Se publica lo que vio la última lectura buena de cada fuente.** Que una web deje de listar un evento es la
señal de que se acabó; que una web falle una semana no lo es, y sus eventos siguen publicados (la tabla
`sources` guarda la última lectura buena de cada página). Una fuente que de repente devuelve cero eventos
cuando la semana anterior dio alguno cuenta como fallo. Lo que lleva 60 días sin verse se borra.

## Fuentes

En `scrapers/`: `museos.py`, `galerias.py`, `charlas.py` (también las agendas mixtas de fundaciones),
`teatro.py`, `cine.py` y `musica.py`. Cada fuente es una `Fuente(nombre, url, tipo)`; las de tipo `agenda`
mezclan exposiciones, charlas, conciertos y cine, y el modelo clasifica cada actividad en su pestaña.

Añadidas en noviembre de 2026: Fundación Juan March, Casa de América, Fundación BBVA, CaixaForum, Teatro
Fernán Gómez, La Casa Encendida, Museo ABC, Biblioteca Nacional, Cineteca, Cines Verdi y las salas El Sol,
Siroco, La Riviera y Café La Palma.

Fuera por protección antibots, que no se intenta saltar: **Museo del Prado** (403), **Centro Dramático
Nacional**, **Compañía Nacional de Teatro Clásico** y **Teatro de la Zarzuela** (Imperva). La Filmoteca
(Cine Doré) no publica su programación en HTML legible.

## Decisiones que no son obvias

- **Cada evento enlaza a su propia ficha.** El texto que lee el modelo lleva los enlaces marcados como
  `texto ⟨URL⟩`, y la URL que devuelve sólo se acepta si existe en la página; si no, el enlace es la página
  de la fuente. Antes el 90% de los enlaces iban a la agenda general de la sede.
- **`event_id` = `source|title|venue`, sin fecha.** La fecha es el dato que el LLM extrae peor; con ella en
  la clave, cada lectura errónea creaba una fila nueva (el mismo montaje llegó a estar cuatro veces con
  cuatro años distintos). Ahora las fechas se actualizan encima de la fila que ya existe.
- **Cada fuente se guarda en una transacción.** Si una fila falla, se deshace lo de esa fuente. Cada cine
  retira lo que sale de su cartel, pero conserva la fecha de incorporación y las etiquetas de las películas
  que siguen. Si cambia el contenido usado para etiquetar un evento, se vuelve a etiquetar.
- **Las fechas se validan en Python, no se le confían al modelo.** La fecha de hoy va en el prompt, y luego
  se exige `YYYY-MM-DD` dentro de una ventana de `[hoy−2 años, hoy+18 meses]`. Un `date_end` anterior al
  `date_start` se interpreta como cruce de año ("del 9 de julio al 10 de enero") y salta al año siguiente.
  Una fecha inválida se descarta sola; el evento sobrevive sin ella.
- **Ante error de certificado se reintenta sin verificar.** Varias sedes públicas
  (`culturaydeporte.gob.es`, `fundacionico.es`, `cinesembajadores.es`) sirven cadenas incompletas.
  Sólo leemos HTML público y no mandamos credenciales.
- **Todo lo que entra en el DOM pasa por `esc()`.** El contenido lo escribe un LLM sobre HTML ajeno.
- **El orden por defecto es la fecha de fin, no la de inicio.** Una exposición que abrió en marzo y cierra
  el sábado es urgente; una que abre en noviembre no.
- **No hay ventana temporal en "todo".** Se probó a recortar a "esta semana" y en agosto Madrid no tiene un
  solo evento con día propio: la página salía vacía. La portada sí mira sólo a los próximos nueve días,
  pero el catálogo completo sigue debajo.
- **Conciertos por sala, no por artista.** Hasta agosto de 2026 se buscaban 4.000 artistas en Bandsintown
  (403) y casi nunca salía nada. Ahora se lee la programación de unas pocas salas y el manifiesto decide.

## Estructura

```
culturalme/
├── scrapers/
│   ├── llm.py          # claude -p, descarga (httpx o Chrome), enlaces, prompts, fechas
│   ├── museos.py  galerias.py  charlas.py  teatro.py  cine.py  musica.py
│   └── tagger.py       # kids_friendly + selective contra los manifiestos
├── pipeline.py         # pasada: fuentes en paralelo, upsert, regla de publicación, purga
├── curate.py           # portada de la semana → data/curation.json
├── generate.py         # docs/index.html
├── semanal.py          # lo que corre launchd: todo lo anterior + git push + avisos
├── ops/com.jorge.culturalme-semanal.plist
├── data/
│   ├── culturalme.db   # SQLite (events + sources)
│   ├── curation.json   # la portada
│   ├── jorge_taste.md  # manifiesto del modo Selecto y de la portada
│   └── kids_taste.md   # manifiesto del modo Niños
├── static/             # style.css y fuentes autoalojadas (Poiret One + EB Garamond)
├── docs/               # lo que publica Vercel (vercel.json: outputDirectory docs)
└── tests/
```

## En el Mac mini

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python semanal.py           # una pasada completa a mano, con publicación
.venv/bin/python pipeline.py          # sólo leer fuentes
.venv/bin/python curate.py            # sólo la portada
.venv/bin/python generate.py && open docs/index.html

cp ops/com.jorge.culturalme-semanal.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jorge.culturalme-semanal.plist
```

Necesita `claude` con sesión iniciada (`~/.local/bin/claude`) y Chrome para las fuentes con `render=True`.
Registro en `~/Library/Logs/culturalme-semanal.log`.

## Pruebas

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

Sin red ni modelo: SQLite en memoria y `claude -p` sustituido. Cubren la regla de publicación por fuente,
la sustitución de cartelera, los enlaces propios, la clasificación de agendas mixtas, la validación de la
portada y el saneado de fechas.
