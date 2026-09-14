import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Agent3ProcessResultsPanel from './Agent3ProcessResultsPanel'

describe('Agent3ProcessResultsPanel directory messaging', () => {
  it('explains Company Directory identity flow', () => {
    render(
      <MemoryRouter>
        <Agent3ProcessResultsPanel processId="p1" stage="RESOURCE_PLANNING" />
      </MemoryRouter>,
    )
    expect(screen.getByText(/Company Directory → Agent 3 eligibility checks/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Company Directory' })).toHaveAttribute('href', '/directory')
    expect(document.body.textContent).not.toMatch(/synthetic employees/i)
    expect(document.body.textContent).not.toMatch(/\bpython\b/i)
  })
})
