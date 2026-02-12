import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api/client'
import { showToast } from './Toast'
import ChatMessage from './ChatMessage'
import type { Exchange, WSMessage } from '../types'

interface ChatAreaProps {
  topicName: string | null
  connected: boolean
  wsSend: (data: object) => void
  wsOnMessage: (fn: (msg: WSMessage) => void) => () => void
  onViewTrace: (traceId: string) => void
  historyVersion: number
}

export default function ChatArea({ topicName, connected, wsSend, wsOnMessage, onViewTrace, historyVersion }: ChatAreaProps) {
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [phase, setPhase] = useState('')
  const [showBanner, setShowBanner] = useState(() => {
    return localStorage.getItem('shesha-welcome-dismissed') !== 'true'
  })
  const scrollRef = useRef<HTMLDivElement>(null)

  // Load history when topic changes
  useEffect(() => {
    if (!topicName) {
      setExchanges([])
      return
    }
    api.history.get(topicName).then(data => {
      setExchanges(data.exchanges as Exchange[])
    }).catch(() => {
      showToast('Failed to load conversation history', 'error')
    })
  }, [topicName, historyVersion])

  // Listen for WebSocket messages
  useEffect(() => {
    return wsOnMessage((msg: WSMessage) => {
      if (msg.type === 'status') {
        setPhase(msg.phase)
      } else if (msg.type === 'step') {
        setPhase(`${msg.step_type} (iter ${msg.iteration})`)
      } else if (msg.type === 'complete') {
        setThinking(false)
        setPendingQuestion(null)
        setPhase('')
        // Reload history to get the saved exchange
        if (topicName) {
          api.history.get(topicName).then(data => {
            setExchanges(data.exchanges as Exchange[])
          }).catch(() => {})
        }
      } else if (msg.type === 'error') {
        setThinking(false)
        setPendingQuestion(null)
        setPhase('')
        showToast(msg.message, 'error')
      } else if (msg.type === 'cancelled') {
        setThinking(false)
        setPendingQuestion(null)
        setPhase('')
      }
    })
  }, [wsOnMessage, topicName])

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [exchanges, thinking])

  const handleSend = useCallback(() => {
    if (!input.trim() || !topicName || thinking || !connected) return
    const question = input.trim()
    wsSend({ type: 'query', topic: topicName, question })
    setInput('')
    setPendingQuestion(question)
    setThinking(true)
    setPhase('Starting')
  }, [input, topicName, thinking, connected, wsSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
    if (e.key === 'Escape' && thinking) {
      wsSend({ type: 'cancel' })
    }
  }

  const dismissBanner = () => {
    setShowBanner(false)
    localStorage.setItem('shesha-welcome-dismissed', 'true')
  }

  if (!topicName) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-dim text-sm">
        Select or create a topic to begin.
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {/* Experimental welcome banner */}
      {showBanner && (
        <div className="bg-amber/5 border-b border-amber/20 px-4 py-2 flex items-center justify-between text-xs text-amber">
          <span>
            This is experimental software. Some features may be incomplete.
            Click the <strong>?</strong> icon in the header for help.
          </span>
          <button onClick={dismissBanner} className="ml-2 hover:text-amber/80">&times;</button>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0 px-4">
        {exchanges.length === 0 && !thinking && (
          <div className="flex items-center justify-center h-full text-text-dim text-sm">
            Ask a question about the papers in this topic.
          </div>
        )}
        {exchanges.map(ex => (
          <ChatMessage key={ex.exchange_id} exchange={ex} onViewTrace={onViewTrace} />
        ))}

        {/* Pending question (shown immediately before answer arrives) */}
        {pendingQuestion && (
          <div className="flex flex-col gap-3 py-3">
            <div className="flex justify-end">
              <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
                {pendingQuestion}
              </div>
            </div>
          </div>
        )}

        {/* Thinking indicator */}
        {thinking && (
          <div className="flex justify-start py-3">
            <div className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-dim">
              <span className="inline-flex gap-1">
                <span className="animate-bounce" style={{ animationDelay: '0ms' }}>.</span>
                <span className="animate-bounce" style={{ animationDelay: '150ms' }}>.</span>
                <span className="animate-bounce" style={{ animationDelay: '300ms' }}>.</span>
              </span>
              {phase && <span className="ml-2 text-xs">{phase}</span>}
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border bg-surface-1 px-4 py-3">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!connected}
            placeholder={
              !connected ? 'Reconnecting...'
              : 'Ask a question...'
            }
            rows={1}
            className="flex-1 bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary resize-none focus:outline-none focus:border-accent disabled:opacity-50"
          />
          {thinking ? (
            <button
              onClick={() => wsSend({ type: 'cancel' })}
              className="px-4 py-2 bg-red text-white rounded text-sm font-medium hover:bg-red/90 transition-colors"
            >
              Cancel
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || !connected}
              className="px-4 py-2 bg-accent text-surface-0 rounded text-sm font-medium hover:bg-accent/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
