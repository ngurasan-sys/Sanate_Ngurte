import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { ChartPanel } from './ChartPanel';

// Mock lightweight-charts to avoid canvas issues in JSDOM
vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => ({
    addSeries: vi.fn(() => ({
      setData: vi.fn(),
    })),
    remove: vi.fn(),
    applyOptions: vi.fn(),
  })),
  LineSeries: vi.fn(),
}));

describe('ChartPanel Overlay Toggles', () => {
  const mockData = [
    { time: '2023-01-01', value: 100 },
    { time: '2023-01-02', value: 105 },
  ];

  it('renders default active overlays correctly', () => {
    render(<ChartPanel title="Test Chart" data={mockData} />);

    // By default vwap, support, resistance are true
    expect(screen.getByText(/VWAP:/i)).toBeInTheDocument();
    expect(screen.getByText(/SUPPORT:/i)).toBeInTheDocument();
    expect(screen.getByText(/RESIST:/i)).toBeInTheDocument();

    // CPR should not be visible by default based on showOverlays default prop
    expect(screen.queryByText(/CPR Central:/i)).not.toBeInTheDocument();
  });

  it('toggles an overlay when its button is clicked', () => {
    render(<ChartPanel title="Test Chart" data={mockData} />);

    // Check initial state for vwap
    expect(screen.getByText(/VWAP:/i)).toBeInTheDocument();

    // The button text is "vwap"
    const vwapButton = screen.getByRole('button', { name: /vwap/i });
    expect(vwapButton).toHaveClass('bg-zinc-800'); // active state

    // Click to toggle off
    fireEvent.click(vwapButton);

    // Overlay should disappear
    expect(screen.queryByText(/VWAP:/i)).not.toBeInTheDocument();
    expect(vwapButton).toHaveClass('bg-zinc-900'); // inactive state

    // Click to toggle back on
    fireEvent.click(vwapButton);

    // Overlay should reappear
    expect(screen.getByText(/VWAP:/i)).toBeInTheDocument();
    expect(vwapButton).toHaveClass('bg-zinc-800'); // active state
  });

  it('allows toggling an inactive overlay on', () => {
    // Explicitly pass showOverlays with an inactive one to ensure it's rendered as a button
    render(
      <ChartPanel
        title="Test Chart"
        data={mockData}
        showOverlays={{ vwap: true, cpr: false }}
      />
    );

    // Check CPR is initially off
    expect(screen.queryByText(/CPR Central:/i)).not.toBeInTheDocument();

    const cprButton = screen.getByRole('button', { name: /cpr/i });
    expect(cprButton).toHaveClass('bg-zinc-900'); // inactive state

    // Click to turn on
    fireEvent.click(cprButton);

    // Overlay should now be visible
    expect(screen.getByText(/CPR Central:/i)).toBeInTheDocument();
    expect(cprButton).toHaveClass('bg-zinc-800'); // active state
  });
});
