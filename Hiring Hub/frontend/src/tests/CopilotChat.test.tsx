import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CopilotChat } from '../components/candidatePool/CopilotChat';
import { NavigationProvider } from '../context/NavigationContext';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

describe('CopilotChat Component', () => {
  const renderChat = (props: React.ComponentProps<typeof CopilotChat>) =>
    render(
      <QueryClientProvider client={new QueryClient()}>
        <NavigationProvider>
          <CopilotChat {...props} />
        </NavigationProvider>
      </QueryClientProvider>
    );

  it('renders active vector tokens without seeded prompts', () => {
    const handleAdd = vi.fn();
    const handleRemove = vi.fn();
    const handleReset = vi.fn();

    renderChat(
        {
          activeTokens: ['Exp: 5+ yrs Python/TS', 'Domain: RAG / LLM'],
          onAddToken: handleAdd,
          onRemoveToken: handleRemove,
          onResetTokens: handleReset,
          onFilterResult: vi.fn(),
          positionTitle: 'Test position',
        }
    );

    expect(screen.getByText(/Hive AI Co-pilot/i)).toBeInTheDocument();
    expect(screen.getByText('Exp: 5+ yrs Python/TS')).toBeInTheDocument();
    expect(screen.getByText('Domain: RAG / LLM')).toBeInTheDocument();

    expect(screen.getByText(/Active NL Criteria Vectors/i)).toBeInTheDocument();
  });

  it('allows user to enter prompt and triggers filter submission', () => {
    const handleAdd = vi.fn();
    const handleRemove = vi.fn();
    const handleReset = vi.fn();

    renderChat(
        {
          activeTokens: [],
          onAddToken: handleAdd,
          onRemoveToken: handleRemove,
          onResetTokens: handleReset,
          onFilterResult: vi.fn(),
          positionTitle: 'Test position',
        }
    );

    const textarea = screen.getByPlaceholderText(/Ask Hive AI to filter/i);
    fireEvent.change(textarea, { target: { value: 'Show me candidates with 5+ yrs experience in SF' } });

    const runBtn = screen.getByText(/Run Filter/i);
    fireEvent.click(runBtn);

    expect(screen.getByText('Show me candidates with 5+ yrs experience in SF')).toBeInTheDocument();
  });
});
