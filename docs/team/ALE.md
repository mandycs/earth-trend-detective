# Ale — 3D, historia, copy, demo y pitch

Plan general: [`PLAN.md`](../../PLAN.md) · Compañera: [`MANDY.md`](MANDY.md)
**Plan detallado con horarios, puertas y recortes: [`ALE-PLAN.md`](ALE-PLAN.md)** ← empieza por ahí.
**Qué falta y qué mejoraría con más tiempo: [`ALE-NEXT.md`](ALE-NEXT.md).**

**Recibo de Mandy:** `sites/<id>/` con PNGs reales + `site.json` → **ya integrados los tres, renderizan.**
**Entrego a Mandy:** guion y textos en inglés de cada caso → **en `sites/<id>/copy.json`**, no en `site.json`
(así el pipeline puede regenerar el JSON sin borrar el texto).

> Estado, sábado 17:20 · la escena 3D corre con los **datos reales** de Lake Mead, Aletsch y Doñana.
> Lo que falta de verdad: capa de tendencia por píxel y frames anuales (lado de Mandy), slides, test con
> personas y ensayo del pitch (mío).

## Sáb 15:30–17:30 · Arranque
- [x] Decidir el 3er sitio → **Doñana**, confirmado. Brief y puntuación: [`../story/SITE-3-DECISION.md`](../story/SITE-3-DECISION.md)
- [x] Pantallas: inicio y modo historia, con propósito a primera vista y un botón principal (en código, no en Figma)
- [x] Escena 3D mínima en `frontend/` con react-three-fiber
- [ ] Modo explora (2D): no existe. Es de Mandy y es la mitad de la promesa "elige cualquier lugar"

## Sáb 18:00–23:00 · Escena 3D
- [x] Terreno: `PlaneGeometry` + heightmap + exageración vertical (relieve calculado del `heightmap_range_m`)
- [x] Capa de tendencia (shader, divergente, alfa = significancia) — *probada con asset sintético; los PNG reales aún no existen*
- [x] Línea de tiempo con fundido entre años — *implementada; deshabilitada hasta que lleguen `year_*`*
- [x] Paneles con serie + veredicto + narrativa leídos de `site.json` (+ `copy.json`)
- [x] Semáforo accesible: icono + texto (`✓ Real ↓`, `? Can't tell yet`), nunca solo color

## Sáb noche · Historia
- [x] Guion de los 3 casos, en inglés: `sites/{lake_mead,aletsch,donana}/copy.json`
- [x] El caso "esto sí es clima" (Aletsch) — su `narrative` es la frase que uso en el pitch
- [ ] Analogías para público ("+1,2 °C ≈ mover la ciudad 150 km al sur") — no escritas

## Dom 09:00 · CORTE 3D
- [ ] Puerta: ¿los tres casos se ven bien con datos reales? **Hoy: sí en relieve y panel; no en capa por píxel**

## Dom 09:00–13:00 · Pulido
- [x] Integrar sitios 2 y 3 (los tres cargan y muestran sus 6 variables)
- [ ] Pasar por el **puesto UX** (Eliana Crivaro) — *pre-revisión hecha por medición: contraste mínimo 8,2:1,
      texto ≥ 16 px, botones ≥ 44 px, cero desbordamiento a 390 px; falta la pasada formal con la hoja*
- [ ] Borrador de slides

## Dom 13:00–16:00 · Entrega y pitch
- [ ] Project Demo: **≤ 7 slides (portada incluida)** o **vídeo ≤ 30 s**, en inglés, un único enlace público
  - Estructura: proyecto/reto → problema → solución → recurso NASA y función → demo → qué funciona + límites → impacto/siguiente paso
- [ ] Resumen 50–200 palabras — *borrador de 179 palabras en [`../submission/project-page.md`](../submission/project-page.md), sin revisar*
- [x] Descripción detallada con **built / simulated / next** — *borrador completo, pendiente de revisión*
- [ ] **Test con 3 personas**: ¿encuentran una tendencia real en su ciudad en < 2 min? Apuntar tiempos
- [ ] Confirmar con organización el formato del pitch (duración, preguntas, soporte) — *depende de la reunión del sábado*
- [ ] Ensayar respuestas cortas ([`../demo/pitch.md`](../demo/pitch.md) §respuestas) — *escritas, sin ensayar*
- [x] Sin logos NASA en contenido generado · sin menores identificables

> Si three.js no es lo tuyo, avísalo pronto: Claude hace la escena 3D desde el lado de Mandy y tú te quedas
> con guion, copy, validación en Giovanni, demo, pitch y página Project. **Resuelto: la escena está hecha y funciona.**
