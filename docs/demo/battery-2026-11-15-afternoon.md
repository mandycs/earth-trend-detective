# Batería del detective — 15 nov, tarde (tras el afinado)

Las mismas 15 preguntas de la noche (12 sitios + 3 seguimientos, mismo hilo), en serie, contra la API en vivo
`http://100.70.153.87:8765` (código de `main` en `b682611`). Comparado con las grabaciones de la noche
(`HANDOFF-2026-11-15.md` §5). Las tres primeras corrieron a la vez que las 4 grabaciones de demo; el resto, solas.

## Resumen

| | Noche | Tarde |
|---|---|---|
| Terminan | 15/15 | 15/15 |
| Errores | 0 | 0 |
| Respuestas `checked` (todas las cifras trazadas por el checker) | 15/15 | 15/15 |
| Caen a plantilla | 1 (Chad) | **3** (CV seguimiento, Punjab, Punjab seguimiento) |
| Intentos rechazados por el checker (total) | — | 20 (cause 9, residual_wording 4, direction 4, lead 2, length 1) |
| `next_questions` | — | 15/15 con 3 |
| Mediana de duración | 19 s | **73 s** |
| Llamadas a herramientas (media) | 8,4 | **15,3** |

## Por pregunta

| # | Pregunta | Noche: s / llamadas / fuente | Tarde: s / llamadas / fuente | Rechazos | Mapa (ops) |
|---|---|---|---|---|---|
| 01 | Aral: still shrinking? | 24,8 / 10 / llm | 47,1 / 19 / llm | 3 | fly_to, show_layer, footprint, before_after |
| 02 | Rondônia: forest cut down? | 22,7 / 10 / llm | 107,2 / 16 / llm | 0 | fly_to, show_layer, before_after, overlay |
| 03 | Chad: why disappearing? | 33,4 / 13 / **template** | 140,2 / 18 / llm | 2 | fly_to, footprint, show_layer, before_after |
| 03b | ↳ Did the rain change? | 7,7 / 1 / llm | 12,4 / 2 / llm | 3 | show_layer, footprint |
| 04 | Central Valley: groundwater? | 16,5 / 8 / llm | 72,8 / 17 / llm | 0 | fly_to, footprint, show_layer ×2 |
| 04b | ↳ What could be causing it? | 21,6 / 7 / llm | 65,7 / 8 / **template** | 4 | show_layer |
| 05 | Punjab: farmers using up water? | 25,7 / 11 / llm | 76,6 / 17 / **template** | 3 | fly_to, footprint, show_layer ×2 |
| 05b | ↳ Climate or the farms? | 14,7 / 2 / llm | 69,8 / 8 / **template** | 2 | show_layer |
| 06 | Delhi hotter? | 14,5 / 7 / llm | 67,2 / 16 / llm | 0 | fly_to, footprint, show_layer ×2 |
| 07 | Greenland ice melting? | 19,6 / 11 / llm | 70,2 / 18 / llm | 1 | fly_to, footprint, show_layer ×2 |
| 08 | Sahel greener or drier? | 20,1 / 14 / llm | 113,8 / 22 / llm | 0 | fly_to, show_layer ×3, footprint |
| 09 | Siberia warming fast? | 12,6 / 6 / llm | 66,6 / 17 / llm | 0 | fly_to, footprint, show_layer |
| 10 | Mar Menor worse? | 19,1 / 12 / llm | 230,7 / 18 / llm | 1 | fly_to, show_layer ×2 |
| 11 | Atlantic ocean warming? | 14,8 / 7 / llm | 198,3 / 16 / llm | 1 | fly_to, overlay, show_layer, footprint |
| 12 | Málaga hotter? | 12,8 / 7 / llm | 125,0 / 18 / llm | 0 | fly_to, show_layer, footprint, show_layer |

(05b no se lanzó en la primera pasada por un fallo de mi script —el hilo de "05_punjab" no se guardó porque el
nombre contiene una "b"— y se lanzó justo después en su hilo; es la misma pregunta.)

## Lo que mejora

- **Chad** ya no cae a plantilla y dice el sentido correcto ("went up"); lluvia y aire quedan descartados porque
  van al revés (punto 1 del afinado).
- **Lluvia sobre medias anuales**: Chad seguimiento da ~0,45 mm/día/década (anoche 0,0071) — punto 2 resuelto.
- **Faceta "still/recently"**: Central Valley, Siberia, Málaga, Mar Menor prueban los últimos años y lo dicen
  ("too noisy to call" o "still warming, about 0.9 °C").
- **"No se puede medir"**: Aral (open water), Central Valley / Punjab (groundwater alone), Greenland (ice directly),
  Chad (open water) lo dicen en la respuesta.
- **Océano**: el Atlántico ahora mide el mar (anoche solo el aire sobre el mar). Mar Menor usa clorofila.
- **Mapa automático**: todas las preguntas de sitio empiezan con `fly_to` y pintan al menos una capa.
- Respuestas en palabras de calle (litros por m², "1 in ten parts") y 3 `next_questions` siempre.

## Regresiones (honestas)

1. **Duración ×4 (mediana 19 → 73 s).** No es el modelo: casi todo el tiempo es `get_series` (la tanda paralela
   de descarga de series tarda 36–201 s; Mar Menor 201 s, Atlántico 116 s, Málaga 100 s). Probablemente caché
   fría de variables nuevas (suelo, clorofila, mar, NDVI) o lentitud del proveedor. Para la demo en vivo: usar
   sitios ya calentados o la grabación.
2. **Plantilla 1 → 3**, justo en Punjab y su seguimiento. El texto de plantilla es correcto pero torpe:
   "about 300 km or about 25 km or about 50 km across" y no responde a la faceta ("climate or the farms?",
   "still falling?"). Motivo: el narrador escribe "cause"/"direction" y el checker lo rechaza 3–4 veces.
3. **Más llamadas (8,4 → 15,3)**: esperable por el afinado (más series y la prueba reciente), pero suma tiempo.
4. **Atlántico**: "warmer air is a supported suspect, since its year-to-year changes moved with the sea
   temperature" roza la atribución (el checker la acepta); y "The recent years also point up, though they gave
   no separate number" es confuso.
5. **Almería** (grabación de demo, no batería): "We can't see any greenhouses, since the land data shows no
   cropland class" — MODIS no tiene clase invernadero; el terreno "Barren" pasó de 1 a 3 de cada 10 y la
   respuesta no lo menciona. Se lee como "no hay invernaderos". No se guarda como demo.

Cifras: las 15 respuestas pasan el checker (`checked: true`, ninguna `false`), así que según el checker no hay
cifras inventadas. No las he trazado a mano una a una.

## Grabaciones de demo (4 corridas)

| Grabación | Resultado | ¿Se guarda? |
|---|---|---|
| Punjab "Is the groundwater going down here?" (29.95, 77.0) | 24 s, 17 llamadas, llm, 0 rechazos, 3 next | **Sí** → `punjab.json` |
| ↳ "Why? And is it still falling in recent years?" | 21 s, plantilla tras 3 rechazos; no responde a "still falling" | No |
| Lake Mead denso (36.1, −114.7) | 38 s, 18 llamadas, llm, 1 rechazo, 3 next; responde "last ten years too noisy" | **Sí**, sustituye a `mead.json` |
| Almería invernaderos (36.75, −2.75) | 35 s, llm, checked, pero engañosa (ver arriba) | No |

El replay no muestra la pregunta de seguimiento (la caja enseña solo `recording.question`), así que aunque el
seguimiento hubiera salido bien, iría como grabación aparte.

Coste OpenRouter de todo (batería + 05b + 4 grabaciones): **≈ 3,93 USD** (uso 79,12 → 83,05 de 90).
