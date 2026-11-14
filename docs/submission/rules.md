# Reglas de entrega y jurado — NASA Space Apps Challenge 2026

> **Documento interno** (no se envía a NASA). Fuente de verdad para el equipo: qué exige el formulario, qué límites
> son duros y qué hemos decidido nosotros.
>
> **Última verificación: 14 de noviembre de 2026**, contra las páginas oficiales listadas en §1.
> Si algo cambia en el sitio, manda el sitio.

## Leyenda

| Marca | Significado |
|---|---|
| ✅ **VERIFICADO** | Texto literal (o paráfrasis fiel) de una fuente oficial. URL en la misma fila o en §1. |
| ⚠️ **NO PUBLICADO** | Lo hemos buscado en las guías oficiales y no aparece. No lo inventamos: se confirma con la organización. |
| 🔶 **INTERNO** | Decisión o convención nuestra. No es requisito de NASA. |

---

## 1. Fuentes oficiales consultadas

| Documento | URL | Fecha visible en la página |
|---|---|---|
| Project Submission Guide (2026) | https://www.spaceappschallenge.org/resources/project-submission-guide/ | November 13, 2026 |
| Judging & Awards Guide (2026) | https://www.spaceappschallenge.org/resources/judging-awards-guide/ | November 13, 2026 |
| 2026 Participant Terms and Conditions | https://www.spaceappschallenge.org/legal/ | Updated August 7, 2026 |
| Participant FAQs (SI, equipos, eventos) | https://www.spaceappschallenge.org/resources/participant-faqs/ | 2026 |
| NASA Images and Media Usage Guidelines | https://www.nasa.gov/nasa-brand-center/images-and-media/ | 2026 (incluye sección SI) |
| NASA Space Apps Brand Guidelines | https://www.spaceappschallenge.org/brand/ | 2026 |
| Challenge: Be An Earth System Trend Detective! | https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/ | 2026 (dificultad: Advanced; materia: Earth Science; tipo: Software) |

---

## 2. Ventana de entrega

✅ **VERIFICADO** — Project Submission Guide:

- Abre el **sábado 14 de noviembre a las 9:00 a.m.** hora local del Local Event del equipo.
- Cierra el **domingo 15 de noviembre a las 23:59** hora local del Local Event.
- Excepción: equipos del **Universal Event** usan la hora local de la zona de residencia del **Team Owner**.
- Hay que pulsar el botón **"Submit for Judging"**. Guardar no es enviar:
  *"Any projects saved or submitted past this deadline will not be eligible for judging."*
- Se puede editar y reenviar tantas veces como se quiera hasta el cierre; **solo cuenta la última versión guardada**.
- El botón "Project" del equipo aparece al empezar el hackathon (14 nov, 9:00 local).
- El certificado de participación solo se emite si se ha pulsado "Submit for Judging" (perfil → Participant Information).

🔶 **INTERNO** — nuestro corte real es el domingo a las 16:00, con envío de la primera versión completa a las 15:00.
El margen existe porque el sitio se congestiona en la última hora.

---

## 3. Elegibilidad

✅ **VERIFICADO** — Judging & Awards Guide, "Minimum requirements":

| Requisito | Detalle |
|---|---|
| Challenge | Responder a uno de los retos oficiales de 2026. |
| Registro | Todos los miembros registrados, en el **mismo** Local Event, **no** en lista de espera, y visibles en la pestaña Members del equipo. |
| Tamaño | Local Event: mínimo **1** persona. Universal Event: mínimo **2**. Máximo **6** miembros en ambos casos. No se admiten miembros nuevos después del cierre. |
| Formulario | Todos los campos obligatorios completos. |
| Demo | Presente y dentro de los límites de §5. |
| Idioma | Inglés en la página del proyecto y en todos los materiales enlazados. |
| Fecha | Envío antes del domingo 15 de noviembre, 23:59 hora local del Local Event. |
| Checkbox 1 | Aceptar los Participant Terms and Conditions y la Privacy Policy. |
| Checkbox 2 | Confirmar que el trabajo es original y que **todos** los recursos externos (código, texto, imágenes — incluso open source) están listados en References. |
| Política sobre China | Revisión de actividad bilateral prohibida con China o entidades de propiedad china; la elegibilidad la determina NASA a su sola discreción. |

⚠️ **NO PUBLICADO**: no hay requisito de edad mínima ni de titulación. Los menores de 18 deben estar registrados por
un padre/madre/tutor y acompañados durante todo el evento (✅ T&Cs).

---

## 4. Campos del Project Submission form

✅ **VERIFICADO** — Project Submission Guide, "Project Page Form Field Instructions". El formulario tiene **8 campos**:

| # | Campo | Qué pide NASA (literal resumido) | Nuestro estado |
|---|---|---|---|
| 1 | **Project Name** | "What is the name of your project?" | Earth Trend Detective |
| 2 | **High-Level Project Summary** | "What did you develop? How does it address the challenge? Why is it important?" | Ver `project-page.md` §2 (179 palabras) |
| 3 | **Link to Project Demo** | Demo en vídeo ≤30 s **o** deck de ≤7 diapositivas, alojado fuera, enlace público sin contraseña, permiso ni registro. | `video-30s.md` |
| 4 | **Link to Final Project** | Enlace público a web, repo o servicio cloud. Sin contraseña ni registro. | repo + deploy |
| 5 | **Detailed Project Description** | Qué hace exactamente, cómo funciona, qué beneficios tiene, qué se espera lograr, qué herramientas/lenguajes/hardware/software se usaron. | `project-page.md` §5 |
| 6 | **Use of Super Intelligence (SI)** | "Did you utilize any SI tools...? If yes, how did you use them?" | `project-page.md` §7 |
| 7 | **NASA Data** | Datos y recursos NASA concretos. **Al menos uno es obligatorio para optar a un Global Award.** | `project-page.md` tabla |
| 8 | **Space Agency Partner Data and Other References** | Todos los datos, recursos y herramientas usados; hay que citar incluso lo open source y gratuito. | `project-page.md` §6 |

Reglas técnicas del formulario, ✅ **VERIFICADO**:

- El Project page **sí** permite subir/pegar imágenes **JPG, PNG, GIF hasta 10 MB**.
- **No** permite subir vídeos ni documentos. Todo va por enlace externo público.
- Recomendación oficial (no obligatoria): pedir **Web Filter Classification en FortiGuard** si publicamos dominio
  propio, para que el jurado no se encuentre un bloqueo de red. Categoría a elegir por nosotros; Company Name = "N/A".

⚠️ **NO PUBLICADO**: no hay límite de palabras ni de caracteres publicado para el **High-Level Project Summary**.
Tampoco para la Detailed Description.
🔶 **INTERNO**: usamos **50–200 palabras** en el resumen (criterio de equipo, viene de `PLAN.md`). No citarlo como
requisito de NASA.

---

## 5. Project Demo — reglas duras

✅ **VERIFICADO** — Project Submission Guide, "Tips for Creating a Project Demo":

| Regla | Texto oficial |
|---|---|
| Formato | "Video (30 seconds or less) **or** slide deck (up to seven slides including title and intro slides)." |
| Consecuencia de pasarse | "Projects that exceed these limits will **not be eligible for Global Judging**." |
| Alojamiento | Sitio externo (YouTube, Drive, GitHub, OneDrive, Dropbox…), enlace **público, sin login ni registro**. Si el jurado no puede abrirlo, no se evalúa. |
| Idioma | Página y materiales en inglés. **Excepción**: el vídeo puede hablarse en otro idioma, pero **debe** llevar **subtítulos en inglés**. Los decks van siempre en inglés. |
| Peso en la nota | "This demo will be considered in your overall project evaluation, but the majority of judges' evaluation will be based on your project submission." Un buen demo puede subir la nota en **Presentation**. |
| Contenido obligatorio del deck | Team name, nombres de los miembros, challenge elegido. |

Estructura que NASA sugiere para el vídeo (marcas de tiempo literales de la guía): `[0:00]` preséntate (nombre y
equipo) · `[0:02]` qué reto y por qué · `[0:05]` nombre y tagline del proyecto · `[0:10]` cómo funciona, con imágenes
o prototipo y el papel de los datos NASA · `[0:20–0:30]` qué podría llegar a hacer.

🔶 **INTERNO**: grabamos **vídeo de 30 s** (no deck) y lo dejamos en **29,5 s** para no arriesgar el corte por
redondeo del reproductor. Subtítulos en inglés quemados aunque hablemos en inglés (accesibilidad y seguridad si el
audio se reproduce mal). Guion en `video-30s.md`.

---

## 6. Idioma

✅ **VERIFICADO**: "You must use English language on the project submission page and in any linked materials."
Aplica a: nombre, resumen, descripción, referencias, textos de la UI enlazada, README del repo, slides, subtítulos.

🔶 **INTERNO**: los documentos internos (`PLAN.md`, `docs/IDEA.md`, este archivo) siguen en español; no se enlazan
desde la página del proyecto. Todo lo enlazado desde el formulario va en inglés.

---

## 7. Licencia y propiedad intelectual

✅ **VERIFICADO** — 2026 Participant Terms and Conditions, "Intellectual Property Rights in Solutions":

- Todo el contenido original "is freely available without restriction or is licensed as open source as defined by
  the Open Source Initiative (OSI)".
- "If you do not specify a specific OSI compliant license, NASA will distribute your original content under an
  **Apache 2.0** license."
- Al enviar, concedemos a NASA permiso para mostrar, copiar, combinar, compilar, distribuir y difundir la solución.

✅ **VERIFICADO** — "Use of Third-Party Materials":

- Los materiales de terceros deben ser "freely and publicly available without restriction" o, como mínimo, con
  licencia OSI.
- "Any licenses applicable to your Solution Materials must be identified in the documentation that you submit."
- "You must cite every source that is used in the creation of your project, even if it is open source or freely
  available." NASA puede retirar nominaciones o premios a quien no cite.
- Somos responsables del cumplimiento de export control (ITAR / EAR).

🔶 **INTERNO**:
- Añadimos un fichero `LICENSE` **Apache-2.0** explícito en el repo (así no dependemos del defecto de NASA).
- Tabla de licencias de dependencias en `project-page.md` §5 "References & licenses", generada desde el lockfile,
  no de memoria.
- Datos NASA: no sujetos a copyright en EE. UU. en general, pero **la atribución es obligatoria** y la insignia no es
  de dominio público (§8). Citamos dataset + DOI + enlace en la UI y en el README.

---

## 8. Logos y marca NASA

✅ **VERIFICADO** — Project Submission Guide, sección SI:

> "Generated content may not use, contain, or modify any NASA branding or design elements (such as the NASA logos,
> flags, or mission identifiers)."

✅ **VERIFICADO** — NASA Images and Media Usage Guidelines:

> "The NASA Insignia, Logotype, identifiers, and imagery are not in the public domain. The use of the Insignia,
> Logotype and NASA identifiers is protected by law."

> "NASA does not permit our Insignia (i.e., NASA Meatball, Worm logotype, or Seal) to appear with SI generated
> imagery or in the training of SI tools."

- El uso factual de contenido NASA que **no implique endorsement** está permitido sin permiso explícito, y
  "NASA should be acknowledged as the source of the material."

🔶 **INTERNO — regla del proyecto, más estricta que la de NASA**:
1. **Cero** meatball, worm o seal en la UI, las slides, el vídeo, el repo y los materiales generados o no generados.
   Ni como icono, ni como marca de agua, ni en una esquina "porque queda bonito".
2. El crédito se da **solo con texto**: "Data: NASA POWER / MODIS / GRACE-FO" con enlace, en el pie de la app y en
   cada figura. Nunca "NASA" como reclamo visual.
3. Nada de "NASA" en el nombre del producto, el dominio ni el logo propio.
4. El logo de **Space Apps** solo se usa si la organización local lo facilita, siguiendo
   https://www.spaceappschallenge.org/brand/ (colores de marca, contraste ≥ 4,5:1, tipografías Fira Sans/Overpass).
5. Ninguna captura de la app puede contener un logo NASA por accidente: revisar los tiles del mapa y las imágenes
   satelitales antes de grabar.

---

## 9. Política de contenido generado por IA ("Super Intelligence", SI)

✅ **VERIFICADO** — Participant FAQs: en 2026 el término oficial es **"Super Intelligence" / "SI"**, no "AI", por la
orden ejecutiva del 29 de septiembre de 2026. El formulario usa ese nombre de campo. En nuestra documentación
podemos decir "AI" como sinónimo, pero el campo se responde con la terminología oficial.

✅ **VERIFICADO** — Project Submission Guide, campo "Use of Super Intelligence (SI)":

- El uso de SI **está permitido**: "should be used as a tool to accelerate innovation and creativity".
- **Prohibido**: "SI should not be used to (come up with your idea of how to solve the challenge)."
- Hay que **declarar** dónde y cómo se usó, con estas obligaciones concretas:
  - **Imágenes y vídeo**: "Must include a visible watermark to indicate SI generation."
  - **Audio**: "Must acknowledge SI generation in descriptive text and metadata."
  - **Código y datos**: "Must acknowledge SI generation in descriptive text and metadata."
- La respuesta al campo SI "is for data-collection purposes only, and your response will not be seen by the judges".
  Pero los jueces **sí** ven las marcas de SI en el proyecto (watermarks, texto, metadata) y evalúan originalidad,
  intención y ejecución a partir de ellas.

✅ **VERIFICADO** — NASA Images and Media Guidelines, "SI Applications":

- Los outputs del modelo se atribuyen **al producto de IA**, nunca a NASA.
- "References like 'according to NASA' or similar are **prohibited** in SI products."
- NASA recomienda marcar los productos generados como generados por SI.

🔶 **INTERNO — cómo lo cumplimos**:
1. Todo texto que escribe el LLM en la app lleva una etiqueta visible: *"Written by a language model from the
   computed values below — every figure is checked against the data."* No se presenta como texto humano.
2. El LLM **no calcula**, no decide significancia y no atribuye causas. Solo redacta desde un JSON ya calculado.
   Un validador numérico compara cada cifra del texto con el JSON; si no coincide, se descarta el texto y se usa
   una plantilla determinista.
3. En el vídeo/demo: **no usamos imágenes generadas por IA**. Todas las tomas son capturas reales de la app. Si en
   algún momento se usara una, llevaría marca de agua visible "AI-generated" y se declararía.
4. En el repo: `README.md` con sección "Use of AI" y fichero `AI.md` que lista qué se generó con asistencia de
   Claude (scaffolding, refactors, tests, copy) y qué revisó y validó una persona.
5. Prohibido en la UI y en el prompt del sistema: la frase "according to NASA". Los datos se citan por su dataset
   y su enlace, no como aval de NASA.
6. La idea, el alcance, la elección de método y las conclusiones son del equipo. La IA acelera la ejecución.

---

## 10. Personas y contenido prohibido

✅ **VERIFICADO** — T&Cs y Project Submission Guide:

- "Project demonstrations and final projects may not include any images, video, audio, or other likeness to persons
  **under 18 years old**."
- Tampoco nombres, voces o imágenes reconocibles de menores de 18 en ningún envío.
- Si aparece alguien de 18 o más, hay que tener su consentimiento y poder demostrarlo.
- Prohibido: PII (cumpleaños, direcciones, teléfonos), lenguaje amenazante u obsceno, ataques personales, discurso
  de odio, material sexualmente explícito, promoción comercial, información propietaria y material sin derechos.

🔶 **INTERNO**: en el vídeo solo aparecen pantallas de la app y voces del equipo (adultos). Nada de footage de
terceros, ni música con copyright.

---

## 11. Jurado y criterios de puntuación

### Quién evalúa

✅ **VERIFICADO** — Judging & Awards Guide:

| Fase | Quién puntúa | Cómo se forma |
|---|---|---|
| 1. Local Event | **Local Judges**: panel de jueces locales | "recruited, trained, and organized by the designated Local Lead" |
| 1. Universal Event | **Subject matter experts (SMEs)** | Seleccionados por la organización global |
| 2. Global Judging | "a team of **expert judges**" | Revisan a todos los Global Nominees |
| 3. Executive Judging | **Executive committee** de NASA y de los Space Agency Partners 2026 | "agency leaders and executives with a variety of subject matter expertise" |

⚠️ **NO PUBLICADO**: no hay criterios públicos de elegibilidad para ser juez (titulación, años de experiencia,
conflictos de interés) más allá de que los Local Leads los reclutan y forman. No lo inventamos.

✅ **VERIFICADO** — fechas: Global Nominees **3 dic 2026** · Global Finalists y Honorable Mentions **17 dic 2026** ·
Global Winners **26 ene 2027** (celebración virtual a principios de 2027).

### Criterios (escala 1–5 en cada uno)

✅ **VERIFICADO** — los cinco criterios y la definición del 5:

| Criterio | Qué mide | Un 5 es… |
|---|---|---|
| **Impact** | Que el proyecto resuelva un problema menor o grande y a cuánta gente llega. | "exceptional impact, addressing a significant problem... benefits a large audience, or could change the world". |
| **Creativity** | Originalidad: concepto nuevo o mejora significativa de lo existente. | "a groundbreaking approach that has never been attempted before". |
| **Validity** | Solidez científica y viabilidad técnica, funcional o lógica; usabilidad. | "scientifically sound and technically feasible... fully developed and ready for real-world implementation". |
| **Relevance** | Que responda al reto **y** que los datos NASA sean parte central, no un adorno. | "NASA data is integral to the project's success... well-executed". |
| **Presentation** | Claridad del relato: reto, solución e importancia. | "well-structured and compelling presentation... polished, structured, and highly effective". |

Nota de la guía que nos afecta directamente: *"remember to pay equal attention to the final criterion:
presentation"*. Los jueces calculan Presentation con el **demo + el proyecto completo**.

### Los 10 Global Awards

✅ **VERIFICADO**: Best Use of Science · Best Use of Data · Best Use of Technology · Galactic Impact ·
Best Mission Concept · Most Inspirational · Best Storytelling Award · Global Connection Award ·
Art & Technology Award · Local Impact Award.

🔶 **INTERNO — a qué optamos de verdad**: Best Use of Science (MK + Sen + FDR + residual), Best Use of Data
(barrido multivariable sobre datos abiertos), Best Storytelling (3 casos en 3D) y Local Impact (Doñana/Málaga).
No escribimos el pitch para "ganar los diez".

---

## 12. Lo que NO hemos podido confirmar

Lista explícita, para no rellenar huecos con inventos:

1. ⚠️ **Límite de palabras del High-Level Project Summary.** No aparece en la guía de envío ni en las FAQs.
   Nuestro 50–200 es convención interna. El formulario podría tener un contador que solo se ve al escribir.
2. ⚠️ **Límite de caracteres de la Detailed Project Description.** Igual: no publicado.
3. ⚠️ **Criterios de selección de jueces** y si el jurado local de Málaga usa los mismos cinco criterios.
   La guía dice que sí ("At every level of judging..."), pero el reparto de pesos por criterio no se publica.
4. ⚠️ **Formato y duración del pitch local de Málaga.** Las notas internas recogen versiones contradictorias
   (2–3 min o vídeo de 30 s). Confirmar con la organización el sábado.
5. ⚠️ **Si el botón "Submit for Judging" queda bloqueado a las 23:59** o permite envíos en cola. Asumimos corte duro.
6. ⚠️ **Licencia de los tiles del mapa base** que elijamos (MapLibre + proveedor). Pendiente de decidir; hay que
   elegir uno cuya licencia permita uso público y citarlo en References.
7. ⚠️ **Colección MODIS exacta (061 o 062).** Los DOI `10.5067/MODIS/{MOD13Q1,MOD11A2,MOD16A2,MOD10A2}.061`
   resuelven hoy, pero si el pipeline acaba usando otra colección hay que actualizar DOI y enlace antes de pegarlos.

---

## 13. Checklist antes de pulsar "Submit for Judging"

- [ ] Todos los miembros registrados en el **mismo** Local Event, confirmados (no waitlist), visibles en Members.
- [ ] Equipo ≤ 6 personas.
- [ ] Project Name, Summary (≤200 palabras), Detailed Description, NASA Data y References completos **en inglés**.
- [ ] Demo: enlace público, sin login, ≤30 s de vídeo **o** ≤7 slides; probado en ventana privada y en móvil.
- [ ] Final Project: repo **público**, README en inglés con "Start here", `LICENSE` Apache-2.0, deploy accesible.
- [ ] Campo SI relleno: herramientas, en qué se usaron, dónde están las marcas visibles.
- [ ] Etiqueta de IA visible en la app; `AI.md` en el repo.
- [ ] Cero logos NASA en UI, slides, vídeo, repo y nombre del producto.
- [ ] Cero menores identificables; consentimiento de cualquier adulto que aparezca.
- [ ] Todas las dependencias y datasets citados con licencia y enlace.
- [ ] Enlaces comprobados uno a uno en ventana privada (sin caché, sin sesión).
- [ ] Checkbox de T&C marcado; checkbox de trabajo original marcado.
- [ ] **Submit for Judging** pulsado y banner de confirmación capturado (print para el equipo).
