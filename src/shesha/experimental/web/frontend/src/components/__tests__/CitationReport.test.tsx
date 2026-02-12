import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import CitationReport from '../CitationReport'

const defaultProps = {
  checking: false,
  progress: null,
  report: null as string | null,
  error: null as string | null,
  onClose: vi.fn(),
}

describe('CitationReport', () => {
  it('renders nothing when not checking and no report', () => {
    const { container } = render(<CitationReport {...defaultProps} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows "Starting citation check..." when checking with no progress', () => {
    render(<CitationReport {...defaultProps} checking={true} />)
    expect(screen.getByText('Starting citation check...')).toBeInTheDocument()
  })

  it('shows progress bar when checking with progress', () => {
    render(
      <CitationReport {...defaultProps} checking={true} progress={{ current: 3, total: 10 }} />
    )
    expect(screen.getByText('Checking 3/10...')).toBeInTheDocument()
  })

  it('shows error message when error is set', () => {
    render(
      <CitationReport
        {...defaultProps}
        checking={false}
        error="Unknown message type: check_citations"
      />
    )
    expect(screen.getByText('Unknown message type: check_citations')).toBeInTheDocument()
  })

  it('shows error even while checking flag is still true', () => {
    render(
      <CitationReport
        {...defaultProps}
        checking={true}
        error="Something went wrong"
      />
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    // Should NOT show "Starting citation check..." when there's an error
    expect(screen.queryByText('Starting citation check...')).not.toBeInTheDocument()
  })

  it('displays formatted report text', () => {
    const report = 'DISCLAIMER: This analysis...\n\nCitations found: 5\n  OK  3 verified'
    render(<CitationReport {...defaultProps} report={report} />)
    expect(screen.getByText(/DISCLAIMER: This analysis/)).toBeInTheDocument()
    expect(screen.getByText(/Citations found: 5/)).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    render(<CitationReport {...defaultProps} checking={true} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button'))
    expect(onClose).toHaveBeenCalled()
  })
})
