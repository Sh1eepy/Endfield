import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// assets/ 目录（字体/角色素材）通过 publicDir 原样提供：
// dev 时访问 /assets/...，build 时复制到 dist/assets/...，路径与 FastAPI 托管一致。
export default defineConfig({
  plugins: [react()],
  publicDir: 'assets',
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
