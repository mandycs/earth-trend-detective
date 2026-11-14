# Earth Trend Detective — La idea (interno)

> Documento interno en español. Resumen ejecutable en [`PLAN.md`](../PLAN.md). Explicación visual para mentores: [`mentor-explainer.html`](mentor-explainer.html).

## Pitch en una frase

> "Todo el mundo puede ver que su embalse se vacía. Nadie te dice cuánto es por el clima y cuánto no.
> Earth Trend Detective sí: con datos de NASA y el rigor de un científico, en dos minutos."

**EN:** *Is it the climate, or is it us?* Pick any place, discover what is changing, whether it is real, and how
much of it the climate does not explain.

## Problema

Los datos de NASA son públicos, pero investigarlos sigue siendo cosa de expertos:
1. Hay que saber **qué variable** pedir (hay cientos).
2. Hay que hacer **la estadística** (tendencia, significancia, estacionalidad, autocorrelación).
3. Hay que **cruzar variables** para separar clima de acción humana. Esto solo se hace en papers o a mano.

El enunciado del reto lo dice: la misma variable sube en una región y baja en otra aunque la mueva el mismo proceso.

## Solución

Una web con dos modos:
- **Modo historia (3D):** 3 casos resueltos con relieve real, capa de tendencia y línea de tiempo. Enseñan a investigar.
- **Modo explora (2D):** click en cualquier punto → diagnóstico en segundos.

El detective sigue 4 pasos:

| Paso | Pregunta del usuario | Qué hacemos |
|---|---|---|
| 1. Barrido | ¿Qué cambia aquí? | Todas las variables NASA aplicables al sitio, no solo la que sospechas |
| 2. Significancia | ¿Es real o casualidad? | MK Hamed-Rao + Sen, FDR, semáforo, "faltan ~N años" |
| 3. Residuo | ¿Es el clima? | Variable ~ drivers climáticos → tendencia de lo que el clima no explica |
| 4. Explicación | ¿Qué significa? | LLM redacta desde los números calculados; validador de cifras; RAG con fuentes |

## Cómo se eligen las variables

1. **Catálogo cerrado** (~10 en MVP, ~25 ideal) con metadatos: dataset, unidades, tags, dónde aplica, relaciones.
2. **Perfil de la región** (cobertura del suelo, clima, costa, nieve) filtra lo que no aplica.
3. **Intención del usuario** (opcional): LLM con salida estructurada → solo ids del catálogo.
4. **Barrido + FDR** ordena por cambio normalizado (σ/década).
5. **Grafo de relaciones** a mano (precip → humedad suelo → NDVI; T → nieve → caudal) para la narrativa coherente.

## Papel del LLM y del RAG

- **LLM:** traduce la pregunta a variables, redacta desde el JSON calculado, responde dudas de seguimiento.
  **Nunca** calcula, decide significancia ni atribuye causas. Validador comprueba cada cifra; si falla → plantilla.
- **RAG:** corpus curado (50–150 docs): fichas de datasets, papers de método, NASA Earth Observatory de los
  3 sitios y mecanismos generales. Convierte la pista en hipótesis **con fuente**. Sin RAG abierto sobre noticias.
- Mensaje: no "tenemos un chat", sino "IA que explica resultados verificados y nunca inventa una cifra".

## Modelo predictivo

No es el núcleo (el reto pide detectar y medir). Como extra si sobra tiempo: extrapolación de Sen con intervalo +
backtest + comparación con proyecciones NASA NEX-GDDP-CMIP6. Nada de deep learning.

## Research de antecedentes (resumen)

| Existe | Qué hace | Hueco |
|---|---|---|
| Giovanni, KNMI, AppEEARS | Series y tendencias de una variable | Saber qué pedir; expertos |
| **Climate Engine** | MK + Sen por píxel con máscara p-valor; series multivariable; endpoints de regresión | Una variable cada vez; el cruce clima/no clima lo hace un experto **a mano** (su tutorial de riberas) |
| Earth Copilot / Hydrology Copilot | NL sobre datos NASA (VEDA, NLDAS-3) | Encuentran datos; no diagnostican; acceso limitado |
| RESTREND, separación GRACE~precip | Método publicado clima vs no clima | Solo en papers; requiere programar |
| Show Your Stripes, NYT hometown | Calentamiento local para público | Solo temperatura; sin significancia ni causas |
| Space Apps anteriores | WMPGang 2024: visualización de series | Sin estadística |

**Conclusión:** no inventamos el método; **lo sacamos de los papers y lo ponemos en manos de cualquiera**,
automatizado, multivariable y explicado. No vendemos como nuevo: el mapa de tendencia con significancia ni el chat con datos NASA.

## Democratización, bien planteada

- Democratizar **el método**, no la gráfica: el usuario aprende a pensar como detective.
- Usuario con nombre: estudiante de 16 años, periodista local, técnico de ayuntamiento.
- Afirmación medible: "encuentra una tendencia real en su ciudad en < 2 min" → test con 3 personas.
- Barreras contra el mal uso como argumento: pista ≠ causa, "no se puede decir", "faltan N años".

## Limitaciones que decimos nosotros antes que el jurado

- El residuo es una **pista**, no una atribución: los factores omitidos acaban en él.
- Depende del periodo elegido (inicio/fin).
- Series cortas (SWOT, huecos GRACE/GRACE-FO) → aviso en vez de conclusión.
- Resoluciones distintas entre datasets → armonizar a una malla común.
