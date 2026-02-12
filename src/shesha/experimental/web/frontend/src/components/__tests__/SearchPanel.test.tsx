import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SearchPanel from '../SearchPanel'

// Mock the api module
vi.mock('../../api/client', () => ({
  api: {
    papers: {
      add: vi.fn(),
    },
    search: vi.fn(),
  },
}))

// Mock Toast to capture calls
vi.mock('../Toast', () => ({
  showToast: vi.fn(),
}))

import { api } from '../../api/client'

const defaultProps = {
  activeTopic: 'my-topic',
  onClose: vi.fn(),
  onPapersChanged: vi.fn(),
  onDownloadStarted: vi.fn(),
}

describe('SearchPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('addSelected passes task_id to onDownloadStarted', () => {
    it('calls onDownloadStarted when api returns a task_id', async () => {
      const user = userEvent.setup()

      // Pre-populate search results so we have something to select
      vi.mocked(api.search).mockResolvedValue([
        { arxiv_id: '2501.00001', title: 'Test Paper', authors: ['Author'], category: 'cs.AI', date: '2025-01-01', in_topics: [] },
      ])

      vi.mocked(api.papers.add).mockResolvedValue({ task_id: 'task-abc-123' })

      render(<SearchPanel {...defaultProps} />)

      // Search for papers
      const input = screen.getByPlaceholderText('Search arXiv...')
      await user.type(input, 'test query')
      await user.click(screen.getByRole('button', { name: 'Go' }))

      // Wait for results to appear
      await waitFor(() => {
        expect(screen.getByText('Test Paper')).toBeInTheDocument()
      })

      // Select the paper
      await user.click(screen.getByText('Test Paper'))

      // Click add button
      await user.click(screen.getByRole('button', { name: /Add 1 paper/ }))

      await waitFor(() => {
        expect(defaultProps.onDownloadStarted).toHaveBeenCalledWith('task-abc-123')
      })
    })

    it('does not call onDownloadStarted when api returns no task_id', async () => {
      const user = userEvent.setup()

      vi.mocked(api.search).mockResolvedValue([
        { arxiv_id: '2501.00002', title: 'Cached Paper', authors: ['Author'], category: 'cs.AI', date: '2025-01-01', in_topics: [] },
      ])

      // Paper already cached — no task_id in response
      vi.mocked(api.papers.add).mockResolvedValue({})

      render(<SearchPanel {...defaultProps} />)

      const input = screen.getByPlaceholderText('Search arXiv...')
      await user.type(input, 'cached')
      await user.click(screen.getByRole('button', { name: 'Go' }))

      await waitFor(() => {
        expect(screen.getByText('Cached Paper')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Cached Paper'))
      await user.click(screen.getByRole('button', { name: /Add 1 paper/ }))

      await waitFor(() => {
        expect(api.papers.add).toHaveBeenCalled()
      })

      expect(defaultProps.onDownloadStarted).not.toHaveBeenCalled()
    })
  })
})
