# Mandy (+ Claude) — Datos, estadística, backend, web 2D, IA, deploy

Plan general: [`PLAN.md`](../../PLAN.md) · Compañera: [`ALE.md`](ALE.md)

**Entregas a Ale:** `sites/<id>/` con PNGs reales + `site.json` (contrato en PLAN §6).
**Recibo de Ale:** guion y textos en inglés de cada caso para meter en `site.json`.

## Sáb 15:30–17:30 · Arranque
- [ ] Cuenta NASA Earthdata Login → token en `.env` (nunca en git)
- [ ] Esqueleto `backend/` (FastAPI) y `frontend/` (Next.js)
- [ ] `backend/catalog/variables.yaml`: 10 variables (id, dataset, banda, unidades, tags, aplica_a, relaciones)
- [ ] Extractor NASA POWER (sin auth) → primera serie mensual de prueba

## Sáb 18:00–23:00 · Motor
- [ ] Extractores AppEEARS (asíncrono → cachear) y Hydrology data rods
- [ ] Series de los 3 sitios en caché
- [ ] Deseasonalizar (anomalías mensuales)
- [ ] MK Hamed-Rao + Sen + IC (`pymannkendall`)
- [ ] FDR Benjamini-Hochberg + ranking σ/década + semáforo (`real` / `likely` / `unknown`)
- [ ] `/sweep`
- [ ] **Checkpoint 1 (23:00):** barrido + semáforo end-to-end en el sitio 1

## Sáb noche · Residuo y assets
- [ ] Residuo: regresión variable ~ drivers (precip, T, ET) → MK del residuo → % no climático (`/residual`)
- [ ] "Años necesarios para significancia" (`/years`)
- [ ] `heightmap.png`, `base.jpg`, `trend_<var>.png`, `year_<var>_<YYYY>.png` del sitio 1
- [ ] `site.json` real del sitio 1 → avisar a Ale

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
