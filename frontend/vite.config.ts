import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.dirname(fileURLToPath(import.meta.url))
const SITES_DIR = path.resolve(ROOT, '../sites')

/**
 * The story-mode assets live in the repo's top-level `sites/` folder, outside
 * the Vite root, because the data pipeline (Mandy) writes them there. This
 * plugin serves `/sites/*` in dev and copies the folder into `dist/sites` on
 * build, so the same URLs work in both modes without duplicating files.
 */
function sitesAssets(): Plugin {
  const MIME: Record<string, string> = {
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
  }
  return {
    name: 'sites-assets',
    configureServer(server) {
      server.middlewares.use('/sites', (req, res, next) => {
        const rel = decodeURIComponent((req.url ?? '/').split('?')[0]).replace(/^\/+/, '')
        const file = path.resolve(SITES_DIR, rel)
        if (!file.startsWith(SITES_DIR) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
          next()
          return
        }
        res.setHeader('Content-Type', MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream')
        res.setHeader('Cache-Control', 'no-cache')
        fs.createReadStream(file).pipe(res)
      })
    },
    writeBundle() {
      const out = path.resolve(ROOT, 'dist/sites')
      fs.rmSync(out, { recursive: true, force: true })
      fs.cpSync(SITES_DIR, out, {
        recursive: true,
        filter: (src) => !/\.(py|md)$/i.test(src),
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), sitesAssets()],
  server: { host: '127.0.0.1', port: 5180, strictPort: true },
  build: { target: 'es2022' },
})
