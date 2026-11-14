# ALE — plan detallado, 30 horas

> Expansión de [`ALE.md`](ALE.md). Documento interno en español; **todo lo que se entrega va en inglés**.
> Última actualización: sáb 14 nov, 16:25. Estado real al escribir: **la escena 3D ya corre con datos falsos**.

---

## 0. La regla de las 30 horas

Tenemos 30 horas de reloj, no 30 de trabajo. Mi parte son **cinco trabajos** (3D, historia, copy, demo, pitch) y
solo soy una persona. El orden de prioridad **no** es el del checklist original:

| Prioridad | Trabajo | Por qué |
|---|---|---|
| 1 | **Demo + pitch** | es el 100 % de lo que el jurado ve de nosotros |
| 2 | **Historia de los 3 casos** | sin historia, la web es otra herramienta de mapas |
| 3 | **Copy en inglés** | es lo que convierte un número en una frase que se entiende |
| 4 | **Integración de los sitios 2 y 3** | depende de Mandy; si llega tarde, se recorta |
| 5 | **3D** | el factor "wow", pero es lo único con plan B (mapas 2D) |

Traducción práctica: **si a las 09:00 del domingo tengo que elegir entre pulir el 3D y escribir las slides,
escribo las slides.** El 3D ya está por delante de lo que pide el plan; a partir de ahora solo se toca si no
compromete la demo.

---

## 1. Decisiones tomadas (y por qué)

1. **`frontend/` con Next.js 16 + React 19 + react-three-fiber 9.** Decisión del equipo. La escena vive en
   `src/story/` y solo `StoryApp.tsx` lleva `'use client'`; `src/app/page.tsx` es un server component que
   la monta. Los assets se sirven desde `sites/` mediante `scripts/sync-sites.mjs` → `public/sites`.
   Trampa documentada: sin `allowedDevOrigins: ['127.0.0.1']` el dev server entrega el HTML pero **no
   hidrata**, y parece que la app está rota cuando en realidad es el origen del HMR.
3. **Los assets del modo historia se sirven desde `sites/` de la raíz**, no duplicados a mano. Next solo
   sirve desde `public/`, así que `scripts/sync-sites.mjs` espeja `sites/` → `public/sites` en `predev` y
   `prebuild`. Mandy escribe en `sites/`, yo consumo la misma ruta. Cero pasos manuales, y si `sites/` no
   existe el build no falla: la UI enseña su estado honesto de "este caso no tiene assets".
4. **La escena se alimenta de `site.json` + PNGs, nunca de números escritos en el código.** La regla de cifras
   del producto (el LLM no inventa cifras) también aplica a mí: si un número aparece en pantalla, viene del JSON.
5. **Assets falsos generados y marcados.** `sites/_example/make_fake_assets.py` produce heightmap, textura base,
   capa de tendencia y 22 frames anuales sintéticos. La UI avisa en pantalla de que son placeholders.
   Sin esto no se puede construir ni enseñar nada hasta que Mandy tenga datos.

---

## 2. Definición de "mi parte está terminada"

| # | Artefacto | Ruta | Cómo se prueba |
|---|---|---|---|
| 1 | Escena 3D con relieve, capa de tendencia y timeline | `frontend/src/story/` | `npm run build` + recorrido manual de los 3 pasos |
| 2 | Los 3 casos cargando desde `site.json` real | `sites/<id>/` | abrir cada pestaña de caso y ver los 3 pasos |
| 3 | Guion en inglés de los 3 casos (narrative, label, steps, caveats) | dentro de cada `site.json` | revisión palabra por palabra: **0 cifras que no estén en el JSON** |
| 4 | Deck de ≤ 7 slides en inglés, un enlace público | `docs/demo/` | abrir en ventana privada, 7 slides contadas |
| 5 | Vídeo de ≤ 30 s (plan B del deck) | enlace público | reproducir sin ratón |
| 6 | Guion literal del pitch + respuestas cortas | `docs/demo/pitch.md` | ensayo cronometrado ≤ 3:00 |
| 7 | Resumen 50–200 palabras + secciones de la página Project | `docs/submission/` | contar palabras, enlaces probados |
| 8 | Test con 3 personas cronometrado | `docs/demo/usability-test.md` | 3 filas con tiempos reales |
| 9 | Repaso del checklist UX con la demo abierta | `docs/UX-CHECKLIST.md` | cada casilla marcada con evidencia |

---

## 3. Cronograma con puertas

Ahora son las **16:25 del sábado**. Todo lo que sigue está en hora local.

### Sáb 16:25 – 17:30 · Cerrar el arranque
- [x] Escena 3D mínima cargando `_example` (hecho y verificado en navegador)
- [x] Boceto de la pantalla principal: título, una frase, un botón (hecho, en código)
- [ ] **Decidir el 3er sitio con Mandy** → **recomendación cerrada: Doñana.** La investigación está hecha y
      puntuada: Doñana 35, Málaga 30, Mead 28, Aletsch 27, Rondônia 23. Argumento decisivo: el paper de Doñana
      **ya hace** la separación clima/no clima que nosotros automatizamos (83 % de 316 lagunas se inundan menos
      de lo que explica el clima). Brief para la conversación: [`../story/SITE-3-DECISION.md`](../story/SITE-3-DECISION.md).
      Plan B si Doñana no da señal en 45 min: Rondônia. Málaga va al **modo explora** como demo del
      "can't tell yet" (su embalse pasó del 17 % al 96 % en 18 meses: episodio, no tendencia).
- [ ] Mandy confirma si va a usar Next.js o se queda con `frontend/` tal cual. Si no contesta antes de las
      18:00, asumo que se queda.

### 17:30 – 18:00 · Revisión con la organización
Tres frases y una demo de 30 s. Guion en `docs/demo/org-review.md` (lo escribo antes de las 17:15):
1. Qué es: "elige un lugar y te dice qué cambia, si es real y cuánto no explica el clima".
2. Qué se ve hoy: la escena 3D con el caso de muestra y el semáforo.
3. Qué necesitamos de ellos: **formatos del pitch** (duración, preguntas, soporte) y si el Project Demo
   admite vídeo además de slides.

### 18:00 – 22:00 · Escena 3D, segunda pasada (solo con datos falsos)
- [ ] Exageración vertical y encuadre por sitio (`vertical_exaggeration`, `elevation_m` en `site.json`)
- [ ] Transición de la capa de tendencia al cambiar de variable (fundido de 400 ms, no corte)
- [ ] Estado "sin capa de tendencia" cuando una variable no tiene PNG (debe verse bien, no roto)
- [ ] Comprobar a 1366×768 (portátil del jurado) y a 390×844 (móvil)
- [ ] Rendimiento: 60 fps con la capa anual; si no, bajar la malla de 340×340 a 220×220
- [ ] Captura de pantalla decente de cada paso para el deck (las necesito yo)

### 22:00 – 23:00 · Caso 1, guion en inglés
- [ ] Escribir `narrative`, `label`, `steps[3]`, `caveats` del caso 1 contra el `site.json` real de Mandy
- [ ] Pasar a Mandy el texto para que lo meta en el JSON (o abrir PR yo mismo)

### 23:00 · **Checkpoint 1 con Mandy**
Qué miro: ¿hay `sites/lake_mead/` con PNGs reales y `site.json`? Si no, sigo con `_example` y escribo el guion
con huecos `{{...}}` marcados para rellenar. **No espero de pie.**

### 23:00 – 01:30 · Guiones 2 y 3 + esqueleto del deck
- [ ] Guion de Aletsch (caso "esto sí es clima") y del 3er sitio
- [ ] Esqueleto de las 7 slides con títulos y qué se ve en cada una
- [ ] Grabar un primer vídeo de 30 s con `_example` (sirve de ensayo y de plan B)

### 02:00 – 08:30 · Dormir
No es negociable. El pitch se pierde por estar roto, no por dormir 6 horas.

### 08:30 – 09:00 · **Checkpoint 2 / corte del 3D**
Pregunta única: **¿el sitio 1 se ve bien con datos reales?**
- Sí → sigo con 3D y pulo.
- No, pero se arregla en 45 min → lo arreglo y vuelvo a preguntar a las 09:45.
- No, y no hay arreglo claro → **modo historia en mapas 2D animados**. Decisión cerrada, sin debate.
  Lo que se queda: la estructura de 3 pasos, el semáforo accesible y los textos. Lo que se cae: three.js.

### 09:00 – 11:00 · Integrar sitios 2 y 3 + copy final
- [ ] Los tres casos abren sin errores ni placeholders visibles
- [ ] Textos definitivos en inglés, sin cifras inventadas
- [ ] Revisión de la lista UX punto por punto con la demo delante

### 11:00 – 13:00 · Deck y vídeo
- [ ] Las 7 slides cerradas (contenido en §6)
- [ ] Vídeo de 30 s grabado y subido, como respaldo
- [ ] Enlace público comprobado en ventana privada

### 13:00 – 14:30 · Test con 3 personas + arreglos
- [ ] Protocolo de §7 ejecutado, con tiempos apuntados
- [ ] Arreglar solo lo que haya roto a 2 de las 3 personas

### 14:30 – 16:00 · Congelar y enviar
- [ ] Nada se toca después de las 16:00 salvo el pitch
- [ ] Submit for Judging hecho y **captura de la confirmación**
- [ ] Repaso de enlaces en ventana privada

### 16:30 – 19:00 · Prueba técnica y pitch
- [ ] Ensayo con el reloj, dos veces
- [ ] Respuestas cortas de §8 memorizadas en una línea cada una

---

## 4. Escena 3D — qué hay, qué falta, cómo está hecho

### Hecho y verificado hoy
- **Terreno**: `PlaneGeometry` 340×340 desplazada en el vertex shader con el heightmap, normales recalculadas
  por diferencias finitas (sin normal map) → el sombreado responde al relieve de verdad.
- **Capas**: base satélite + tendencia (Sen por píxel, alfa = significancia) + frames anuales con fundido.
  Las tres se componen en el fragment shader con `MeshStandardMaterial.onBeforeCompile`.
- **Timeline**: play/pausa y arrastre, 2003→2024, fundido entre años consecutivos, bucle al final.
- **Panel**: 3 pasos (`What is changing` → `Is it real` → `Is it the climate`), lista de variables con
  sparkline en SVG, semáforo con icono + texto (`✓ Real ↓`, `? Can't tell yet`), barra de reparto clima/no clima.
- **Estados**: carga ("Loading layers…"), error de caso sin assets con botón de recuperación, aviso de
  placeholders cuando el `id` empieza por `_`.
- **Comprobado en navegador**: los 3 pasos cambian los píxeles renderizados (hash distinto por paso),
  el scrub 2003→2024 cambia la superficie, el conmutador de casos muestra el error correcto y se recupera.

### Comandos
```bash
cd frontend
npm run dev        # http://127.0.0.1:5180 (Next 16, sincroniza sites/ antes)
npm run build      # build de producción
npm run typecheck  # tsc --noEmit
# regenerar assets falsos:
uv run --python 3.11 --with pillow --with numpy python sites/_example/make_fake_assets.py
```

### Lo que falta
| Falta | Coste | Cuándo |
|---|---|---|
| Fundido al cambiar de variable | 20 min | sáb 18:00 |
| Afinar exageración/encuadre por sitio | 30 min | sáb 18:00 |
| Revisión móvil y 1366×768 | 30 min | sáb 20:00 |
| Capturas para el deck | 20 min | sáb 21:30 |
| Code-split del bundle (1,1 MB → 320 kB gzip hoy) | 30 min | **solo si sobra tiempo** |

---

## 5. Historia y copy — el molde de los tres casos

### Estructura fija (los mismos 3 pasos en los 3 casos)
1. **¿Qué cambia aquí?** Una imagen y una frase. Sin cifras todavía.
2. **¿Es real?** La cifra, el veredicto y —si toca— "harían falta N años más".
3. **¿Es el clima?** El reparto y la frase que separa pista de causa.

### Reglas de escritura (aplican a `narrative`, `label`, `steps`, `caveats`)
- Frases de **máximo 18 palabras**. Una idea por frase.
- **Palabras prohibidas en la UI**: Mann-Kendall, Sen, FDR, p-value, residual, anomalía, significancia
  estadística, atribución, GRACE (en el titular; en la fuente sí). Si hace falta el concepto, se explica
  con una comparación ("una vez de cada mil por pura casualidad").
- **Ninguna cifra que no esté en el JSON.** Si quiero decir "el 70 % no lo explica el clima", el 70 está en
  `residual_pct_non_climate`. Si no está, no se dice.
- Voz activa, segunda persona, presente. "You pick a place", no "places can be selected".
- **Nunca "proof", "cause", "because of humans".** Sí: "a clue", "consistent with", "does not explain".
- Un caso tiene que sonar a **alivio** (Aletsch: esto sí es el clima) para que el patrón se entienda.
- Las analogías van en el guion del pitch, no en la UI (la UI se defiende sola).

### Lo que entrego a Mandy (campos de `site.json`)
```jsonc
{
  "name": "Lake Mead",                    // 1-3 palabras, como lo diría un local
  "country": "United States",             // país, no región
  "steps": [
    { "title": "What is changing here?", "body": "≤ 45 palabras" },
    { "title": "Is it real, or is it chance?", "body": "≤ 45 palabras" },
    { "title": "Is it the climate?", "body": "≤ 45 palabras" }
  ],
  "variables": [
    { "id": "grace_tws", "label": "Total water stored" }   // label ≤ 4 palabras, sin siglas
  ],
  "narrative": "≤ 60 palabras para el paso 3",
  "caveats": ["≤ 20 palabras cada una"],
  "sources": [ { "title": "NASA GRACE", "url": "https://…" } ]
}
```
Regla de oro: **si el texto necesita el gráfico para entenderse, está mal escrito.**

---

## 6. Demo: las 7 slides (portada incluida)

| # | Slide | Qué se ve | Qué digo (≤ 2 frases) |
|---|---|---|---|
| 1 | Portada | Nombre + "Is it the climate, or is it us?" + los 3 casos | Qué es, en una frase |
| 2 | Problema | Las 3 barreras: qué variable pedir, la estadística, cruzar variables | "Los datos son públicos; el método no" |
| 3 | Solución | La pantalla en 3 pasos, sin texto técnico | "Cuatro preguntas, en orden" |
| 4 | Demo | Captura de los 3 pasos del caso 1 + el semáforo | La demo en 40 s |
| 5 | Por qué es honesto | `? Can't tell yet`, "N more years needed", pista ≠ causa | "Preferimos decir que no lo sabemos" |
| 6 | Recurso NASA | Tabla recurso → función real (GRACE, MODIS, GPM, POWER) | "Sin NASA no hay producto" |
| 7 | Qué hay / qué falta | Tabla **built / simulated / next** + un enlace | Lo que funciona hoy, sin adornos |

Regla: **una idea por slide**. Las de prosa, ≤ 40 palabras (la portada real tiene 56 contando etiquetas; el
cuerpo son 12). Las de tabla o listas, ≤ 120, porque el deck se lee solo, sin narrador: un jurado que lo abre
en la plataforma no te oye. Si una slide de prosa necesita explicación, la slide está mal.

El deck vive en `frontend/public/deck.html` (un solo fichero, 7 slides de 1280×720, imprimible a PDF con
Ctrl+P). Se sirve en `<url>/deck.html`, así que el enlace público es el mismo deploy de la app.

---

## 7. Test con 3 personas (domingo 13:00)

Protocolo idéntico para las tres, cronómetro en mano:
1. Abrir la web y callarse. **No tocamos nada, no explicamos nada.**
2. Tarea: *"Encuentra un cambio real cerca de tu ciudad."*
3. Apuntar: ¿lo consigue? ¿cuánto tarda? ¿dónde se atasca? ¿qué dice en voz alta?
4. Meta: **< 2 minutos** las 3 personas. Si 2 de 3 se atascan en el mismo sitio, ese sitio se arregla.
5. Guardar la tabla en `docs/demo/usability-test.md` con tiempos reales. Se lo enseño al jurado.

---

## 8. Pitch: el esqueleto y las respuestas

**90 s** (si la organización da 2–3 min, se estira con la demo, nunca con más slides):
1. 0-10 s · La pregunta que nadie responde: "tu pantano se vacía, ¿es el clima o somos nosotros?"
2. 10-30 s · Qué hace la web, con la pantalla delante.
3. 30-60 s · Los 3 pasos sobre el caso 1, señalando el semáforo y el reparto.
4. 60-75 s · Lo honesto: "cuando no se puede saber, lo decimos".
5. 75-90 s · Impacto y siguiente paso: institutos, prensa local, ayuntamientos.

Respuestas cortas (una línea cada una, ensayadas):
- **¿Dónde interviene NASA?** En cada serie del barrido y en el reparto clima/no clima.
- **¿Qué funciona hoy?** La tabla built/simulated/next de la slide 7.
- **¿Cómo sé que no estáis inventando?** El LLM solo redacta desde números calculados, y un validador
  comprueba cada cifra; si falla, se usa una plantilla.
- **¿Principal limitación?** El reparto es una pista, no una causa: lo que no medimos cae en el saco.
- **¿Qué os hace distintos de Climate Engine?** Ellos te dan una variable; nosotros cruzamos y explicamos.

---

## 9. Contrato con Mandy y plan B

| Lo que necesito | Para cuándo | Si no llega |
|---|---|---|
| `sites/<id>/` con PNGs + `site.json` del sitio 1 | sáb 23:00 | sigo con `_example`, guion con huecos `{{}}` |
| Sitios 2 y 3 | dom 09:00 | demo con 1 caso real + 2 con datos de muestra **marcados** |
| Decisión Next.js vs Vite | sáb 18:00 | se queda Vite; migrar después es 15 min |
| Confirmar que `site.json` respeta los campos de §5 | sáb 20:00 | adapto el render a lo que haya y lo documento |

Nota importante para Mandy: el render **tolera** variables sin capa de tendencia, sin serie anual y sin
`residual_pct_non_climate`. Prefiero un caso incompleto que se vea honesto a uno completo que se vea roto.

---

## 10. Recortes, en este orden

1. Vídeo de 30 s (el deck de 7 slides basta).
2. Segundo y tercer caso en modo historia (se quedan como pestañas con mensaje honesto).
3. Animación anual (se queda la capa de tendencia estática).
4. Capturas cuidadas para el deck (vale una captura normal).
5. Todo el 3D (mapas 2D animados). **Última opción, y solo si falla el checkpoint de las 09:00.**

Nunca se recorta: los textos, el semáforo honesto, el pitch y el submit.

---

## 11. Estado exacto para retomar

```bash
# 1. Servir la web
cd C:/Users/aleja/Desktop/NASA/earth-trend-detective/frontend && npm run dev   # puerto 5180
# 2. Ver que compila
npm run build
# 3. Volver a generar los assets falsos si se borran
uv run --python 3.11 --with pillow --with numpy python ../sites/_example/make_fake_assets.py
```
- La web abre en `http://127.0.0.1:5180/` y carga `sites/_example/`.
- Los otros dos casos están listados pero vacíos: muestran el estado de error a propósito.
- Lo siguiente en la lista es §3, sábado 18:00: fundido de capa al cambiar de variable.

---

## 12. Riesgos de mi parte

| Riesgo | Señal de que está pasando | Qué hago |
|---|---|---|
| Me enamoro del 3D y no llego a la demo | a las 23:00 no hay guion escrito | corto el 3D en el acto |
| Los textos suenan a paper | frases de 30 palabras con "significancia" | reescribo con las reglas de §5 |
| El guion depende de cifras que aún no existen | aparecen `{{}}` en el JSON final | escribo la frase sin cifra o la quito |
| El deck se llena de texto | más de 40 palabras por slide | recorto a la mitad, sin piedad |
| El pitch se va de tiempo | el ensayo pasa de 2:00 | quito la slide 6 y la digo de viva voz |
| Los datos reales llegan a las 08:00 del domingo | checkpoint 2 sin sitio 1 | activo el plan 2D y aviso a Mandy en el momento |

---

## 13. Reglas verificadas de la convocatoria (afectan a mi trabajo)

Fuente: [`../submission/rules.md`](../submission/rules.md) — con URL por cada afirmación y una lista explícita
de lo que **no** se pudo confirmar.

| Regla | Consecuencia para mí |
|---|---|
| Project Demo: **vídeo ≤ 30 s o deck ≤ 7 diapositivas** (portada e intro incluidas). Pasarse = fuera de Global Judging | Deck de 7, contadas. Si sobra tiempo, vídeo de 29,5 s como respaldo |
| Todo el texto enviado va **en inglés** (nombre, resumen, descripción, referencias, UI enlazada, README, slides, subtítulos) | también el README del repo y los textos de la UI |
| 2026 lo llama **"Super Intelligence (SI)"**, no "AI", y hay un campo obligatorio del formulario | la declaración va redactada y lista para pegar, no improvisada a las 15:50 |
| **Imágenes o vídeo generados por SI llevan marca de agua visible** | **cero imágenes generadas por IA en el deck**. Capturas de la app y diagramas hechos por nosotros |
| La insignia de NASA **no** es de dominio público y no puede aparecer junto a contenido generado por SI | cero meatball/worm/seal en UI, slides, vídeo y repo. Se dice "built with NASA data", nunca "according to NASA" |
| Licencia: **Apache-2.0** por defecto si no se indica otra | añadir `LICENSE` Apache-2.0 al repo (lo hace Mandy en el cierre) |
| **Al menos un dataset NASA** es obligatorio para optar a Global Award | la tabla de la slide 6 y de la página Project ya lo cubre |
| Los jueces ven las marcas de SI y evalúan originalidad | mejor decir nosotros lo que usamos que esconderlo |

Lo que sigue **sin confirmar** y hay que preguntar el sábado a las 17:30: formato y duración del pitch local,
si el Project Demo admite vídeo además del deck, y si el puesto UX requiere inscripción.

