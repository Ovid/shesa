import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface DownloadTask {
  taskId: string
  papers: { arxiv_id: string; status: string }[]
}

interface DownloadProgressProps {
  taskIds: string[]
  onComplete: (taskId: string) => void
}

export default function DownloadProgress({ taskIds, onComplete }: DownloadProgressProps) {
  const [tasks, setTasks] = useState<DownloadTask[]>([])

  useEffect(() => {
    if (taskIds.length === 0) return

    const interval = setInterval(async () => {
      const updated: DownloadTask[] = []
      for (const taskId of taskIds) {
        try {
          const data = await api.papers.taskStatus(taskId)
          updated.push({ taskId, papers: data.papers })
          const allDone = data.papers.every(p => p.status === 'complete' || p.status === 'error')
          if (allDone) {
            onComplete(taskId)
          }
        } catch {
          // Task may have been cleaned up
        }
      }
      setTasks(updated)
    }, 2000)

    return () => clearInterval(interval)
  }, [taskIds, onComplete])

  if (tasks.length === 0) return null

  return (
    <div className="fixed bottom-10 left-4 flex flex-col gap-2 z-50 max-w-xs">
      {tasks.map(task => (
        <div key={task.taskId} className="bg-surface-2 border border-border rounded px-3 py-2 text-xs shadow-lg">
          {task.papers.map(p => (
            <div key={p.arxiv_id} className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                p.status === 'complete' ? 'bg-green'
                : p.status === 'error' ? 'bg-red'
                : 'bg-amber animate-pulse'
              }`} />
              <span className="font-mono text-text-secondary">{p.arxiv_id}</span>
              <span className="text-text-dim">{p.status}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
