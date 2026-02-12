import type { Exchange } from '../types'

interface ChatMessageProps {
  exchange: Exchange
  onViewTrace: (traceId: string) => void
}

export default function ChatMessage({ exchange, onViewTrace }: ChatMessageProps) {
  return (
    <div className="flex flex-col gap-3 py-3">
      {/* User question */}
      <div className="flex justify-end">
        <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
          {exchange.question}
        </div>
      </div>

      {/* Assistant answer */}
      <div className="flex justify-start">
        <div className="max-w-[70%] bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary">
          <div className="whitespace-pre-wrap">{exchange.answer}</div>
          <div className="flex items-center gap-3 mt-2 text-[10px] text-text-dim">
            <span>{exchange.tokens.total} tokens</span>
            <span>{exchange.execution_time.toFixed(1)}s</span>
            {exchange.trace_id && (
              <button
                onClick={() => onViewTrace(exchange.trace_id!)}
                className="text-accent hover:underline"
              >
                View trace
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
