# Tercer caso: decisión (para hablar con Mandy a las 17:30)

> Basado en `docs/story/research-*.md` (5 dosieres, 73 URLs verificadas). No hay cifras inventadas:
> cada número de aquí tiene fuente en su dosier.

## Recomendación: **Doñana** en modo historia. Málaga en modo explora.

| Criterio | Doñana | Málaga | Rondônia |
|---|---|---|---|
| Claridad de la señal | 8/10 | 4/10 | 6/10 |
| Literatura que separa clima / no clima | **10/10** | 9/10 | 7/10 |
| Cercanía para un jurado de Málaga | 8/10 | **10/10** | 1/10 |
| Datos NASA disponibles | 8/10 | 7/10 | **9/10** |
| **Total** | **35** | 30 | 23 |

## Por qué Doñana

1. **El paper ya hace exactamente lo que nosotros automatizamos.** 442 imágenes Landsat, 316 lagunas,
   1985–2018: **el 83 % de las lagunas se inundan menos de lo que explica el clima**. Esa es nuestra
   "columna del residuo", publicada y citable. En el pitch se dice así: *"el método existe y está publicado;
   lo que no existe es una web que lo haga por ti en dos minutos"*.
2. **Hay una frase que cuenta el caso sola**, y está medida: la laguna de Santa Olalla se secó dos veces en
   ~50 años de registro (1983, 1995) y luego **tres años seguidos** (2022, 2023, 2024).
3. **Está a 2,5 h de Málaga** y es un icono que el jurado conoce. No es un embalse de Nevada.
4. **La frase que resume el caso en una línea:** el parque está protegido; el acuífero que lo alimenta no.

## Por qué Málaga va al modo explora (y no al modo historia)

El embalse de La Viñuela pasó del **17 % (sep-2024) al 96 % (abr-2026)**. Eso es un **episodio, no una
tendencia**: un Sen sobre esa serie saldría *no significativo*. Como titular del modo historia sería un
titular falso en 2026.

Como demo del modo explora es **oro puro**: es el caso que enseña el semáforo honesto.
*"Elegimos el embalse que todo el mundo en Málaga conoce. La respuesta es: 'todavía no se puede decir'."*
Eso es exactamente lo que nos separa de una herramienta que siempre encuentra una tendencia.

## Lo que necesito que confirme Mandy (10 min de datos, no de opinión)

1. **bbox propuesto:** lon −6.60 … −6.25 · lat 36.85 … 37.15 (Doñana Natural Space, 1.225 km²).
2. **¿Hay señal clara en MODIS/Landsat para NDVI y extensión de agua** en esa ventana, 2003–2024?
   Si la señal es débil, el caso pierde su gracia.
3. **Resolución del PNG de tendencia:** a 250 m (MODIS) la ventana son ~120×130 px; a 30 m (Landsat) son
   ~1000×1100 px. Con 512×512 nos vale: **que rellene a 512 con el remuestreo que prefiera**.
4. **Coste:** si Doñana no da señal en 45 min, el plan B es **Rondônia** (MODIS NDVI 250 m continuo
   2000–2026, la mejor disponibilidad de datos de los cinco). No es Málaga: su serie no aguanta un test.

## Lo que aporto yo en cuanto haya `sites/donana/`

- `steps` (3), `narrative`, `labels` y `caveats` en inglés, con el molde de §5 de `ALE-PLAN.md`.
- La frase de Santa Olalla para el pitch, con su fuente.
- El guion de lo que se dice mientras se pulsa play.
