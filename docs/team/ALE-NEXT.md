# Con más tiempo: qué mejoraría y por qué

> Auditoría honesta al final del sábado. Cada punto lleva coste estimado y qué gana el jurado.
> Los tres primeros son **huecos**, no mejoras: sin ellos la demo promete más de lo que enseña.

---

## 0. Los tres huecos que más pesan hoy

| Hueco | Estado real | Qué cuesta cerrarlo |
|---|---|---|
| **Capa de tendencia por píxel** | `assets.trend` está vacío en los tres sitios. La leyenda dice "Regional series · no per-pixel layer yet" | 1–2 h en el pipeline. Es el 80 % del "wow" |
| **Frames anuales** | `assets.yearly` vacío → la línea de tiempo está deshabilitada | 1 h. Sin ellos no hay "mira cómo se vacía" |
| **Modo explora (2D)** | No existe. La promesa "elige cualquier lugar" hoy no se puede enseñar | 3–4 h. Es de Mandy, pero es la mitad del pitch |

Y una cuarta, de credibilidad: **el paso 3 no cambia la superficie**. Verificado con hashes: pasos 2 y 3 pintan lo mismo porque el residuo solo vive en el panel. Se arregla con el primer hueco.

---

## 1. Producto — lo que subiría la nota de verdad

1. **El residuo como capa, no como barra.** Un `residual_<var>.png` (mismo formato que `trend_`) y el paso 3 pinta el mapa del "esto no lo explica el clima". Es la diferencia entre explicar el método y enseñarlo. *Coste: 3 h (1 pipeline + 1 render + 1 copy).*
2. **Intervalos de confianza visibles.** `ci_low` y `ci_high` ya vienen en el JSON y no se usan. Una gráfica de la pendiente con su intervalo convierte la incertidumbre en algo que se ve: "si el intervalo cruza el cero, no hay tendencia". *Coste: 2 h.*
3. **Cepillado temporal.** Arrastrar una ventana sobre la serie y recalcular la tendencia ahí. La limitación que confesamos ("depende del periodo") pasa a ser interactiva, y el jurado la entiende en cinco segundos. *Coste: 3–4 h si el backend lo permite; 1 h si se precalculan 3 ventanas.*
4. **La rueda de sospechosos.** Mandy ya tiene un motor de "suspect lineup": presentar las causas candidatas con evidencia a favor y en contra, en vez de una cifra sola. Convierte el panel en una investigación. *Coste: 2 h de UI sobre datos que ya existen.*
5. **Descargar la prueba.** Botón que baja el CSV de la serie y el PNG de la tendencia. Un periodista local puede citarnos; un ayuntamiento puede llevarlo a una comisión. *Coste: 1 h.*
6. **"Lo que no pudimos medir".** El pipeline ya escribe `missing: {lst_day: "…"}` y la UI lo ignora. Enseñarlo es honestidad visible y gratis. *Coste: 30 min.*
7. **Comparar dos lugares.** Dos terrenos lado a lado, mismo año, misma variable. "Mira tu embalse al lado de Doñana". *Coste: 4 h.*

---

## 2. El otro enfoque (la apuesta alternativa)

**a) Mapa primero, diorama opcional.** El 3D es un artefacto de presentación: impresiona en la demo, pero no ayuda a leer un dato. Con el mismo esfuerzo, un mapa 2.5D (MapLibre + hillshade animado + la capa de tendencia encima) es más legible en un proyector, funciona en móvil y carga en 1 segundo. El diorama se queda como "cinematic mode" para el pitch. **Si volviéramos a empezar, yo haría esto.**

**b) Una variable contada a fondo, no seis a medias.** El barrido de seis variables es el argumento técnico, pero la historia se cuenta con una. La demo perfecta: una variable, tres pasos, el mapa cambiando, y el resto en una tabla.

**c) El pitch como un caso que se resuelve en vivo.** Sin slides: abrir la web, elegir el lugar del jurado, y que el veredicto aparezca delante de ellos. Más arriesgado, mucho más memorable. Necesita que el modo explora exista y que la wifi aguante.

---

## 3. Datos y estadística

- **Bootstrap por bloques** para el intervalo de la pendiente, en vez del asintótico: respeta la autocorrelación y es defendible ante cualquiera que pregunte.
- **Pre-whitening vs Hamed-Rao**: calcular ambos y mostrar que la conclusión no cambia. Cuesta poco y blinda la defensa ante un estadístico del jurado.
- **FDR espacial (Benjamini-Yekutieli)**: los píxeles vecinos no son independientes; el BH clásico es optimista. Con la capa por píxel esto deja de ser teórico.
- **Validación cruzada del residuo**: ¿el modelo predice años que no ha visto? Si no, el "% no climático" es un ajuste, no una señal.
- **MK estacional** (por mes) además de la media anual: detecta cambios que se esconden al promediar.

---

## 4. 3D y rendimiento

- **Texturas KTX2/Basis** y **code-split de three**: hoy el bundle son ~1 MB (277 kB gzip) y las texturas PNG van sin comprimir. En una wifi de hackathon eso se nota.
- **`frameloop="demand"`** cuando la escena está quieta: la batería del portátil del jurado lo agradece.
- **DPR adaptativo** (1 en móvil) y **poster frame** mientras cargan las texturas.
- **Accesibilidad real**: navegar la escena con teclado (flechas orbitan, +/− zoom) y una tabla de datos equivalente para lectores de pantalla. El semáforo ya no depende del color, pero **la capa de tendencia sí**: probarla con deuteranopia simulada y, si falla, añadir trama además de color.

---

## 5. Narrativa y pitch

- **Un giro por caso.** Lake Mead no es "bajó el agua": es "la lluvia no falló, nosotros tomamos el agua". Doñana no es "se seca": es "el parque está protegido, el acuífero no". Un caso sin giro es un gráfico.
- **La analogía climática** que pide `ALE.md` y aún no está escrita: "+1,2 °C ≈ mover tu ciudad 150 km al sur". Va en el pitch, no en la UI.
- **Tres segundos de silencio** con el mapa girando antes de decir la conclusión. Es la parte que la gente recuerda.
- **Un caso que salga "no se puede decir"** en la demo en vivo y decirlo con orgullo. Es el momento más diferenciador del pitch.

---

## 6. Proceso (para la próxima)

- **Esquema JSON + test de contrato en CI.** Hoy el manifiesto cambió dos veces bajo los pies (campos renombrados, `narrative: null`) y se arregló a mano. Un `site.schema.json` y un test de 20 líneas lo habrían cazado en 10 segundos.
- **Playwright con los tres pasos y una aserción por veredicto.** El fallo más caro posible a las 15:50 es "el botón no hace nada", y es exactamente lo que un test e2e caza.
- **El copy en un fichero aparte** (ya hecho: `copy.json`, que el pipeline no puede pisar). Lección general: separar lo que genera una máquina de lo que escribe una persona.
- **Congelar el copy antes que el código.** Los textos se pueden escribir el viernes; el código no.
