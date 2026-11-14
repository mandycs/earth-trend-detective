# Handoff — sesión backend/datos de Mandy (sáb 14 nov 2026, ~18:00)

> Para empezar una sesión nueva en limpio. Interno, en español. Lo entregable va en inglés.
> Documentos que mandan: [`PLAN.md`](../../PLAN.md) · [`AGENTS.md`](../../AGENTS.md) · [`MANDY.md`](MANDY.md) · [`../UX-CHECKLIST.md`](../UX-CHECKLIST.md).

## 1. Estado del repo

- `main` = `mandy/arranque` en `6d64a0c`+ (Mandy hizo push a mano; el hook bloquea a Claude el push a `main`).
  `mandy/arranque` va por delante con commits nuevos (OpenRouter, relieve/mosaico): ver `git log main..mandy/arranque`.
- Backend: `backend/` (FastAPI, uv, `source backend/.venv/bin/activate`). **270 tests** con `python -m pytest -q`.
- Frontend: `frontend/` (Next 16.4.6 + R3F, npm, **no actualizar versiones**). `/` = modo historia 3D (Ale),
  `/explore` = mapa 2D (Mandy, tema propio acotado en `src/app/explore/`).
- Commits: `<type>: <desc>` + líneas de co-autoría. Push en cada commit de la rama de trabajo; **nunca a `main`**.

## 2. Qué está hecho

**Datos (NASA)** — extractores con caché en `backend/data/cache/` (git-ignorada):
- POWER (clima, sin auth) · GRACE/GRACE-FO JPL mascons (agua total, ~300 km) · GLDAS Noah mensual vía Earthdata
  Cloud OPeNDAP (data rods está retirado) · AppEEARS (MODIS, NetCDF primero, QC) · NASADEM (relieve) · GIBS (imagen).
- Validación no NASA: USBR nivel de Lake Mead (r = 0,70 con GRACE, 233 meses).

**Motor** (`backend/app/stats/`): anomalías → MK Hamed-Rao + Sen + IC → FDR BH → semáforo `real/likely/unknown`;
`years.py` (años necesarios); `residual.py` (clima vs no clima, modelos candidatos elegidos por validación cruzada
por bloques; Lake Mead 84 %, el modelo con clima de las Rocosas no valida → rango honesto 54–84 % pendiente de
decisión); `lineup.py` (rueda de sospechosos: diferencias anuales, retardos 0–2, FDR, out-of-sample, placebos —
**motor listo, sin datos reales aún**).

**Reglas de honestidad ya en código** (`site_report.py`): sin % no climático para GLDAS (modelo sin uso humano) ni
para GRACE en sitios `snow/glacier` (Aletsch); cada caso lleva `note`/`caveats` en inglés llano.

**API** (`backend/app/main.py`): `/health`, `/variables`, `/sweep?lat&lon[&include_series]`, `/sites`,
`/sites/{id}/sweep`, `POST /explain/route`, `POST /explain/narrative` (LLM + validador de cifras + 1 reintento +
plantilla). LLM: Anthropic con `LLM_API_KEY` o, si no hay, **OpenRouter** con la clave de `~/.secrets/openkey`
(Sonnet/Haiku 5.5). Probado en real: el validador rechazó un borrador y aceptó el segundo.

**Assets** (`sites/<id>/`, contrato en `frontend/README.md` + `frontend/src/story/types.ts`):
- Los 3: `heightmap.png` (16 bit), `heightmap.json`, `base.jpg`, `site.json` (country, elevation_m, caveats,
  series anuales, note, badge, headline, missing, validation).
- Lake Mead: `trend_lst_day.png/.json`, `year_lst_day_<YYYY>.png` ×22 (la tendencia caliente cae sobre el antiguo
  lecho del lago).
- **Nuevo (sin commit al escribir esto):** `heightmap_rgb.png` (terrain-RGB, 0,1 m), `hillshade.png`,
  `base_hq.jpg` (mediana de 12 escenas HLS 30 m sin nubes) — script en
  `backend/app/assets/{relief,composite}.py`. Revisar `base_hq.jpg` y, si gusta, sustituir a `base.jpg` y listar
  `heightmap_rgb`/`hillshade` en `site_export.find_assets`.

## 3. Qué corre ahora mismo (en el PC de casa)

| Proceso | Cómo verlo / pararlo |
|---|---|
| Vigilante AppEEARS (`python -m app.extractors.appeears watch --interval 600 --build`) | `backend/data/cache/appeears/watch.log`; descarga, genera mapas y re-exporta `site.json` solo |
| Backend `uvicorn` en **100.70.153.87:8765** (Tailscale) | CORS vía `CORS_ORIGINS` |
| Frontend `next start` en **100.70.153.87:5180** (build con `NEXT_PUBLIC_API_URL=http://100.70.153.87:8765`) | recompilar para ver cambios |

Mandy lo ve desde el portátil por Tailscale. Puertos 3000/8000/8010 ocupados por otros servicios.

**AppEEARS:** 1/10 tareas descargadas (LST Lake Mead). Pendientes: Aletsch ×4 (nieve+LST), Doñana (NDVI, ET, LST),
`lake_mead_water` (MOD09A1 → área de agua y `year_water_<YYYY>.png`), `suspect_*` ×3 (MCD12Q1 cultivo/urbano).
**`APPEEARS_TOKEN` caduca dom 15 a las 14:45 UTC (15:45 Málaga)** → si algo sigue pendiente, `POST /api/login` de
nuevo y actualizar `.env` a mano (el hook impide a Claude escribir `.env`).

## 4. Decisiones pendientes de Mandy

1. Mostrar en Lake Mead el rango **54–84 %** (recomendado) o solo 84 %.
2. Qué se hace con el modo historia de Ale (la revisión la tiene Mandy; **no** está en el repo y no debe subirse).
3. Deploy público: dónde (Dokploy recomendado). De momento, local por Tailscale.
4. Render cinematográfico (Blender/PyVista) de los 3 casos para pitch/vídeo de 30 s.

## 5. Encargos en curso

- **Sesión `front`**: rediseño con taste (anti AI-slop, más visual), 3D como pieza estrella (terrain-RGB, hillshade,
  luz rasante, exageración), portada coherente que lleve a 3D y `/explore`. Rama `mandy/front-taste`. Me reporta a mí.
- Otra sesión (`earth-trend-detective-bf`) recibió las fuentes de presión humana (MCD12Q1, Black Marble 2012–24,
  INE Almonte, USBR consumo). Ojo: Las Vegas usa ~4 % del Colorado → no es el sospechoso de Lake Mead.

## 6. Investigador agente + capas — backend HECHO (sáb 14, ~19:00)

- `sites/<id>/layers.json` (`app/layers.py`, también lo escribe `site_export`): capa, fuente NASA + URL,
  leyenda (stops, rango, unidad), fechas, `analysed|visual_only`. Regenerar: `python -m app.layers --all`.
- Antes/después (`app/assets/beforeafter.py`): mediana MODIS true colour 2003 vs 2024, misma estación.
  **Solo Lake Mead** (se ve el lago encoger); Aletsch y Doñana excluidos (`SKIP`): a 250 m es un borrón.
- `POST /investigate` (`app/investigate/`), SSE. Body `{question, site_id}` o `{question, lat, lon}`.
  Eventos: `place` (tags del entorno) → `plan` (`source: llm|default`) → `step_start` / `step_done` |
  `step_failed` por paso → `done`. Pasos del menú: `land_cover` (MCD12Q1 vía GIBS, 2003 vs 2023, sin auth),
  `climate` (POWER), `water_storage` (GRACE + residuo), `then_and_now` (URLs GIBS del día más limpio),
  `soil_and_runoff` (GLDAS, lento); siempre cierra `explain` (narrativa validada). Los `why` del LLM con
  cifras se sustituyen por el texto del menú. Probado en real: Aral 13,5 s.
- Cada `step_done.result` trae `layer` para pintar: `wms` (cobertura), `footprint` (GRACE ~300 km), `point`.
- Falta en front: pantalla del investigador (consumir SSE con `fetch` + ReadableStream; `EventSource` no hace POST),
  pila de capas desde `layers.json`, cortina antes/después.
- Backend reiniciado en 100.70.153.87:8765 con `/investigate`; log en `backend/data/cache/uvicorn.log`.

## 6b. Diseño original del bloque (referencia)

**Investigador agente + capas.** El usuario elige sitio/punto y pregunta; el LLM arma un plan de 3–6 pasos
**solo con piezas de un menú cerrado** (salida estructurada); el código ejecuta y la UI enseña el avance y pinta la
capa de cada paso; narrativa validada; plan por defecto si falla el LLM.

- Precreado: los 3 casos completos (MODIS por píxel, residuo, sospechosos, vídeo); `layers.json` por sitio (fuente
  NASA, leyenda, fechas, `analysed|visual_only`); GRACE global (ya en disco); MODIS MCD12C1 global para etiquetar
  entorno; planes por defecto por entorno.
- En el momento, cualquier punto (< 10 s): entorno, plan LLM, POWER + barrido, GRACE + residuo, GIBS antes/después,
  NASADEM relieve. GLDAS (1–2 min) al final u opcional. MODIS por píxel: **no** en vivo.
- Backend (Mandy): `layers.json` + capas GIBS antes/después, etiquetador de entorno, `POST /investigate` con pasos en
  streaming (SSE), `/sweep` del punto con GRACE + residuo.
- Front: pila de capas con opacidad, línea de tiempo 2003–2024 común, cortina antes/después, leyenda con fuente
  NASA, pantalla del investigador paso a paso.

## 7. Otros pendientes (MANDY.md, domingo)

- Rueda de sospechosos con datos reales (MCD12Q1 al llegar; INE Almonte y USBR consumo ya).
- Serie temporal del residuo → `lineup.run_lineup` (accessor de ~10 líneas en `residual.py`).
- README en inglés con "Start here", sección NASA Data (cada recurso con su función real), declaración de IA,
  `LICENSE`, repo público antes de enviar, enlaces probados en ventana privada.
- Validación con Giovanni (captura) si da tiempo.

## 8. Trampas conocidas

- netCDF4/HDF5 no es thread-safe: `gather.py` lee las fuentes locales NetCDF en serie.
- AppEEARS `QC_Day` usa `_FillValue` 0 = "buena calidad": xarray lo vuelve NaN; se relee como 0.
- Tareas de Aletsch en tramos de años → subcarpetas `cache/appeears/aletsch/<y0-y1>/`.
- `next dev` no hidrata desde otra IP (`allowedDevOrigins`): usar build + `next start -H <ip>`.
- Hooks: `freno-peligro` bloquea escribir `.env` y `git push` a `main`.
- Tests aislados de claves reales de LLM (`backend/tests/conftest.py`).
