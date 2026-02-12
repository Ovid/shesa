import { useState } from 'react'

interface HeaderProps {
  onSearchToggle: () => void
  onCheckCitations: () => void
  onExport: () => void
  onHelpToggle: () => void
  dark: boolean
  onThemeToggle: () => void
}

export default function Header({
  onSearchToggle,
  onCheckCitations,
  onExport,
  onHelpToggle,
  dark,
  onThemeToggle,
}: HeaderProps) {
  const [logoError, setLogoError] = useState(false)

  return (
    <header className="h-13 border-b border-border bg-surface-1 flex items-center px-4 shrink-0">
      {/* Logo + Title */}
      <div className="flex items-center gap-2">
        {logoError ? (
          <div className="w-8 h-8 rounded bg-accent flex items-center justify-center text-surface-0 font-bold text-sm">
            S
          </div>
        ) : (
          <img
            src="/static/shesha.png"
            alt="Shesha"
            className="w-8 h-8"
            onError={() => setLogoError(true)}
          />
        )}
        <span className="text-base font-bold text-text-primary">Shesha</span>
        <span className="text-xs text-text-dim font-mono">arXiv Explorer</span>
        <span className="text-[10px] text-amber border border-amber/40 rounded-full px-2 py-0.5 font-medium">
          Experimental
        </span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Action buttons */}
      <div className="flex items-center gap-1">
        <button
          onClick={onSearchToggle}
          className="p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          title="Search arXiv"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </button>
        <button
          onClick={onCheckCitations}
          className="p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          title="Check citations"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
        <button
          onClick={onExport}
          className="p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          title="Export transcript"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </button>
        <button
          onClick={onHelpToggle}
          className="p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          title="Help"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>

        {/* Divider */}
        <div className="w-px h-6 bg-border mx-1" />

        {/* Theme toggle */}
        <button
          onClick={onThemeToggle}
          className="p-2 rounded hover:bg-surface-2 text-text-secondary transition-colors"
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {dark ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  )
}
