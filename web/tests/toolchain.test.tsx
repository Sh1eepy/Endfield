// @vitest-environment node
import { afterAll, beforeAll, expect, test } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import { fileURLToPath } from 'node:url'
import type { AddressInfo } from 'node:net'

let server: ViteDevServer | undefined
let base: string

beforeAll(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    server: { host: '127.0.0.1', port: 0, strictPort: true, open: false },
    logLevel: 'error',
  })
  await server.listen()
  const address = server.httpServer!.address() as AddressInfo
  base = `http://127.0.0.1:${address.port}`
}, 20000)

afterAll(async () => {
  if (!server) return
  // 等待模块预转换完成，避免关闭时与依赖预打包取消流程互相等待。
  await server.waitForRequestsIdle()
  server.httpServer?.closeIdleConnections()
  await server.close()
}, 20000)

test('dev server transforms the HTML entry', async () => {
  const response = await fetch(base)
  expect(response.status).toBe(200)
  const html = await response.text()
  expect(html).toContain('/@vite/client')
  expect(html).toContain('/src/main.tsx')
})

test('dev server transforms React TSX', async () => {
  const response = await fetch(`${base}/src/main.tsx`)
  expect(response.status).toBe(200)
  expect(await response.text()).toContain('createRoot')
})

test('custom asset plugin still serves images', async () => {
  const response = await fetch(`${base}/assets/mascots/endfield-logo.png`)
  expect(response.status).toBe(200)
  expect(response.headers.get('content-type')).toBe('image/png')
  const bytes = new Uint8Array(await response.arrayBuffer())
  expect([...bytes.slice(0, 8)]).toEqual([137, 80, 78, 71, 13, 10, 26, 10])
})
