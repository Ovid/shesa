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
    <div className="px-4 py-3 border-t border-border bg-surface-2">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-text-primary leading-tight">{paper.title}</h3>
          <p className="text-xs text-text-secondary mt-1">
            {paper.authors.join(', ')}
          </p>
          <p className="text-xs text-text-dim mt-1 line-clamp-3">
            {paper.abstract}
          </p>
          <div className="flex items-center gap-3 mt-2 text-[10px] text-text-dim font-mono">
            <span>{paper.category}</span>
            <span>{paper.date}</span>
            <a
              href={paper.arxiv_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              arXiv
            </a>
          </div>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          <button
            onClick={onClose}
            className="text-text-dim hover:text-text-secondary text-xs"
          >
            Close
          </button>
          <button
            onClick={() => {
              if (confirm(`Remove paper ${paper.arxiv_id} from "${topicName}"?`)) {
                onRemove(paper.arxiv_id)
              }
            }}
            className="text-red hover:text-red/80 text-xs"
          >
            Remove
          </button>
        </div>
      </div>
    </div>
  )
}
