import type { Exchange, PaperInfo } from '../types'

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

interface ChatMessageProps {
  exchange: Exchange
  onViewTrace: (traceId: string) => void
  topicPapers?: PaperInfo[]
  onPaperClick?: (paper: PaperInfo) => void
}

export default function ChatMessage({ exchange, onViewTrace, topicPapers, onPaperClick }: ChatMessageProps) {
  const questionTime = formatTime(exchange.timestamp)
  // Estimate answer time by adding execution_time to the question timestamp
  const answerTime = formatTime(
    new Date(new Date(exchange.timestamp).getTime() + exchange.execution_time * 1000).toISOString()
  )

  // Resolve paper_ids to PaperInfo objects
  const consultedPapers = (exchange.paper_ids ?? [])
    .map(id => topicPapers?.find(p => p.arxiv_id === id))
    .filter((p): p is PaperInfo => p != null)

  return (
    <div className="flex flex-col gap-3 py-3">
      {/* User question */}
      <div className="flex flex-col items-end gap-0.5">
        <div className="max-w-[70%] bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-sm text-text-primary">
          {exchange.question}
        </div>
        <span className="text-[10px] text-text-dim mr-1">{questionTime}</span>
      </div>

      {/* Assistant answer */}
      <div className="flex flex-col items-start gap-0.5">
        <div className="max-w-[70%] bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary">
          <div className="whitespace-pre-wrap">{exchange.answer}</div>

          {/* Consulted papers */}
          {consultedPapers.length > 0 && (
            <div className="mt-2 pt-2 border-t border-border">
              <div className="text-[10px] text-text-dim mb-1">Consulted papers:</div>
              <div className="flex flex-wrap gap-1">
                {consultedPapers.map(paper => (
                  <button
                    key={paper.arxiv_id}
                    onClick={() => onPaperClick?.(paper)}
                    className="text-[10px] text-accent hover:underline bg-accent/5 rounded px-1.5 py-0.5"
                    title={paper.title}
                  >
                    {paper.arxiv_id}
                  </button>
                ))}
              </div>
            </div>
          )}

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
        <span className="text-[10px] text-text-dim ml-1">{answerTime}</span>
      </div>
    </div>
  )
}
