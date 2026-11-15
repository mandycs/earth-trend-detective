# Mandy (+ Claude) — Datos, estadística, backend, web 2D, IA, deploy

Plan general: [`PLAN.md`](PLAN.md) · Compañera: [`ALE.md`](ALE.md)

**Entregas a Ale:** `sites/<id>/` con PNGs reales + `site.json` (contrato en PLAN §6).
**Recibo de Ale:** guion y textos en inglés de cada caso para meter en `site.json`.

## Sáb 15:30–17:30 · Arranque
- [x] Cuenta NASA Earthdata Login → token en `.env` (nunca en git)
- [x] Esqueleto `backend/` (FastAPI) y `frontend/` (Next.js)
- [x] `backend/catalog/variables.yaml`: 10 variables (id, dataset, banda, unidades, tags, aplica_a, relaciones)
- [x] Extractor NASA POWER (sin auth) → primera serie mensual de prueba

## Sáb 18:00–23:00 · Motor
- [x] Extractores AppEEARS (asíncrono → cachear) y Hydrology data rods
- [x] Series de los 3 sitios en caché
- [x] Deseasonalizar (anomalías mensuales)
- [x] MK Hamed-Rao + Sen + IC (`pymannkendall`)
- [x] FDR Benjamini-Hochberg + ranking σ/década + semáforo (`real` / `likely` / `unknown`)
- [x] `/sweep`
- [x] **Checkpoint 1 (23:00):** barrido + semáforo end-to-end en el sitio 1

## Sáb noche · Residuo y assets
- [x] Residuo: regresión variable ~ drivers (precip, T, ET) → MK del residuo → % no climático (`/residual`)
- [x] "Años necesarios para significancia" (`/years`)
- [ ] `heightmap.png`, `base.jpg`, `trend_<var>.png`, `year_<var>_<YYYY>.png` del sitio 1
- [x] `site.json` real del sitio 1 → avisar a Ale

## Sáb noche · Notas de lo hecho
- Data rods retirado → GLDAS mensual vía Earthdata Cloud OPeNDAP.
- GRACE = señal regional (~300 km): en sitios snow/glacier no se da % no climático.
- GLDAS es modelo sin uso humano → nunca % no climático.
- Validación Lake Mead con USBR (no NASA): r = 0,70 en anomalías mensuales.
- Assets: heightmap NASADEM + base GIBS (MODIS / HLS 30 m) de los 3 sitios. Faltan trend/year PNG (esperan AppEEARS).

## Rueda de sospechosos (nuevo)
- [ ] Fuentes de presión humana por sitio (investigación en curso)
- [ ] Motor `stats/lineup.py`: cambios año a año, retardos 0–2, FDR, validación fuera de muestra, placebos
- [ ] Selección de drivers por validación cruzada (clima río arriba en Lake Mead, nieve en Aletsch)
- [ ] Extractores de 1–2 sospechosos por sitio + integración en `site.json`

## Dom 09:00–13:00 · Producto
- [ ] Modo explora: mapa + click → barrido POWER → semáforo (icono + texto, no solo color) + gráfica
- [ ] Estados de carga y errores que dicen qué hacer
- [ ] LLM: pregunta → ids (salida estructurada, enum)
- [ ] LLM: JSON → narrativa + **validador de cifras** (fallback a plantilla)
- [ ] RAG curado (fichas datasets, papers de método, NASA Earth Observatory de los 3 sitios)
- [ ] Assets + `site.json` de los sitios 2 y 3
- [ ] Validar 1 serie por sitio contra Giovanni (captura para la demo)

## Dom 13:00–16:00 · Cierre
- [ ] Deploy público + caché de los casos demo
- [ ] README en inglés con "Start here"
- [ ] Página Project: NASA Data (recurso + función), referencias, declaración de IA
- [ ] **Repo a público** antes de enviar
- [ ] Probar enlaces en ventana privada
- [ ] Submit for Judging (primera versión) y confirmar
