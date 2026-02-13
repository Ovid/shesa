import type { ReactNode } from 'react'

import type { Exchange, PaperInfo } from '../types'

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

const CITATION_RE = /\[@arxiv:([^\]]+)\]/g
const ARXIV_ID_RE = /\d{4}\.\d{4,5}(?:v\d+)?/g

function renderAnswerWithCitations(
  text: string,
  topicPapers?: PaperInfo[],
  onPaperClick?: (paper: PaperInfo) => void,
): ReactNode[] {
  const parts: ReactNode[] = []
  let lastIndex = 0

  for (const match of text.matchAll(CITATION_RE)) {
    const rawContent = match[1]
    const matchStart = match.index!

    // Add text before this match
    if (matchStart > lastIndex) {
      parts.push(text.slice(lastIndex, matchStart))
    }

    // Extract all arxiv IDs from the tag (handles semicolon-separated IDs)
    const ids = [...rawContent.matchAll(ARXIV_ID_RE)].map(m => m[0])

    if (ids.length === 0) {
      // No valid IDs found — render as literal text
      parts.push(match[0])
    } else {
      for (const arxivId of ids) {
        const paper = topicPapers?.find(p => p.arxiv_id === arxivId)
        if (paper) {
          parts.push(
            <button
              key={`cite-${matchStart}-${arxivId}`}
              onClick={() => onPaperClick?.(paper)}
              className="text-xs text-accent hover:underline bg-accent/5 rounded px-1 py-0.5 mx-0.5 inline"
              title={paper.title}
            >
              {paper.arxiv_id}
            </button>
          )
        } else {
          parts.push(`[@arxiv:${arxivId}]`)
        }
      }
    }

    lastIndex = matchStart + match[0].length
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts.length > 0 ? parts : [text]
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
          <div className="whitespace-pre-wrap">{renderAnswerWithCitations(exchange.answer, topicPapers, onPaperClick)}</div>

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
