# culturalme v2 — plan de trabajo

**Qué es**: la agenda de **esta semana** en Madrid. Se abre el viernes por la mañana y contesta una sola
pregunta: *¿qué hago estos días?* Lo que no cabe en esa pregunta, o se va a un segundo plano, o se va del todo.

Punto de partida medido (pasada del 14-ago): 241 eventos publicados, **1 empezaba en los 7 días siguientes**;
106 (44%) llevaban meses sin aparecer en su fuente; 225 (93%) enlazaban a una home genérica.

## Decisiones

- **Dos planos, no seis secciones.** El corte es por naturaleza del evento, no por capricho:
  - **Esta semana** (vista por defecto): charlas, teatro y cine. Se muestra lo que solapa con `[hoy, hoy+7]`.
    Cine entra siempre: la cartelera *es* la de esta semana. Orden: por día, con cabecera de día.
  - **Exposiciones**: museos y galerías. Duran meses, no son "de esta semana", pero son la mitad del valor.
    Orden: **por fecha de cierre ascendente** — lo que se acaba antes es lo accionable.
- **Conciertos fuera, entero.** Se borran `scrapers/conciertos.py`, `data/artists.json`, DICE y Bandsintown,
  el secret `DICE_API_KEY` y las 18 filas de la sección en la DB. Razón medida: 18 eventos en cuatro meses
  con 4.011 artistas en lista, y **4m08s de la última pasada para encontrar 1 concierto**. Bandsintown
  devuelve 403 y nunca ha producido nada.
- **Nada se publica si no se ha visto en la última pasada.** Es el cambio con más efecto: quita los 106
  fantasmas de golpe. Además se purgan filas con `last_seen` de más de 60 días. Cine se sigue reemplazando.
- **Se acaban las alucinaciones de año.** Cuatro reglas, todas en Python, ninguna confiada al modelo:
  1. La fecha de hoy va explícita en el prompt.
  2. Ventana válida `[hoy−30d, hoy+18m]`; fuera de ella la fecha se descarta (el evento sobrevive sin fecha,
     no se tira).
  3. `date_end < date_start` → el cierre pasa al año siguiente (es el caso "9 jul – 10 ene").
  4. Formato estricto `YYYY-MM-DD`; `2026-07` se descarta.
  Hoy hay 61 eventos fechados en 2027 y 139 en 2024 por esta vía.
- **`event_id` sin fecha**: pasa a ser `source|title|venue`. Las fechas se **actualizan** al reencontrar el
  evento en vez de crear una fila nueva. Colapsa los 109 duplicados actuales (*BISONTES EN LLAMAS* está
  cuatro veces con cuatro fechas de 2024).
- **De 76 fuentes a 36.** Se quedan las que han producido algo en las últimas cuatro pasadas. Fuera las 28
  restantes: 5 dominios **sin registro DNS** (mpazarte, parraromero, albarranbourdais, fernandez-braso,
  galleryweekendmadrid), Helga de Alvear 404, García Galería 500, las 5 ferias (cero eventos desde siempre)
  y 11 SPAs que sirven JS y devuelven menos de 600 caracteres de texto.
- **Reintento SSL antes de rendirse.** Los fallos de `culturaydeporte.gob.es`, `fundacionico.es` y
  `cinesembajadores.es` son cadenas de certificado incompletas, no caídas. Se intenta con verificación normal
  y sólo ante error TLS se reintenta sin verificar. Recupera 4 fuentes, entre ellas **Cines Embajadores**
  (39.000 caracteres, 32 fechas) que no ha funcionado nunca. No se envían credenciales a ningún sitio, así que
  el riesgo de bajar la verificación en esos hosts es leer HTML público manipulado, no filtrar nada.
- **Matadero deja de scrapearse dos veces.** `museos.py` y `teatro.py` apuntan a la misma URL con nombres
  distintos ("Matadero Madrid" y "Naves del Español") y duplican cada evento. Se queda una sola entrada.
- **Diseño: el de granvia.** Negro puro, Poiret One en versales espaciadas para títulos y chips, EB Garamond
  para el texto, filetes de 1px, cero cajas de color. Las tres `woff2` se copian de `~/repos/granvia/fonts`
  y se autoalojan: fuera Fraunces, fuera la paleta pastel rainbow y fuera la llamada a Google Fonts.
- **Se escapa el HTML.** Hoy títulos y descripciones se inyectan crudos en template strings; hay un evento
  real titulado `<SCRI> B` (Nave 73) que desaparece de la página por eso.
- **Se van dos controles**, por redundantes con la vista nueva — dímelo si prefieres conservarlos:
  - El selector de sede: con dos planos y ~10 fuentes en cada uno, sobra.
  - El orden "Más nuevo / Por fecha": en una agenda sólo hay un orden. El badge "nuevo" se queda.
- **Se mantienen** los modos ⭐ Selecto y 👶 Niños con sus manifiestos tal cual, el botón Visto y su
  `localStorage`, el cron de los viernes, GitHub Pages y el coste (~$2-4/mes de Haiku, hosting gratis).

## Pasos

1. `scrapers/llm.py`: fecha de hoy en los prompts, validación y saneado de fechas, fallback TLS.
2. `pipeline.py`: `event_id` sin fecha, `UPDATE` de fechas al reencontrar, purga por `last_seen`, fusión de
   `upsert_events` y `replace_section` (hoy repiten el mismo INSERT de 20 líneas), fuera `image_url`
   (columna muerta, 0 filas) y el doble mecanismo `GLOBAL_EXCLUDE` + `EXCLUDE_TITLES`.
3. Poda de fuentes en los cinco scrapers; borrado de `conciertos.py` y `artists.json`.
4. Migración de la DB: purga de conciertos, de fechas imposibles y de duplicados por el `event_id` nuevo.
5. `generate.py`: los dos planos, cabeceras de día, escapado, y limpieza del bucle duplicado de `.filter-btn`
   y del `EVENTS.indexOf(e)` dentro del `map`.
6. `static/style.css` nuevo + fuentes autoalojadas.
7. Pasada real en local para ver la web con datos frescos, `README.md` al día (hoy dice "~50 fuentes" y
   "18 museos"; son 76 y 19, y documenta un `runtime.txt` que no existe) y nota de proyecto en memoria.

## Fuera de la v2

- **Playwright.** Lo que arreglaría el Prado (403 en todas sus rutas, protección de bots), el Thyssen y las
  11 SPAs. Es un runner distinto y multiplica el tiempo de pasada; si luego quieres el Prado, es su propio
  trabajo.
- Conciertos por Songkick o Ticketmaster Discovery (JSON estructurado, cero LLM). Descartado hoy por decisión
  tuya; la puerta queda abierta.
- Imágenes en las tarjetas, notificaciones, filtro por barrio, precios y entradas.

---

## Después de ejecutarlo (20-ago-2026)

La primera pasada real con el modelo confirmó los arreglos de datos (0 duplicados, 0 fechas incoherentes,
0 eventos fechados en 2024, 6m10s frente a 15m56s) y tumbó la decisión de producto principal:

**"Esta semana" no funciona.** En agosto Madrid no tiene un solo evento con día propio — el primero es el
1 de septiembre. La ventana de 7 días dejaba la portada en tres obras y la cartelera de cine, que se lee
exactamente igual que la app rota de la que veníamos. El problema no era el dato, era el recorte: la
temporada de Madrid arranca en septiembre y no cabe en siete días.

Sustituido por **cuatro pestañas de tipo de actividad** (exposiciones, cine, teatro, charlas), sin ventana
temporal, con **orden por fecha de fin** y un conmutador a "más nuevo". Vuelven así los dos controles que
la v2 había quitado por redundantes, que dejan de serlo en cuanto desaparece la agrupación por día.

Lo demás del plan se mantiene: la purga por `last_seen`, el `event_id` sin fecha, la validación de fechas
en Python, el rescate TLS, las 39 fuentes, el escapado y el diseño de granvia.
