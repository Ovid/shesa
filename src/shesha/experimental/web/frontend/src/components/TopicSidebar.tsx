import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { showToast } from './Toast'
import type { TopicInfo } from '../types'

interface TopicSidebarProps {
  activeTopic: string | null
  onSelectTopic: (name: string) => void
  onTopicsChange: () => void
}

export default function TopicSidebar({ activeTopic, onSelectTopic, onTopicsChange }: TopicSidebarProps) {
  const [topics, setTopics] = useState<TopicInfo[]>([])
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [renamingTopic, setRenamingTopic] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [menuOpen, setMenuOpen] = useState<string | null>(null)

  const loadTopics = async () => {
    try {
      const data = await api.topics.list()
      setTopics(data)
    } catch {
      showToast('Failed to load topics', 'error')
    }
  }

  useEffect(() => { loadTopics() }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await api.topics.create(newName.trim())
      setCreating(false)
      setNewName('')
      await loadTopics()
      onTopicsChange()
      onSelectTopic(newName.trim())
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to create topic', 'error')
    }
  }

  const handleRename = async (oldName: string) => {
    if (!renameValue.trim() || renameValue.trim() === oldName) {
      setRenamingTopic(null)
      return
    }
    try {
      await api.topics.rename(oldName, renameValue.trim())
      setRenamingTopic(null)
      await loadTopics()
      onTopicsChange()
      if (activeTopic === oldName) {
        onSelectTopic(renameValue.trim())
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to rename topic', 'error')
    }
  }

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete topic "${name}" and all its papers?`)) return
    try {
      await api.topics.delete(name)
      setMenuOpen(null)
      await loadTopics()
      onTopicsChange()
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed to delete topic', 'error')
    }
  }

  return (
    <aside className="w-56 border-r border-border bg-surface-1 flex flex-col shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs text-text-dim font-semibold uppercase tracking-wider">Topics</span>
        <button
          onClick={() => { setCreating(true); setNewName('') }}
          className="text-text-dim hover:text-accent transition-colors text-lg leading-none"
          title="Create topic"
        >
          +
        </button>
      </div>

      {/* Topic list */}
      <div className="flex-1 overflow-y-auto py-1">
        {creating && (
          <div className="px-3 py-1">
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleCreate()
                if (e.key === 'Escape') setCreating(false)
              }}
              onBlur={() => { if (!newName.trim()) setCreating(false) }}
              placeholder="Topic name..."
              className="w-full bg-surface-2 border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </div>
        )}

        {topics.map(t => (
          <div
            key={t.project_id}
            className={`group flex items-center px-3 py-1.5 cursor-pointer text-sm transition-colors relative ${
              activeTopic === t.name
                ? 'bg-accent-dim text-accent border-l-2 border-accent'
                : 'text-text-secondary hover:bg-surface-2'
            }`}
            onClick={() => onSelectTopic(t.name)}
          >
            {renamingTopic === t.name ? (
              <input
                autoFocus
                value={renameValue}
                onChange={e => setRenameValue(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleRename(t.name)
                  if (e.key === 'Escape') setRenamingTopic(null)
                }}
                onBlur={() => handleRename(t.name)}
                onClick={e => e.stopPropagation()}
                className="flex-1 bg-surface-2 border border-border rounded px-1 py-0.5 text-sm text-text-primary focus:outline-none focus:border-accent"
              />
            ) : (
              <>
                <span className="flex-1 truncate">{t.name}</span>
                <span className="text-[10px] text-text-dim ml-1">{t.paper_count}</span>
                <button
                  onClick={e => {
                    e.stopPropagation()
                    setMenuOpen(menuOpen === t.name ? null : t.name)
                  }}
                  className="ml-1 opacity-0 group-hover:opacity-100 text-text-dim hover:text-text-secondary transition-opacity"
                >
                  &hellip;
                </button>
              </>
            )}

            {/* Context menu */}
            {menuOpen === t.name && (
              <div className="absolute right-2 top-full z-20 bg-surface-2 border border-border rounded shadow-lg text-xs">
                <button
                  className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-text-secondary"
                  onClick={e => {
                    e.stopPropagation()
                    setRenamingTopic(t.name)
                    setRenameValue(t.name)
                    setMenuOpen(null)
                  }}
                >
                  Rename
                </button>
                <button
                  className="block w-full text-left px-3 py-1.5 hover:bg-surface-1 text-red"
                  onClick={e => {
                    e.stopPropagation()
                    handleDelete(t.name)
                  }}
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        ))}

        {topics.length === 0 && !creating && (
          <div className="px-3 py-4 text-text-dim text-xs text-center">
            No topics yet. Click + to create one.
          </div>
        )}
      </div>
    </aside>
  )
}
