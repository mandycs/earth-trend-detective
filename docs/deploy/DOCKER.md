# Docker: dos servicios (api + web)

Interno. Alibi / Earth Trend Detective se despliega como **dos contenedores con dos dominios**:

| Servicio | Dockerfile | Puerto dentro | Healthcheck | Local (compose) |
|---|---|---|---|---|
| `api` (FastAPI, uv) | `backend/Dockerfile` | 8000 | `GET /health` → `{"status":"ok"}` | `http://127.0.0.1:8777` |
| `web` (Next 16 standalone) | `frontend/Dockerfile` | 3000 | `GET /` → 200 | `http://127.0.0.1:5190` |

En los dos el **contexto de build es la raíz del repo** (no `backend/` ni `frontend/`): la API necesita `sites/` y
la web la necesita para el `prebuild` (`scripts/sync-sites.mjs` copia `../sites` a `public/sites`; además se copia
`backend/data/recordings`). El `.dockerignore` de la raíz deja fuera `node_modules`, `.next`, `.venv`,
`backend/data/cache`, `backend/data/detective`, `video/`, `docs/`, `.claude`, `.superpowers`, `.git` y todo `.env*`.

## Correr en local

```bash
cp .env.docker.example .env.docker        # rellenar una clave (o pasarla desde la shell, abajo)
docker compose up -d --build
curl -s http://127.0.0.1:8777/health      # {"status":"ok"}
open http://127.0.0.1:5190
docker compose down                       # los volúmenes se quedan (no usar -v)
```

Pasar la clave de OpenRouter sin escribirla en ningún fichero del repo:

```bash
export OPENROUTER_API_KEY="$(cat ~/.secrets/openkey)"
printf 'services:\n  api:\n    environment:\n      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}\n' \
  | docker compose -f docker-compose.yml -f - up -d
```

Prueba SSE de una investigación corta:

```bash
curl -N -X POST http://127.0.0.1:8777/detective -H 'Content-Type: application/json' \
  -d '{"question":"Has it gotten hotter here?","lat":36.1,"lon":-114.7}'
# event: place / thinking / tool_start / tool_done / map / board / answer / done
```

Sin clave, la respuesta es un único `event: error` con el mensaje de "sin modelo" (es lo esperado).

Si `docker compose up` falla con *all predefined address pools have been fully subnetted* (pasa en esta
máquina: hay demasiadas redes Docker), añadir `network_mode: bridge` a los dos servicios en un override; no hace
falta red compartida porque web y api son orígenes separados y el navegador habla con la API directamente.

## Variables

**API (runtime, nunca en la imagen):**

| Variable | Notas |
|---|---|
| `OPENROUTER_API_KEY` o `LLM_API_KEY` | Una de las dos. `LLM_API_KEY` (Anthropic directo) gana si están las dos. Sin ninguna: narrador en modo plantilla y `/detective` devuelve `error`. |
| `DETECTIVE_MODEL` | Opcional. **Tiene que ir en el formato del proveedor activo** (`anthropic/claude-sonnet-5.5` en OpenRouter, `claude-sonnet-5-5` en Anthropic). Ver `backend/app/detective/README.md`. |
| `CORS_ORIGINS` | Coma-separado, **el dominio exacto de la web** (`https://alibi.example`). Sin él solo valen los orígenes de desarrollo. |
| `DETECTIVE_DB` | Ya viene en la imagen: `/app/backend/data/detective/detective.sqlite` (dentro del volumen). |
| `LANGSMITH_TRACING`, `LANGCHAIN_TRACING_V2` | Fijadas a `false` en la imagen. **No activarlas**: mandarían prompts, resultados y coordenadas a un tercero. |
| `NASA_TOKEN`, `APPEEARS_TOKEN` | Solo si hay que descargar datos que no estén ya en la caché (GRACE, GLDAS, NASADEM, AppEEARS). Los casos resueltos funcionan con la caché sembrada. |
| `DETECTIVE_MAX_TOOL_CALLS`, `DETECTIVE_MAX_SECONDS` | Opcionales. |

Rutas que el código resuelve desde la "raíz del repo" (`Path(__file__).parents[...]`): en la imagen la raíz es
`/app` y el proyecto `/app/backend`, así que `sites/` está en `/app/sites` y `catalog/` en `/app/backend/catalog`
(los dos horneados). `llm.py` y los extractores hacen `load_dotenv(/app/.env)`: el fichero no existe en la imagen
y no pasa nada, las variables llegan por env. `OPENROUTER_KEY_FILE` por defecto apunta a `~/.secrets/openkey` del
usuario `app`, que no existe: en contenedor usar `OPENROUTER_API_KEY` (o montar un secreto como fichero y apuntar
`OPENROUTER_KEY_FILE` a él).

**Web (build arg):**

| Build arg | Notas |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL pública de la API (`https://api.alibi.example`, sin barra final). **Se incrusta en el JS al hacer `next build`**: cambiar el dominio de la API exige reconstruir la imagen web. El build falla si no se pasa. |

### Acoplamiento CORS ↔ NEXT_PUBLIC_API_URL

Son las dos caras de lo mismo y van juntas en cada cambio de dominio:

- `web` se construye con `NEXT_PUBLIC_API_URL=https://<dominio-api>`.
- `api` arranca con `CORS_ORIGINS=https://<dominio-web>`.

Si falla uno, el navegador bloquea las llamadas (narrador, barrido del mapa, detective) sin mensaje visible.
Comprobar con
`curl -si -X OPTIONS https://<dominio-api>/detective -H 'Origin: https://<dominio-web>' -H 'Access-Control-Request-Method: POST' | grep -i access-control-allow-origin`.

## Volúmenes

| Volumen | Montaje | Qué guarda |
|---|---|---|
| caché | `/app/backend/data/cache` | Descargas NASA: fichero global GRACE (`.nc`), paquetes AppEEARS, GLDAS, NASADEM, POWER, USBR. ~130 MB en local. |
| detective | `/app/backend/data/detective` | SQLite (checkpointer + store, WAL). **Un solo réplica** de la API: SQLite no se comparte entre contenedores. |

Los directorios existen en la imagen con dueño `app` (uid 10001), así que un volumen nuevo hereda los permisos.

### Sembrar la caché (necesario para los casos resueltos)

Sin caché, los casos resueltos intentan descargar de NASA (necesitan tokens y tardan mucho). Copiar la caché
local al volumen una vez:

```bash
# local (volumen de compose: etd_etd-cache)
docker run --rm -v etd_etd-cache:/dst -v "$PWD/backend/data/cache:/src:ro" alpine \
  sh -c 'cp -a /src/. /dst/ && rm -f /dst/*.log && chown -R 10001 /dst'

# servidor (desde la máquina con la caché; NOMBRE_VOLUMEN = el que tenga el servicio api)
tar -C backend/data/cache --exclude='*.log' -cz . \
  | ssh <servidor> 'docker run -i --rm -v NOMBRE_VOLUMEN:/dst alpine sh -c "tar -xz -C /dst && chown -R 10001 /dst"'
```

Hacerlo con la API parada o justo antes del primer arranque. Redesplegar no borra el volumen.

## Despliegue en Dokploy (dos aplicaciones, un dominio cada una)

Crear **dos Applications** desde el mismo repo/rama, tipo de build **Dockerfile**:

**api**
- Build path / contexto: `.` (raíz). Dockerfile: `backend/Dockerfile`.
- Environment: `OPENROUTER_API_KEY` (o `LLM_API_KEY`), `CORS_ORIGINS=https://<dominio-web>`, y opcionales
  (`DETECTIVE_MODEL`, tokens NASA). Nada de secretos como build args.
- Mounts: volumen → `/app/backend/data/cache`; volumen → `/app/backend/data/detective`.
- Domain: `api.<dominio>` → container port **8000**, HTTPS.
- Healthcheck: el del Dockerfile (`/health`). Réplicas: 1.

**web**
- Build path: `.` (raíz). Dockerfile: `frontend/Dockerfile`.
- Build args: `NEXT_PUBLIC_API_URL=https://api.<dominio>`.
- Sin variables de runtime ni volúmenes.
- Domain: `<dominio>` → container port **3000**, HTTPS.
- Healthcheck: el del Dockerfile (`GET /`).

Orden: primero la API (y sembrar la caché), luego la web.

## SSE detrás de Traefik

`/detective` (y `/investigate`) responden `text/event-stream` con `Cache-Control: no-cache` y
`X-Accel-Buffering: no`. Traefik no bufferiza respuestas por defecto (solo si se añade el middleware `buffering`,
que **no** hay que poner en la API) y vacía los eventos según llegan: no hace falta configuración extra.

Tiempos: en Traefik v3 el `readTimeout` del entrypoint (60 s por defecto) aplica a leer la *petición*, no a la
respuesta; `writeTimeout` es 0 (sin límite) e `idleTimeout` 180 s. La API **no manda keepalives**: entre dos
eventos puede haber silencio largo si una herramienta descarga datos (GRACE, AppEEARS) con la caché vacía. Con la
caché sembrada los huecos son de segundos. Si hay Cloudflare con proxy delante, su límite es ~100 s sin datos:
sembrar la caché o desactivar el proxy para el subdominio de la API.

## Tamaños (build local, 2026-11-15)

- `etd-api`: ~1.35 GB (pila científica: numpy, scipy, xarray, netCDF4, h5py, matplotlib, statsmodels).
- `etd-web`: ~420 MB (Node 24 slim + standalone + ~64 MB de `public/sites`).
