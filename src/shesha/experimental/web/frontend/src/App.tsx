import { useState } from 'react'
import Header from './components/Header'
import StatusBar from './components/StatusBar'
import ToastContainer from './components/Toast'
import { useTheme } from './hooks/useTheme'
import { useWebSocket } from './hooks/useWebSocket'
import type { ContextBudget } from './types'

export default function App() {
  const { dark, toggle: toggleTheme } = useTheme()
  const { connected } = useWebSocket()

  const [activeTopic, setActiveTopic] = useState<string | null>(null)
  const [modelName] = useState('gpt-5-mini')
  const [tokens] = useState({ prompt: 0, completion: 0, total: 0 })
  const [budget] = useState<ContextBudget | null>(null)
  const [phase] = useState('Ready')
  const [searchOpen, setSearchOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  // Placeholder to suppress unused var warnings until components are built
  void setActiveTopic
  void searchOpen
  void helpOpen

  return (
    <div className="h-screen flex flex-col bg-surface-0 text-text-primary font-sans">
      <Header
        onSearchToggle={() => setSearchOpen(s => !s)}
        onCheckCitations={() => {}}
        onExport={() => {}}
        onHelpToggle={() => setHelpOpen(h => !h)}
        dark={dark}
        onThemeToggle={toggleTheme}
      />

      {/* Connection loss banner */}
      {!connected && (
        <div className="bg-amber/10 border-b border-amber text-amber text-sm px-4 py-1.5 text-center">
          Connection lost. Reconnecting...
        </div>
      )}

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Topic sidebar placeholder */}
        <aside className="w-56 border-r border-border bg-surface-1 p-3 text-text-dim text-sm shrink-0">
          Topics
        </aside>

        {/* Center area */}
        <main className="flex-1 flex flex-col items-center justify-center text-text-dim">
          {activeTopic
            ? `Active topic: ${activeTopic}`
            : 'Select or create a topic to begin.'}
        </main>
      </div>

      <StatusBar
        topicName={activeTopic}
        modelName={modelName}
        tokens={tokens}
        budget={budget}
        phase={phase}
        onModelClick={() => {}}
      />

      <ToastContainer />
    </div>
  )
}
