import { afterEach, expect, test, vi } from 'vitest'
import { fetchAsk, fetchHealth } from '../src/api'

afterEach(() => vi.unstubAllGlobals())

test.each([
  [429, { detail: '本站今日问答次数已用完' }, '本站今日问答次数已用完'],
  [401, { detail: '需要有效的访问令牌' }, '需要有效的访问令牌'],
  [429, { error: '请求过于频繁，请稍后重试' }, '请求过于频繁，请稍后重试'],
  [422, { detail: [{ msg: 'validation error' }] }, 'HTTP 422'],
])('ask displays a readable API error (%s)', async (status, body, expected) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, json: async () => body }))
  await expect(fetchAsk('test')).rejects.toThrow(expected)
})

test('non-JSON proxy errors keep the HTTP status', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502,
    json: async () => { throw new SyntaxError('not JSON') } }))
  await expect(fetchHealth()).rejects.toThrow('HTTP 502')
})
