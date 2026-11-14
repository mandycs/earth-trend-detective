# Guion y copy de los tres casos (inglés)

> Para pegar en cada `sites/<id>/site.json`. Campos: `name`, `country`, `steps[3]`, `narrative`,
> `caveats`, y `label` de cada variable.
>
> **Reglas aplicadas** (§5 de `ALE-PLAN.md`): frases ≤ 18 palabras · cero jerga (Mann-Kendall, Sen, FDR,
> p-value, residual, anomalía) · **cero cifras sueltas**: los números los pinta la UI desde el JSON, no el
> texto · voz activa, presente, segunda persona · nunca "proof", "cause", "because of humans" · "clue",
> "consistent with", "does not explain".

---

## 1 · Lake Mead (Estados Unidos) — *sobre todo nosotros, en parte el clima*

```jsonc
{
  "name": "Lake Mead",
  "country": "United States",
  "steps": [
    {
      "title": "What is changing here?",
      "body": "The reservoir behind Hoover Dam has been shrinking for two decades. Press play and watch the waterline move."
    },
    {
      "title": "Is it real, or is it chance?",
      "body": "The drop is far bigger than the year-to-year wobble. It is not a straight line either: a wet winter put water back in 2023."
    },
    {
      "title": "Is it the climate?",
      "body": "Rainfall here shows no clear trend. Most of the loss comes from what we take out, not from what the sky fails to send."
    }
  ],
  "narrative": "Seven states hold rights to more water than the river carries. A warmer atmosphere takes its share of the flow. The rest of the gap is us.",
  "caveats": [
    "One wet year does not undo a two-decade decline.",
    "The leftover share is a clue, not proof of who is responsible."
  ]
}
```

**Por qué está escrito así:** el caso tiene trampa. En 2023–24 el embalse **recuperó** nivel, y una tendencia
que lo esconda es cherry-picking. Por eso el paso 2 lo dice antes de que lo diga el jurado. Y el paso 3 no
acusa a la sequía: señala el reparto de derechos, que es el hallazgo del paper.

**Lo que NO se dice en la UI:** "megasequía", "cambio climático causó", "16,5 MAF". Los derechos de agua son
un dato del pitch, no de la pantalla.

---

## 2 · Aletsch (Suiza) — *esto sí es el clima*

```jsonc
{
  "name": "Aletsch",
  "country": "Switzerland",
  "steps": [
    {
      "title": "What is changing here?",
      "body": "The largest glacier in the Alps is shorter than it was a century ago. The pale band on the rock shows where the ice used to reach."
    },
    {
      "title": "Is it real, or is it chance?",
      "body": "People have walked out and measured this glacier almost every year since the 1870s. The retreat is steady and large, not one hot summer."
    },
    {
      "title": "Is it the climate?",
      "body": "Nothing is pumped here. No reservoir, no irrigation, no change in land use. Temperature is the driver, and the ice answers."
    }
  ],
  "narrative": "Some changes are not our doing, and it matters that we say so. A detector that blames people for everything is not a detector.",
  "caveats": [
    "A retreating glacier is not a water-supply forecast.",
    "Ice loss here is slow enough to see only decade by decade."
  ]
}
```

**Por qué está escrito así:** es el **caso de control**. Si los tres casos acabaran en "es culpa humana", el
jurado (y cualquiera) desconfiaría del método. Este demuestra lo contrario, y la frase del `narrative` es la
que uso en el pitch.

---

## 3 · Doñana (España) — *sobre todo nosotros, amplificado por la sequía*

```jsonc
{
  "name": "Doñana",
  "country": "Spain",
  "steps": [
    {
      "title": "What is changing here?",
      "body": "One of Europe's great wetlands is drying from below. Its ponds are not simply waiting for rain."
    },
    {
      "title": "Is it real, or is it chance?",
      "body": "From space, most ponds now flood less than rain and heat alone would allow. The gap is measured, not guessed."
    },
    {
      "title": "Is it the climate?",
      "body": "The park is protected. The aquifer that feeds it is not. Water pumped for berries and for a beach town never reaches the ponds."
    }
  ],
  "narrative": "One lagoon dried twice in fifty years, then three years in a row. Rain explains part of that. The pumps explain the rest.",
  "caveats": [
    "The aquifer reaches far beyond the park boundary.",
    "Drought makes it worse; it does not start it."
  ]
}
```

**Por qué está escrito así:** la frase *"the park is protected, the aquifer is not"* es el caso entero en 12
palabras. Y *"twice in fifty years, then three years in a row"* es el gancho emocional, medido y con fuente
(research-donana.md §3). Es la frase que se dice en el pitch mientras se pulsa play.

---

## Etiquetas de variables (≤ 4 palabras, sin siglas)

| id | label | Nota |
|---|---|---|
| `grace_tws` | Total water stored | no decir "GRACE" en la etiqueta |
| `precip` | Rainfall | |
| `lst` | Surface temperature | |
| `ndvi` | Green vegetation | no decir "NDVI" |
| `snow_cover` | Snow cover | |
| `water_extent` | Open water | para Doñana y Mead |
| `soil_moisture` | Soil moisture | |
| `et` | Water evaporating | en vez de "evapotranspiración" |

## Frases que no se usan nunca (lista negra de la UI)

`proof` · `cause` · `because of humans` · `anthropogenic` · `significant trend` (sin explicar) ·
`p-value` · `Mann-Kendall` · `Sen's slope` · `residual` · `anomaly` · `attribution` · `correlation` ·
`data-driven insights` · `revolutionary` · `game-changing`

## Glosario de traducción (concepto → frase de la calle)

| Concepto interno | Lo que se escribe |
|---|---|
| p < 0,001 | "a pattern this steady would almost never happen by chance" |
| no significativo | "can't tell yet" |
| años necesarios | "about N more years of data would be needed" |
| residuo | "the part rain and heat do not explain" |
| FDR / múltiples variables | "we tested several variables at once, and corrected for that" |
| atribución | "a clue, not a verdict" |
