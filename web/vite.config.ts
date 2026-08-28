import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const assetsDir = path.join(__dirname, 'assets')

// 静态资源服务：dev 模式由 vite 中间件直接服务 web/assets，build 时复制到 dist/assets。
// 这样代码里所有 /assets/... 路径在 dev / build / FastAPI 托管三种模式下都一致。
const MIME: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
}

function assetsPlugin() {
  return {
    name: 'endfield-assets',
    configureServer(server: { middlewares: { use: (fn: (req: any, res: any, next: any) => void) => void } }) {
      server.middlewares.use((req: any, res: any, next: any) => {
        const url = String(req.url || '').split('?')[0]
        if (!url.startsWith('/assets/')) return next()
        const rel = url.replace(/^\/assets\//, '')
        const file = path.join(assetsDir, rel)
        // 防目录穿越：解析后必须仍在 assetsDir 内
        if (!file.startsWith(assetsDir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
          res.statusCode = 404
          res.end('not found')
          return
        }
        res.setHeader('Content-Type', MIME[path.extname(file).toLowerCase()] || 'application/octet-stream')
        res.setHeader('Cache-Control', 'public, max-age=3600')
        fs.createReadStream(file).pipe(res)
      })
    },
    closeBundle() {
      fs.cpSync(assetsDir, path.join(__dirname, 'dist', 'assets'), { recursive: true })
    },
  }
}

export default defineConfig({
  plugins: [react(), assetsPlugin()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
