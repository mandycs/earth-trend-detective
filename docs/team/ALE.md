# Ale — 3D, historia, copy, demo y pitch

Plan general: [`PLAN.md`](../../PLAN.md) · Compañera: [`MANDY.md`](MANDY.md)
**Plan detallado con horarios, puertas y recortes: [`ALE-PLAN.md`](ALE-PLAN.md)** ← empieza por ahí.

**Recibo de Mandy:** `sites/<id>/` con PNGs reales + `site.json`. Mientras tanto, trabaja con [`sites/_example/`](../../sites/_example/site.json).
**Entrego a Mandy:** guion y textos en inglés de cada caso (campos `narrative`, `label`, `steps` de `site.json`).

> Si three.js no es lo tuyo, avísalo pronto: Claude hace la escena 3D desde el lado de Mandy y tú te quedas
> con guion, copy, validación en Giovanni, demo, pitch y página Project.

## Sáb 15:30–17:30 · Arranque
- [ ] Decidir el 3er sitio (Doñana / Rondônia / algo de Málaga) con Mandy
- [ ] Bocetos de las pantallas: inicio, modo historia, modo explora (propósito a primera vista, un botón principal)
- [ ] Escena 3D mínima en `frontend/` con react-three-fiber cargando `_example`

## Sáb 18:00–23:00 · Escena 3D con datos falsos
- [ ] Terreno: `PlaneGeometry` + heightmap + exageración vertical
- [ ] Capa de tendencia (shader, divergente, atenuado si no significativo)
- [ ] Línea de tiempo: cambiar/fundir texturas anuales
- [ ] Paneles con serie + veredicto + narrativa leídos de `site.json`
- [ ] Semáforo accesible: icono + texto (`↑ Real`, `↓ Real`, `? Can't tell yet`), nunca solo color

## Sáb noche · Historia
- [ ] Guion de los 3 casos, en inglés. Orden: qué cambia → ¿es real? → ¿es el clima?
- [ ] Un caso tiene que ser "esto sí es clima" (Aletsch) para mostrar que no siempre culpamos al humano
- [ ] Analogías para público ("+1.2 °C ≈ moving 150 km south")

## Dom 09:00 · CORTE 3D
- [ ] ¿Funciona el sitio 1 con datos reales? Si no → modo historia en mapas 2D animados

## Dom 09:00–13:00 · Pulido
- [ ] Integrar sitios 2 y 3
- [ ] Pasar por el **puesto UX** (Eliana Crivaro): texto ≥ 16 px, contraste ≥ 4,5:1, táctil ≥ 44 px, estados de carga
- [ ] Borrador de slides

## Dom 13:00–16:00 · Entrega y pitch
- [ ] Project Demo: **≤ 7 slides (portada incluida)** o **vídeo ≤ 30 s**, en inglés, un único enlace público
  - Estructura: proyecto/reto → problema → solución → recurso NASA y función → demo → qué funciona + límites → impacto/siguiente paso
- [ ] Resumen 50–200 palabras (en inglés)
- [ ] Descripción detallada: **built / simulated / next**
- [ ] **Test con 3 personas**: ¿encuentran una tendencia real en su ciudad en < 2 min? Apuntar tiempos
- [ ] Confirmar con organización el formato del pitch (duración, preguntas, soporte)
- [ ] Ensayar respuestas cortas (PLAN §12)
- [ ] Sin logos NASA en contenido generado · sin menores identificables
