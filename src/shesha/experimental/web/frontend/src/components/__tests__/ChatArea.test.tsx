import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll } from 'vitest'

beforeAll(() => {
  const store: Record<string, string> = {}
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k in store) delete store[k] },
    },
    configurable: true,
  })
  Element.prototype.scrollTo = vi.fn()
})

// Mock the api module
vi.mock('../../api/client', () => ({
  api: {
    history: { get: vi.fn().mockResolvedValue({ exchanges: [] }) },
  },
}))

// Mock Toast
vi.mock('../Toast', () => ({
  showToast: vi.fn(),
  default: () => null,
}))

import ChatArea from '../ChatArea'

describe('ChatArea input disabled state', () => {
  const baseProps = {
    topicName: 'chess',
    connected: true,
    wsSend: vi.fn(),
    wsOnMessage: vi.fn().mockReturnValue(() => {}),
    onViewTrace: vi.fn(),
    onClearHistory: vi.fn(),
    historyVersion: 0,
  }

  it('disables textarea when no papers are selected', () => {
    render(<ChatArea {...baseProps} selectedPapers={new Set()} />)
    const textarea = screen.getByPlaceholderText('Select papers in the sidebar first...')
    expect(textarea).toBeDisabled()
  })

  it('enables textarea when papers are selected', () => {
    render(<ChatArea {...baseProps} selectedPapers={new Set(['paper-1'])} />)
    const textarea = screen.getByPlaceholderText('Ask a question...')
    expect(textarea).not.toBeDisabled()
  })
})
