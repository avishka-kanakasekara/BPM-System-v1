import '@testing-library/jest-dom'
import { beforeAll, vi } from 'vitest'

beforeAll(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network access is disabled in tests'))))
  vi.stubGlobal('XMLHttpRequest', class BlockedXMLHttpRequest {
    constructor() {
      throw new Error('Network access is disabled in tests')
    }
  })
})
