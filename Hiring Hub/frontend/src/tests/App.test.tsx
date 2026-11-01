import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import App from '../App';

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    ensureOrganization: vi.fn().mockResolvedValue(undefined),
  };
});

describe('Adobee Hive Recruitment Portal App', () => {
  it('renders brand header and sidebar navigation correctly', async () => {
    render(<App />);

    expect(await screen.findByText(/Candidate Search/i)).toBeInTheDocument();
    expect(screen.getAllByText(/adobee hive/i)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/Job Postings/i)[0]).toBeInTheDocument();
    expect(screen.getByText(/Analytics & Pipelines/i)).toBeInTheDocument();
  });

  it('navigates to Analytics & Pipelines view when sidebar link is clicked', async () => {
    render(<App />);

    const analyticsNavBtn = await screen.findByText(/Analytics & Pipelines/i);
    fireEvent.click(analyticsNavBtn);

    await waitFor(() => {
      expect(screen.getByText(/Talent Pipeline Intelligence/i)).toBeInTheDocument();
      expect(screen.getByText(/Total Active Pipeline/i)).toBeInTheDocument();
      expect(screen.getByText(/Requisition Funnel Progression/i)).toBeInTheDocument();
    });
  });

  it('navigates to Candidate Search view and displays candidate roster', async () => {
    render(<App />);

    const candidateSearchBtn = await screen.findByText(/Candidate Search/i);
    fireEvent.click(candidateSearchBtn);

    await waitFor(() => {
      expect(screen.getByText(/Hive AI Co-pilot/i)).toBeInTheDocument();
      expect(screen.getByText(/Filtered Pool/i)).toBeInTheDocument();
    });
  });
});
