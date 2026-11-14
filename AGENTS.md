# Earth Trend Detective — notas para agentes

Hackathon NASA Space Apps 2026 (Málaga). Equipo de dos: **Mandy** (datos, estadística, backend, web 2D, LLM/RAG,
deploy) y **Ale** (3D, historia, copy, demo, pitch).

**Documentos que mandan**, en este orden:
1. [`PLAN.md`](PLAN.md) — plan general, calendario, criterios del jurado, recortes.
2. [`docs/team/ALE-PLAN.md`](docs/team/ALE-PLAN.md) — mi parte, hora a hora, con puertas y plan B.
3. [`docs/team/MANDY.md`](docs/team/MANDY.md) — la otra mitad.
4. [`docs/UX-CHECKLIST.md`](docs/UX-CHECKLIST.md) — lo que hay que pasar antes de enseñar la demo.

## Reglas del proyecto

- Documentos internos **en español**; todo lo que se entrega (README, página Project, demo, slides, UI, textos
  de los casos) **en inglés**.
- **Ninguna cifra inventada, en ningún sitio.** En la UI, toda cifra sale de `sites/<id>/site.json`. Si un dato
  no está, no se escribe la frase.
- Los assets de `sites/_example/` son sintéticos y están marcados en pantalla. No enseñarlos como medición.
- El residuo clima/no clima es **una pista, no una atribución**. Nada de "proof" ni "cause".
- Sin logos de NASA en contenido generado. Sin menores identificables.

## Comandos

```bash
# web (modo historia 3D)
cd frontend && npm run dev          # http://127.0.0.1:5180
cd frontend && npm run build        # type-check + bundle + copia ../sites a dist/sites

# regenerar los assets sintéticos del caso de muestra
uv run --python 3.11 --with pillow --with numpy python sites/_example/make_fake_assets.py
```

Stack fijado: React 18.3 · @react-three/fiber 8.17 · three 0.169 · Vite 7. **No actualizar versiones durante
el hackathon.**

## Contrato de datos del modo historia

Mandy produce `sites/<id>/` con `heightmap.png`, `base.jpg`, `trend_<var>.png`, `year_<var>_<YYYY>.png` y
`site.json`; Ale consume. El contrato completo está en [`frontend/README.md`](frontend/README.md) y los tipos
en `frontend/src/story/types.ts`. Un caso incompleto (sin capa de tendencia, sin serie anual) debe verse
honesto, nunca roto.
