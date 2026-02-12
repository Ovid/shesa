import { useState, useCallback } from 'react'
import Header from './components/Header'
import StatusBar from './components/StatusBar'
import ToastContainer, { showToast } from './components/Toast'
import TopicSidebar from './components/TopicSidebar'
import PaperBar from './components/PaperBar'
import ChatArea from './components/ChatArea'
import SearchPanel from './components/SearchPanel'
import TraceViewer from './components/TraceViewer'
import HelpPanel from './components/HelpPanel'
import DownloadProgress from './components/DownloadProgress'
import CitationReport from './components/CitationReport'
import { useTheme } from './hooks/useTheme'
import { useWebSocket } from './hooks/useWebSocket'
import { api } from './api/client'
import type { ContextBudget } from './types'

export default function App() {
  const { dark, toggle: toggleTheme } = useTheme()
  const { connected, send, onMessage } = useWebSocket()

  const [activeTopic, setActiveTopic] = useState<string | null>(null)
  const [modelName] = useState('gpt-5-mini')
  const [tokens] = useState({ prompt: 0, completion: 0, total: 0 })
  const [budget, setBudget] = useState<ContextBudget | null>(null)
  const [phase] = useState('Ready')

  const [searchOpen, setSearchOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [traceView, setTraceView] = useState<{ topic: string; traceId: string } | null>(null)

  // Citation check state
  const [citationChecking, setCitationChecking] = useState(false)
  const [citationProgress, setCitationProgress] = useState<{ current: number; total: number } | null>(null)
  const [citationReport, setCitationReport] = useState<object | null>(null)

  // Download tasks
  const [downloadTaskIds, setDownloadTaskIds] = useState<string[]>([])

  const handleTopicSelect = useCallback((name: string) => {
    setActiveTopic(name)
    // Load context budget
    api.contextBudget(name).then(setBudget).catch(() => {})
  }, [])

  const handleExport = useCallback(async () => {
    if (!activeTopic) {
      showToast('Select a topic first', 'warning')
      return
    }
    try {
      const content = await api.export(activeTopic)
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${activeTopic}-transcript.md`
      a.click()
      URL.revokeObjectURL(url)
      showToast('Transcript exported', 'success')
    } catch {
      showToast('Failed to export transcript', 'error')
    }
  }, [activeTopic])

  const handleCheckCitations = useCallback(() => {
    if (!activeTopic) {
      showToast('Select a topic first', 'warning')
      return
    }
    setCitationChecking(true)
    setCitationProgress(null)
    setCitationReport(null)
    send({ type: 'check_citations', topic: activeTopic })
  }, [activeTopic, send])

  const handleViewTrace = useCallback((traceId: string) => {
    if (activeTopic) {
      setTraceView({ topic: activeTopic, traceId })
    }
  }, [activeTopic])

  const handleDownloadComplete = useCallback((taskId: string) => {
    setDownloadTaskIds(prev => prev.filter(id => id !== taskId))
  }, [])

  return (
    <div className="h-screen flex flex-col bg-surface-0 text-text-primary font-sans">
      <Header
        onSearchToggle={() => setSearchOpen(s => !s)}
        onCheckCitations={handleCheckCitations}
        onExport={handleExport}
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
        <TopicSidebar
          activeTopic={activeTopic}
          onSelectTopic={handleTopicSelect}
          onTopicsChange={() => {}}
        />

        {/* Center column */}
        <div className="flex-1 flex flex-col min-w-0">
          <PaperBar topicName={activeTopic} />
          <ChatArea
            topicName={activeTopic}
            connected={connected}
            wsSend={send}
            wsOnMessage={onMessage}
            onViewTrace={handleViewTrace}
          />
        </div>

        {/* Right panels */}
        {searchOpen && (
          <SearchPanel activeTopic={activeTopic} onClose={() => setSearchOpen(false)} />
        )}
      </div>

      <StatusBar
        topicName={activeTopic}
        modelName={modelName}
        tokens={tokens}
        budget={budget}
        phase={phase}
        onModelClick={() => {}}
      />

      {/* Overlays */}
      {traceView && (
        <TraceViewer
          topicName={traceView.topic}
          traceId={traceView.traceId}
          onClose={() => setTraceView(null)}
        />
      )}

      {helpOpen && <HelpPanel onClose={() => setHelpOpen(false)} />}

      <CitationReport
        checking={citationChecking}
        progress={citationProgress}
        report={citationReport}
        onClose={() => {
          setCitationChecking(false)
          setCitationReport(null)
        }}
      />

      <DownloadProgress
        taskIds={downloadTaskIds}
        onComplete={handleDownloadComplete}
      />

      <ToastContainer />
    </div>
  )
}
