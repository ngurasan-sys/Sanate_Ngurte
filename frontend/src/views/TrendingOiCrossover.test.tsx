import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TrendingOiCrossover } from './TrendingOiCrossover';
import { useOptionStore } from '../stores/optionStore';

vi.mock('../stores/optionStore', () => ({
  useOptionStore: vi.fn(),
}));

// Mock Recharts to avoid DOM/SVG measuring issues in JSDOM
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  AreaChart: ({ children }: any) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />,
  XAxis: () => <div data-testid="xaxis" />,
  YAxis: () => <div data-testid="yaxis" />,
  Tooltip: () => <div data-testid="tooltip" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  ReferenceArea: () => <div data-testid="reference-area" />,
  ReferenceLine: () => <div data-testid="reference-line" />,
}));

describe('TrendingOiCrossover', () => {
  const mockStartWsLiveFeed = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading/empty state when no data', () => {
    (useOptionStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      spotTrendingOI: { NIFTY: [] },
      startWsLiveFeed: mockStartWsLiveFeed,
    });

    render(<TrendingOiCrossover />);

    expect(screen.getByText('Trending OI Crossover')).toBeInTheDocument();
    expect(screen.getByText('Market Status / Active Signal')).toBeInTheDocument();
    expect(screen.getByText('WAITING')).toBeInTheDocument();

    // Filter cards
    expect(screen.getByText('TIME FILTER')).toBeInTheDocument();
    expect(screen.getByText('DISTANCE FILTER')).toBeInTheDocument();
    expect(screen.getByText('LAST CROSSOVER')).toBeInTheDocument();
    expect(screen.getByText('NONE')).toBeInTheDocument();
  });

  it('renders blocked states correctly', () => {
    (useOptionStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      spotTrendingOI: {
        NIFTY: [
          {
            time: '14:31:00',
            trade_valid: false,
            time_filter_status: 'BLOCKED',
            distance_filter_status: 'VALID',
            vwap_supertrend_distance: 20.5,
            crossover: 'NO_CROSSOVER',
            ceOi: 100000,
            peOi: 200000
          }
        ]
      },
      startWsLiveFeed: mockStartWsLiveFeed,
    });

    render(<TrendingOiCrossover />);

    expect(screen.getByText('Trading Paused: Post 2:30 PM')).toBeInTheDocument();
    expect(screen.getByText('Post 2:30 PM')).toBeInTheDocument();
  });

  it('renders distance blocked state correctly', () => {
    (useOptionStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      spotTrendingOI: {
        NIFTY: [
          {
            time: '12:00:00',
            trade_valid: false,
            time_filter_status: 'VALID',
            distance_filter_status: 'BLOCKED',
            vwap_supertrend_distance: 45.5,
            crossover: 'BULLISH_CROSSOVER',
            crossover_timestamp: '11:50:00',
            ceOi: 100000,
            peOi: 200000
          }
        ]
      },
      startWsLiveFeed: mockStartWsLiveFeed,
    });

    render(<TrendingOiCrossover />);

    expect(screen.getByText('Trading Paused: VWAP and SuperTrend too wide')).toBeInTheDocument();
    expect(screen.getByText('45.5 pts / 40 pts max')).toBeInTheDocument();
    expect(screen.getByText('BULLISH')).toBeInTheDocument(); // Last Crossover
    expect(screen.getByText('11:50:00')).toBeInTheDocument();
  });

  it('renders valid execution state correctly', () => {
    (useOptionStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      spotTrendingOI: {
        NIFTY: [
          {
            time: '12:00:00',
            trade_valid: true,
            time_filter_status: 'VALID',
            distance_filter_status: 'VALID',
            vwap_supertrend_distance: 25.0,
            crossover: 'BULLISH_CROSSOVER',
            execution_state: 'TIER_1_ENTERED',
            ceOi: 100000,
            peOi: 200000
          }
        ]
      },
      startWsLiveFeed: mockStartWsLiveFeed,
    });

    render(<TrendingOiCrossover />);

    expect(screen.getByText('TIER 1 ENTERED')).toBeInTheDocument();
    expect(screen.getByText('25.0 pts / 40 pts max')).toBeInTheDocument();
  });
});
