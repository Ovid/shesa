import type { PaperInfo } from '../types'

interface PaperDetailProps {
  paper: PaperInfo | null
  topicName: string
  onRemove: (arxivId: string) => void
  onClose: () => void
}

export default function PaperDetail({ paper, topicName, onRemove, onClose }: PaperDetailProps) {
  if (!paper) return null

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {/* Top bar with Back button */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-surface-1">
        <button
          onClick={onClose}
          className="text-sm text-text-secondary hover:text-accent transition-colors"
        >
          &larr; Back
        </button>
        <span className="text-xs text-text-dim font-mono">{paper.arxiv_id}</span>
      </div>

      {/* Paper content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-3xl">
        <h1 className="text-xl font-semibold text-text-primary leading-tight">
          {paper.title}
        </h1>
        <p className="text-sm text-text-secondary mt-2">
          {paper.authors.join(', ')}
        </p>
        <div className="flex items-center gap-3 mt-3 text-xs text-text-dim font-mono">
          <span>{paper.category}</span>
          <span>{paper.date}</span>
          <a
            href={paper.arxiv_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            View on arXiv
          </a>
        </div>
        <div className="mt-6 text-sm text-text-secondary leading-relaxed">
          {paper.abstract}
        </div>

        {/* Actions */}
        <div className="mt-8 flex gap-3">
          <button
            onClick={() => {
              if (confirm(`Remove paper ${paper.arxiv_id} from "${topicName}"?`)) {
                onRemove(paper.arxiv_id)
              }
            }}
            className="px-3 py-1.5 text-xs text-red border border-red/30 rounded hover:bg-red/10 transition-colors"
          >
            Remove from topic
          </button>
        </div>
      </div>
    </div>
  )
}
