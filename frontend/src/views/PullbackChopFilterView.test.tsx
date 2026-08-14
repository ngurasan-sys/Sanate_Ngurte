import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { PullbackChopFilterView } from './PullbackChopFilterView';
import { useChopFilterStore } from '../stores/useChopFilterStore';

// Mock the components and hooks
vi.mock('../components/InteractiveChart', () => ({
  default: () => <div data-testid="mock-chart">Interactive Chart</div>
}));
vi.mock('../hooks/useChopFilterWebSocket', () => ({
  useChopFilterWebSocket: vi.fn()
}));

describe('PullbackChopFilterView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state when disconnected', () => {
    useChopFilterStore.setState({ timestamp: null, connectionStatus: 'DISCONNECTED' });
    render(<PullbackChopFilterView />);
    expect(screen.getByText(/Awaiting Market Data/i)).toBeInTheDocument();
  });

  it('renders CHOP_ZONE correctly', () => {
    useChopFilterStore.setState({
      timestamp: "10:00:00",
      connectionStatus: 'CONNECTED',
      marketState: 'CHOP_ZONE',
      internalState: 'WAITING',
      priceData: { ltp: 100, vwap: 101, supertrend: 99, upperBand: 101, lowerBand: 99 },
      oiData: { diffPct: 10.0 },
      activeSignal: { type: 'WAIT', message: 'In chop', color: 'slate' }
    });

    render(<PullbackChopFilterView />);
    expect(screen.getByText('NO TRADE ZONE')).toBeInTheDocument();
    expect(screen.getByText('In chop')).toBeInTheDocument();
    expect(screen.getByTestId('mock-chart')).toBeInTheDocument();
  });

  it('renders TRENDING_BULLISH correctly', () => {
    useChopFilterStore.setState({
      timestamp: "10:00:00",
      connectionStatus: 'CONNECTED',
      marketState: 'TRENDING_BULLISH',
      internalState: 'BULLISH_TIER_1',
      priceData: { ltp: 100, vwap: 90, supertrend: 100, upperBand: 100, lowerBand: 90 },
      oiData: { diffPct: 50.0 },
      activeSignal: { type: 'BUY_TIER_1', message: 'Scale In', color: 'emerald' }
    });

    render(<PullbackChopFilterView />);
    expect(screen.getByText('BULLISH TREND CONFIRMED')).toBeInTheDocument();
    expect(screen.getByText('Scale In')).toBeInTheDocument();
  });
});
