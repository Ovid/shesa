import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DownloadProgress from '../DownloadProgress'

vi.mock('../../api/client', () => ({
  api: {
    papers: {
      taskStatus: vi.fn(),
    },
  },
}))

import { api } from '../../api/client'

const defaultProps = {
  taskIds: ['task-1'],
  onComplete: vi.fn(),
}

describe('DownloadProgress', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a modal with progress bar when downloading', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'complete' },
        { arxiv_id: '2501.00002', status: 'downloading' },
        { arxiv_id: '2501.00003', status: 'pending' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    // poll() is called immediately on mount
    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })

    // Should show progress count: 1 complete out of 3 total
    expect(screen.getByText(/1\/3/)).toBeInTheDocument()
    // Should show currently downloading paper
    expect(screen.getByText(/2501\.00002/)).toBeInTheDocument()
  })

  it('renders nothing when no taskIds', () => {
    render(<DownloadProgress taskIds={[]} onComplete={vi.fn()} />)
    expect(screen.queryByText('Downloading Papers')).not.toBeInTheDocument()
  })

  it('can be dismissed with close button', async () => {
    const user = userEvent.setup()

    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'downloading' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /×/ }))

    expect(screen.queryByText('Downloading Papers')).not.toBeInTheDocument()
  })

  it('calls onComplete when all papers are done', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'complete' },
        { arxiv_id: '2501.00002', status: 'complete' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(defaultProps.onComplete).toHaveBeenCalledWith('task-1')
    })
  })

  it('shows animated bar when downloading but none complete', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'downloading' },
        { arxiv_id: '2501.00002', status: 'pending' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Downloading Papers')).toBeInTheDocument()
    })

    // Progress bar should have animate-progress-slide class, not 0% width
    const barFill = screen.getByTestId('download-bar-fill')
    expect(barFill.className).toContain('animate-progress-slide')
  })

  it('shows green bar when all downloads complete', async () => {
    vi.mocked(api.papers.taskStatus).mockResolvedValue({
      task_id: 'task-1',
      papers: [
        { arxiv_id: '2501.00001', status: 'complete' },
        { arxiv_id: '2501.00002', status: 'complete' },
      ],
    })

    render(<DownloadProgress {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText(/2\/2/)).toBeInTheDocument()
      expect(screen.getByText(/Complete/)).toBeInTheDocument()
    })
  })
})
