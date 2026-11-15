# Earth Trend Detective — Plan de trabajo (interno)

> NASA Space Apps Challenge 2026 · Málaga · Reto: **Be An Earth System Trend Detective!** (Advanced)
> Equipo: **Mandy** (+ Claude) y **Ale** · Tareas por persona: [`docs/team/MANDY.md`](MANDY.md) · [`docs/team/ALE.md`](ALE.md)
>
> ⚠️ Documento interno en español. Todo lo que se entrega (README, página Project, demo, slides, UI) va **en inglés**.

---

## 1. Fechas que mandan

| Cuándo | Qué |
|---|---|
| Sáb 14 · 09:00 | Inicio oficial del desarrollo |
| Sáb 14 · 17:30–18:00 | Revisión de organización: llevar la idea clara |
| Dom 15 · 09:00–16:00 | Trabajo final + mentoría + **puesto UX (Eliana Crivaro)** |
| **Dom 15 · 16:00** | **Congelado** (corte real nuestro) |
| Dom 15 · 16:30–17:15 | Prueba técnica del pitch |
| Dom 15 · 17:30–19:00 | Pitches |
| **Dom 15 · antes de 23:59** | **Submit for Judging** (cierre oficial NASA) |

> Pitch local: las guías se contradicen (2–3 min o vídeo de 30 s; 2–3 preguntas). **Confirmar con la organización.**

## 2. La idea en una frase

**"Is it the climate, or is it us?"** Una web donde cualquier estudiante elige un lugar y descubre qué está
cambiando allí, si el cambio es real (estadísticamente) y cuánto **no** lo explica el clima, con datos de NASA y en lenguaje llano.

## 3. Qué aportamos (y qué NO vendemos como nuevo)

| Ya existe | Quién | Qué le falta |
|---|---|---|
| Series y tendencias de una variable | Giovanni, KNMI, AppEEARS | Hay que saber qué pedir; para expertos |
| Mapa Mann-Kendall + Sen por píxel con máscara de p-valor | Climate Engine | Una variable cada vez; el cruce entre variables solo a mano (tutoriales) |
| Chat en lenguaje natural sobre datos NASA | Earth Copilot / Hydrology Copilot | Encuentra datos; no diagnostica |
| Separar tendencia climática vs no climática (residuo) | Papers: RESTREND, GRACE~precip | Solo en literatura, requiere programar |

**Innovación:** automatizar y explicar al público el razonamiento que hoy hacen los expertos a mano:
1. **Barrido automático** de todas las variables del sitio + corrección FDR.
2. **Significancia honesta**: MK Hamed-Rao, semáforo "real / probable / no se puede decir", "faltan ~N años".
3. **Residuo clima vs no clima** cuantificado ("el X % no lo explica el clima").
4. **Explicación en lenguaje llano** con LLM verificado (no inventa cifras) + RAG con fuentes.

Siempre **pista, no atribución causal**.

## 4. Jurado local y cómo les hablamos

No hay ningún científico del clima. **Menos jerga, más impacto y demo.**

| Jurado | Perfil | Qué destacar |
|---|---|---|
| César Trujillo (TeamLabs) | Inversión, emprendimiento | Impacto, usuarios (institutos, periodistas, ayuntamientos), siguiente paso |
| Pedro Manjón (Atech) | Tecnología, IA, ciberseguridad | LLM verificado que nunca inventa cifras |
| Carmen H. Ledesma (42 Málaga) | Educación, comunidad | "Convierte a cualquier estudiante en detective" |
| Carlos Pérez del Pulgar (UMA) | Robótica espacial, ESA | Datos de satélite y rigor |
| Lucía Pardo (Málaga Jam) | Videojuegos, prototipado | El 3D y la interacción |

Criterios (1–5): **Impacto · Creatividad · Validez · Relevancia (recurso NASA con función real) · Presentación.**

## 5. Producto

### Modo historia (3D) — 3 casos resueltos
| Sitio | Historia | Variables clave | Tipo |
|---|---|---|---|
| Lago Mead (EE. UU.) | El embalse se vacía | GRACE↓, agua↓, precipitación (no signif.) | No climático dominante |
| Glaciar Aletsch (Alpes) | Nieve/hielo en retroceso | Cobertura nieve↓, LST↑ | Climático dominante |
| **Por decidir**: Doñana / Rondônia / algo de Málaga | Humedal, deforestación o sequía local | NDVI, LST, ET, GRACE | No climático |

> Un caso cercano (Doñana o Málaga) conecta mejor con un jurado local. Comprobar con datos que la señal es clara.

### Modo explora (2D)
Click en cualquier punto → barrido de variables de clima (NASA POWER, inmediato) → semáforo + explicación.

### Requisitos UX (guía del puesto UX de Málaga)
- Propósito a primera vista: título claro, una frase, **un** botón principal.
- **Nunca solo color**: el semáforo y la paleta sube/baja llevan icono + texto (`↑ Real`, `↓ Real`, `? Can't tell yet`). Contraste ≥ 4,5:1.
- Estados del sistema: "Analyzing…", errores que dicen qué hacer, nada de pantallas mudas.
- Texto ≥ 16 px, zonas táctiles ≥ 44 px, funciona en móvil.
- UI en inglés.

## 6. Arquitectura

```
frontend/  Next.js + MapLibre + Plotly + react-three-fiber
   │
   ▼
backend/   FastAPI
   ├─ /profile   → ficha región → variables aplicables
   ├─ /sweep     → series mensuales → deseasonalizar → MK Hamed-Rao + Sen
   │               → FDR Benjamini-Hochberg → ranking σ/década → semáforo
   ├─ /residual  → regresión variable ~ drivers climáticos → MK del residuo → % no climático
   ├─ /years     → años de datos necesarios para significancia
   ├─ /explain   → LLM: pregunta→ids (enum) · JSON→narrativa · validador de cifras · RAG
   └─ /sites/<id>→ assets precalculados del modo historia
backend/catalog/variables.yaml  ·  backend/rag/ (50-150 docs curados)
sites/<id>/                      ·  assets del modo historia (contrato abajo)
```

### Fuentes de datos
| Fuente | Uso | Auth |
|---|---|---|
| NASA POWER API | Clima (T, precip, radiación) — modo explora y plan B | No |
| AppEEARS | MODIS por área (NDVI, LST, ET, nieve) | Earthdata Login |
| Hydrology data rods (GES DISC) | GLDAS/NLDAS: humedad suelo, ET, escorrentía | Earthdata Login |
| GRACE / GRACE-FO | Almacenamiento total de agua | Earthdata Login |
| Giovanni · NOAA CDO · KNMI | **Validación** | — |

Secretos (token Earthdata, API key LLM) en `.env` (ver `.env.example`), **nunca** en el repo.

### Contrato del modo historia (Mandy produce → Ale consume)
```
sites/<id>/heightmap.png          # DEM (NASADEM/SRTM) normalizado, 16-bit si es posible
sites/<id>/base.jpg               # textura satélite
sites/<id>/trend_<var>.png        # Sen por píxel, divergente, no signif. atenuado
sites/<id>/year_<var>_<YYYY>.png  # anomalía anual para la línea de tiempo
sites/<id>/site.json              # bbox, exageración vertical, variables, veredictos, textos, fuentes
```
Ejemplo con datos falsos para empezar ya: [`sites/_example/site.json`](../../sites/_example/site.json).

## 7. Reparto

| | Mandy (+ Claude) | Ale |
|---|---|---|
| Foco | Datos, estadística, backend, web 2D, LLM/RAG, deploy | 3D, historia de los 3 casos, copy en inglés, demo (slides/vídeo), pitch, página Project |
| Entrega a la otra persona | PNGs + `site.json` reales | Guion y textos de cada caso para meter en `site.json` |

> Si Ale no domina three.js: Claude escribe la escena 3D desde el lado de Mandy y Ale se queda con guion,
> copy, validación en Giovanni, demo, pitch y página Project.

## 8. Calendario (hora local)

| Cuándo | Mandy (+ Claude) | Ale |
|---|---|---|
| Sáb 15:30–17:30 | Earthdata, repo, `variables.yaml`, primer extractor (POWER) | Elegir 3er sitio, bocetos de pantallas, escena 3D con `_example` |
| Sáb 17:30–18:00 | **Revisión con organización** (ambos) | |
| Sáb 18:00–23:00 | Series de los 3 sitios + motor MK/Sen/FDR + `/sweep` | Terreno + capa de tendencia + timeline con datos falsos |
| **Sáb 23:00** | **Checkpoint 1**: barrido + semáforo funcionando end-to-end en 1 sitio | |
| Sáb 23:00–cierre noche | Residuo + PNGs reales del sitio 1 | Guion y copy en inglés de los 3 casos |
| Dom 09:00 | **Checkpoint 2 / CORTE 3D**: si el 3D no va con el sitio 1 real → modo historia en mapas 2D animados | |
| Dom 09:00–13:00 | Modo explora · LLM narrador + validador · RAG · PNGs sitios 2 y 3 | Integrar sitios 2 y 3 · pulido · **puesto UX** · borrador de slides |
| Dom 13:00–15:00 | Deploy público + caché · README "Start here" · NASA Data / IA en la página Project | Demo (≤7 slides o ≤30 s) · resumen 50–200 palabras · **test con 3 personas** |
| Dom 15:00–16:00 | **Congelar** · Submit for Judging (primera versión) | Ensayo del pitch |
| Dom 16:30 / 17:30 | Prueba técnica / **pitch** | |
| Dom antes de 23:59 | Si algo cambió: Save Progress + **volver a Submit** + confirmar | |

## 9. Checklist de entrega (todo en inglés)
- [ ] Todos registrados, aceptados en Málaga e incorporados al equipo
- [ ] Nombre + resumen 50–200 palabras (mapa del proyecto, no eslogan)
- [ ] Project Demo: **un** enlace público, ≤ 7 diapositivas (portada incluida) **o** vídeo ≤ 30 s
- [ ] Final Project: repo/web **públicos** con "Start here" → ⚠️ el repo nace privado: **hacerlo público antes de enviar**
- [ ] Descripción detallada: qué hace, cómo, método, **construido / simulado / futuro**, limitaciones
- [ ] NASA Data: recurso, enlace y **función real** de cada uno
- [ ] Otras referencias (papers, Climate Engine, librerías) y licencias
- [ ] Declaración de IA (Claude para programar, LLM en el producto) y marcado de contenido generado
- [ ] Sin logos NASA en contenido generado · sin menores identificables
- [ ] Enlaces probados en ventana privada
- [ ] **Submit for Judging** + confirmación visible

## 10. Recortes si vamos tarde (en este orden)
1. RAG → plantilla + LLM sin fuentes externas
2. 3D → mapas 2D animados
3. Mapa por píxel → solo series por región
4. 3er sitio → 2 sitios

**Nunca se recorta:** barrido + significancia + residuo + explicación verificada.

## 11. Riesgos
| Riesgo | Mitigación |
|---|---|
| AppEEARS lento | Precalcular y cachear los 3 sitios primero |
| LLM inventa cifras | Solo redacta desde JSON; validador; temperatura baja |
| Crítica estadística | Hamed-Rao, deseasonalizar, FDR, cautelas visibles |
| Residuo ≠ causa | Lenguaje de "pista"; factores omitidos van al residuo; depende del periodo |
| Series cortas | Aviso "series too short" / "N more years needed" |
| Daltonismo | Icono + texto en cada estado, no solo color |

## 12. Preguntas que nos harán (ensayar respuesta corta)
- ¿Dónde interviene el recurso NASA? → en cada serie del barrido y en el residuo; sin NASA no hay producto.
- ¿Qué funciona hoy y qué falta? → tabla construido / simulado / futuro.
- ¿Qué comprobación respalda la conclusión? → validación con Giovanni + estación CDO.
- ¿Principal limitación? → el residuo es una pista, no una causa.
- ¿Qué decisión aporta más valor? → automatizar el cruce entre variables que Climate Engine deja a mano.

## 13. Referencias
- Reto — https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/
- RESTREND fenológico — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6263966/
- RESTREND norte de China — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6651126/
- Precipitation vs non-precipitation water storage trends (China) — https://ui.adsabs.harvard.edu/abs/2023WRR....5933261Z
- Climate-induced groundwater depletion in GRACE — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6411996/
- Climate Engine Mann-Kendall endpoints — https://www.climateengine.org/apis/mapidEndpoints/
- Climate Engine tutorial riberas — https://www.climateengine.org/applications/riparian-restoration-outcomes/
- Earth Copilot — https://blogs.microsoft.com/blog/2024/11/14/from-questions-to-discoveries-nasas-new-earth-copilot-brings-microsoft-ai-capabilities-to-democratize-access-to-complex-data/
- Hydrology Copilot — https://www.nextgov.com/digital-government/2025/12/nasa-and-microsoft-finalize-tool-track-earths-water-changes/410238/
