interface CitationReportProps {
  checking: boolean
  progress: { current: number; total: number } | null
  report: string | null
  error: string | null
  onClose: () => void
}

export default function CitationReport({ checking, progress, report, error, onClose }: CitationReportProps) {
  if (!checking && !report && !error) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-surface-1 border border-border rounded-lg shadow-2xl w-[600px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-text-primary">Citation Check</h2>
          <button onClick={onClose} className="text-text-dim hover:text-text-secondary">&times;</button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {checking && progress && (
            <div className="text-center py-8">
              <div className="text-sm text-text-secondary mb-2">
                Checking {progress.current}/{progress.total}...
              </div>
              <div className="w-full bg-surface-2 rounded-full h-2">
                <div
                  className="bg-accent h-2 rounded-full transition-all"
                  style={{ width: `${(progress.current / progress.total) * 100}%` }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="text-center py-8 text-red text-sm">
              {error}
            </div>
          )}

          {checking && !progress && !error && (
            <div className="text-center py-8 text-text-dim text-sm">
              Starting citation check...
            </div>
          )}

          {report && (
            <pre className="text-xs text-text-secondary font-mono whitespace-pre-wrap">
              {report}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}
