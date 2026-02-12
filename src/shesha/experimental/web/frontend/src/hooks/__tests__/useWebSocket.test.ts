import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useWebSocket } from '../useWebSocket'

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  readyState = 0
  closed = false

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send = vi.fn()
  close() {
    this.closed = true
    this.readyState = 3
    this.onclose?.()
  }

  // Test helpers
  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }
}

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('does not reconnect after unmount', () => {
    const { unmount } = renderHook(() => useWebSocket())

    // WebSocket connected
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    // Unmount triggers close -> onclose -> setTimeout(connect, 2000)
    unmount()

    // Advance past the reconnect delay
    act(() => vi.advanceTimersByTime(3000))

    // Should NOT have created a second WebSocket
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('reconnects while mounted', () => {
    renderHook(() => useWebSocket())

    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    // Simulate server-side close while still mounted
    act(() => ws.close())

    // Advance past the reconnect delay
    act(() => vi.advanceTimersByTime(3000))

    // Should have created a second WebSocket for reconnection
    expect(MockWebSocket.instances).toHaveLength(2)
  })
})
