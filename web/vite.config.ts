import fs from 'node:fs'
import type { ServerResponse } from 'node:http'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, type Connect, type Plugin, type PreviewServer, type ViteDevServer } from 'vite'

const dataFiles: Record<string, { path: string; missing: string }> = {
  '/objects.json': {
    path: fileURLToPath(new URL('../data/out/objects.json', import.meta.url)),
    missing: 'objects.json not found. From the repo root: uv run python pipeline/build_objects.py',
  },
  '/leo_shells.json': {
    path: fileURLToPath(new URL('../data/out/leo_shells.json', import.meta.url)),
    missing: 'leo_shells.json not found. From the repo root: uv run python pipeline/leo_shells.py',
  },
}

function sendObjects(req: Connect.IncomingMessage, res: ServerResponse, next: Connect.NextFunction) {
  const url = req.url?.split('?')[0] ?? ''
  const file = dataFiles[url]
  if (!file) {
    next()
    return
  }
  if (!fs.existsSync(file.path)) {
    res.statusCode = 404
    res.setHeader('Content-Type', 'text/plain; charset=utf-8')
    res.end(file.missing)
    return
  }
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'no-cache')
  fs.createReadStream(file.path).pipe(res)
}

function serveObjects(): Plugin {
  const attach = (server: ViteDevServer | PreviewServer) => {
    server.middlewares.use(sendObjects)
  }
  return {
    name: 'serve-objects',
    configureServer: attach,
    configurePreviewServer: attach,
  }
}

export default defineConfig({
  plugins: [react(), serveObjects()],
  worker: { format: 'es' },
  server: {
    fs: {
      allow: [fileURLToPath(new URL('.', import.meta.url)), fileURLToPath(new URL('..', import.meta.url))],
    },
    proxy: {
      '/ask': 'http://127.0.0.1:8000',
      '/speak': 'http://127.0.0.1:8000',
      '/place': 'http://127.0.0.1:8000',
      '/rank': 'http://127.0.0.1:8000',
      '/shells': 'http://127.0.0.1:8000',
      '/close_approaches': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/listen': 'http://127.0.0.1:8000',
      '/imagine': 'http://127.0.0.1:8000',
    },
  },
})
