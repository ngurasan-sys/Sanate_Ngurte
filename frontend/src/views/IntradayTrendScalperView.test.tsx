import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom';
import { IntradayTrendScalperView } from './IntradayTrendScalperView';
import { useMarketStore } from '../stores/marketStore';
import { useAlgoStore } from '../stores/algoStore';

// Mock the chart component to avoid Lightweight Charts / jsdom canvas errors in tests
vi.mock('../components/InteractiveChart', () => ({
  default: () => <div data-testid="mock-interactive-chart">Mock Chart</div>,
}));

// Mock the stores
vi.mock('../stores/marketStore', () => ({
  useMarketStore: vi.fn(),
}));

vi.mock('../stores/algoStore', () => ({
  useAlgoStore: vi.fn(),
}));

describe('IntradayTrendScalperView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders waiting state when no signal is present', () => {
    // Setup empty data
    (useMarketStore as any).mockReturnValue({
      indices: { NIFTY: { spot: 20000, change: 0, trend: 'NEUTRAL' } },
    });
    (useAlgoStore as any).mockReturnValue({
      signals: [],
    });

    render(<IntradayTrendScalperView />);

    expect(screen.getByText('INTRADAY TREND SCALPER')).toBeInTheDocument();
    expect(screen.getByText('WAITING FOR MARKET DATA')).toBeInTheDocument();
    expect(screen.getByText('0 / 3')).toBeInTheDocument();
    expect(screen.getByText('IDLE')).toBeInTheDocument();
  });

  it('renders populated state when signal is present', () => {
    // Setup populated data
    (useMarketStore as any).mockReturnValue({
      indices: { NIFTY: { spot: 20100, change: 50, trend: 'BULLISH' } },
    });
    (useAlgoStore as any).mockReturnValue({
      signals: [
        {
          strategy: 'intraday_trend_scalper',
          market_regime: 'BULLISH_TREND_CONFIRMED',
          daily_trades_count: 1,
          oi_difference: 4500000,
          execution_state: {
            status: 'ENTRY_TIER_1',
            avg_entry: 20050.5,
            current_sl: 20000.0,
            quantity: 2,
            next_action: 'Awaiting pullback or tier 2',
          },
          timestamp: '10:15:00',
        },
      ],
    });

    render(<IntradayTrendScalperView />);

    expect(screen.getByText('BULLISH_TREND_CONFIRMED')).toBeInTheDocument();
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    expect(screen.getAllByText('ENTRY TIER 1').length).toBeGreaterThan(0);
    expect(screen.getByText('4,500,000')).toBeInTheDocument();

    // Check specific ladder visual values
    expect(screen.getAllByText('2 LOTS')[0]).toBeInTheDocument();
  });
});
