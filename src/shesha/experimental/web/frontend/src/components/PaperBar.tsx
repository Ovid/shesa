import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { showToast } from './Toast'
import type { PaperInfo } from '../types'
import PaperDetail from './PaperDetail'

interface PaperBarProps {
  topicName: string | null
}

export default function PaperBar({ topicName }: PaperBarProps) {
  const [papers, setPapers] = useState<PaperInfo[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    if (!topicName) {
      setPapers([])
      return
    }
    api.papers.list(topicName).then(setPapers).catch(() => {
      showToast('Failed to load papers', 'error')
    })
  }, [topicName])

  if (!topicName || papers.length === 0) return null

  return (
    <div className="border-b border-border bg-surface-1">
      {/* Chip strip */}
      <div className="flex items-center gap-1.5 px-3 py-2 overflow-x-auto">
        {papers.map(p => (
          <button
            key={p.arxiv_id}
            onClick={() => setExpanded(expanded === p.arxiv_id ? null : p.arxiv_id)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-mono border transition-colors shrink-0 ${
              expanded === p.arxiv_id
                ? 'border-accent bg-accent-dim text-accent'
                : 'border-border bg-surface-2 text-text-secondary hover:border-text-dim'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-green shrink-0" />
            {p.arxiv_id}
          </button>
        ))}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <PaperDetail
          paper={papers.find(p => p.arxiv_id === expanded) ?? null}
          topicName={topicName}
          onRemove={async (arxivId) => {
            try {
              await api.papers.remove(topicName, arxivId)
              setPapers(papers.filter(p => p.arxiv_id !== arxivId))
              setExpanded(null)
              showToast('Paper removed', 'success')
            } catch {
              showToast('Failed to remove paper', 'error')
            }
          }}
          onClose={() => setExpanded(null)}
        />
      )}
    </div>
  )
}
