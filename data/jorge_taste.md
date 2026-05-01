# Manifiesto de gusto cultural — Madrid

Contexto para que un LLM marque eventos (exposición, concierto, charla, película, obra de teatro) como `selectivo: sí` / `selectivo: no`.

## Me interesa

- **Arte siglo XX–XXI con curaduría seria.** Realismo figurativo, hiperrealismo y pintura urbana (línea Hopper, Estes, Antonio López, Isabel Quintanilla, Andrew Wyeth, Fairfield Porter). También expresionismo abstracto, minimalismo y conceptual sólo si son obras canónicas, no ejercicios decorativos.
- **Ensayo de no ficción con datos.** Reportaje largo, biografía intelectual, historia económica, libros que cuentan algo con números delante.
- **Charlas de policy con evidencia empírica.** Economía aplicada, política pública, datos en mesa. Mejor si la persona publica papers o escribe en Substacks serios.
- **Temas activadores:** vivienda, ciudad, demografía, mercado laboral, desigualdades, crecimiento, brechas generacionales, geopolítica europea, IA y su impacto, energía y transición, Estado y administración pública.
- **Ciencia dura sólo si conecta con sociedad o economía** (no biología por la biología, no astrofísica de divulgación; sí IA, energía, salud pública con datos, biotech con implicaciones de mercado).
- **Música indie, rap, rock o electrónica contemporánea.** No hace falta nombre de cartel — el descubrimiento es parte del punto. Rango cómodo: indie/post-punk británico contemporáneo, rap español exigente, folk/rock americano contemplativo, electrónica de autor.
- **Cine de autor con criterio.** A24, Cannes, Berlín, Sundance, Locarno son atajos razonables. Filmoteca y retrospectivas siempre interesan.
- **Teatro contemporáneo con texto y oficio.** Adaptaciones literarias serias, dramaturgia de autor, intérpretes con peso (Sacristán, Blanca Portillo, Israel Elejalde, Andrés Lima).

## Me da igual

- Divulgación científica blanda sin gancho social o económico.
- Cuestiones menores y de nicho académico sin ambición analítica.
- Historia local o anecdótica sin hilo conceptual.
- Festivales y ciclos genéricos sin línea editorial visible.

## Banderas rojas

- **Lenguaje postmoderno:** *deconstruir*, *resignificar*, *decolonial*, *narrativas*, *imaginarios*, *afectos*, *cuidados*, *miradas situadas*, *cuerpos*, *resiliencia*.
- **Activismo en lugar de análisis.** Tono militante, emocional o de denuncia disfrazado de academia.
- **Autoayuda y wellness.** TED motivacional, mindfulness, sanación, *transformador*, *propósito*, coaching, "encuentra tu voz".
- **Formato participativo.** *Performance participativa*, *experiencia inmersiva*, *co-creación*, *facilitación*, *deriva colectiva*, taller vivencial.
- **Música derivativa.** Tributos, covers, homenajes, "lo mejor de", jazz de ambiente, flamenco fusión genérico, musicales mainstream.
- **Literatura romántica, autoficción confesional, autoayuda en disfraz literario.**
- **"Arte y emociones", "arte que sana", postmodernismo pretencioso, neo-espiritualidad.**
- **Mesas redondas con 5+ ponentes** o charla-coloquio sin moderación firme; divulgación con humorista o famoso de relleno.
- **Esoterismo y etiquetas vacías:** *círculo de mujeres*, *espacio seguro*, *ecosocial*, *escucha activa*, *intuitivo*.
- **Marca por encima del contenido:** evento patrocinado por banco/telco como excusa promocional.

## Universos de cabecera

Los nombres siguientes son **emblemas** de las corrientes que me importan, no una lista cerrada. El LLM debe inferir "alguien del mismo universo" cuando tope con eventos: gente del mismo gremio, escuela, círculo de pensamiento o circuito artístico vale igual.

- **Economía aplicada de frontera:** Esther Duflo, Abhijit Banerjee, Raj Chetty, Claudia Goldin, Daron Acemoglu, Dani Rodrik, David Card, Emmanuel Saez, Tyler Cowen, Noah Smith, Branko Milanović.
- **Policy en español:** Luis Garicano, Toni Roldán, José García-Montalvo, Florentino Felgueroso, Manuel Hidalgo, Mauro Guillén, Pol Antràs, Jorge Galindo (también si aparece).
- **Divulgación con rigor y estética:** Jaime Altozano, Quantum Fracture, Hannah Ritchie, Nate Silver, Our World in Data, voces tipo *Works in Progress* / *Asterisk*.
- **Realismo pictórico y figuración seria:** Edward Hopper, Richard Estes, Andrew Wyeth, Antonio López, Isabel Quintanilla, Fairfield Porter, Eric Fischl, John Sloan, Alex Colville.
- **Indie / post-punk / electrónica de autor:** The xx, Bon Iver, Beach House, Mount Kimbie, Burial, James Blake, Big Thief, Phoebe Bridgers, Wild Beasts, Caribou, Four Tet.
- **Cine y teatro de oficio:** A24, ciclos de Filmoteca, retrospectivas de autor; en escena Sacristán, Blanca Portillo, Israel Elejalde, Andrés Lima, Lluís Pasqual.
- **Fotografía documental:** Henri Cartier-Bresson, Robert Frank, Dorothea Lange, Sebastião Salgado, Vivian Maier, Cristina García Rodero, Alex Webb, Saul Leiter, William Eggleston, Stephen Shore, Magnum en general.
- **Arquitectura:** Mies van der Rohe, Le Corbusier, Alvar Aalto, Louis Kahn, Tadao Ando, Rafael Moneo, Alejandro de la Sota, Alejandro Aravena, Norman Foster, Rem Koolhaas, Lacaton & Vassal, Anne Lacaton, Snøhetta.
- **Filosofía analítica:** Bertrand Russell, Wittgenstein, Quine, John Rawls, Robert Nozick, Daniel Dennett, Derek Parfit, Bernard Williams, Saul Kripke, Timothy Williamson, T. M. Scanlon, Peter Singer, Frank Jackson.

## Regla de decisión

- **`selectivo: sí`** cuando:
  - Aparece un nombre de "Universos de cabecera" **o alguien que claramente pertenezca al mismo universo** (mismo gremio, escuela, círculo, circuito).
  - El tema cae limpio en "Me interesa" **y** no hay banderas rojas en título o descripción.
  - Es música indie/rap/rock/electrónica sin nombre conocido y la sala o línea editorial encaja.
- **`selectivo: no`** cuando:
  - Aparece cualquier bandera roja, aunque el tema sea atractivo. La duda se resuelve descartando.
  - Es divulgación blanda, lenguaje postmoderno o formato participativo.
- **Jerarquía:** headliner > tema > banderas. Un headliner real anula banderas rojas razonables; un tema fuerte **no** las anula.
- **Horario, duración, precio:** indiferentes.
- **Ante duda final:** descartar. Mejor un falso negativo que un falso positivo.
