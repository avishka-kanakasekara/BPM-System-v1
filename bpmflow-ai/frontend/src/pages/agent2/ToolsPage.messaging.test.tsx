import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Agent2ToolsPage from './ToolsPage'

describe('Agent2ToolsPage', () => {
  it('states one-step registered-tool execution only', () => {
    render(
      <MemoryRouter>
        <Agent2ToolsPage />
      </MemoryRouter>,
    )
    expect(screen.getByText(/one authorized Workflow Step using an allow-listed registered tool/i)).toBeInTheDocument()
    expect(screen.getByText(/One request → one Workflow Step → one registered tool → one receipt/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})
