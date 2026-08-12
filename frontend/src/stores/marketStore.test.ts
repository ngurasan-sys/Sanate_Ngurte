import { describe, it, expect, beforeEach } from 'vitest';
import { useMarketStore } from './marketStore';
import { mockMarketIndices } from '../mock/data';

describe('useMarketStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    const initialState = useMarketStore.getInitialState();
    useMarketStore.setState(initialState, true);
  });

  it('should initialize with correct default state', () => {
    const state = useMarketStore.getState();
    expect(state.indices).toEqual(mockMarketIndices);
    expect(state.selectedSymbol).toBe('NIFTY');
    expect(state.timeframe).toBe('15m');
  });

  it('should update indices using setIndices', () => {
    const newIndices = {
      NIFTY: { ...mockMarketIndices.NIFTY, spot: 25000 },
      SENSEX: { ...mockMarketIndices.SENSEX, spot: 82000 },
    };

    useMarketStore.getState().setIndices(newIndices);

    const state = useMarketStore.getState();
    expect(state.indices).toEqual(newIndices);
  });

  it('should update specific index price and change properties correctly', () => {
    const initialSensexSpot = mockMarketIndices.SENSEX.spot;

    useMarketStore.getState().updateIndexPrice('NIFTY', 25050, 100, 0.4);

    const state = useMarketStore.getState();

    // NIFTY should be updated
    expect(state.indices.NIFTY.spot).toBe(25050);
    expect(state.indices.NIFTY.change).toBe(100);
    expect(state.indices.NIFTY.changePercent).toBe(0.4);

    // Other properties in NIFTY should remain unchanged
    expect(state.indices.NIFTY.trend).toBe(mockMarketIndices.NIFTY.trend);
    expect(state.indices.NIFTY.support).toBe(mockMarketIndices.NIFTY.support);

    // SENSEX should remain completely unchanged
    expect(state.indices.SENSEX.spot).toBe(initialSensexSpot);
    expect(state.indices.SENSEX).toEqual(mockMarketIndices.SENSEX);
  });

  it('should change the selected symbol', () => {
    useMarketStore.getState().setSelectedSymbol('SENSEX');
    expect(useMarketStore.getState().selectedSymbol).toBe('SENSEX');

    useMarketStore.getState().setSelectedSymbol('NIFTY');
    expect(useMarketStore.getState().selectedSymbol).toBe('NIFTY');
  });

  it('should change the timeframe', () => {
    useMarketStore.getState().setTimeframe('1h');
    expect(useMarketStore.getState().timeframe).toBe('1h');

    useMarketStore.getState().setTimeframe('Daily');
    expect(useMarketStore.getState().timeframe).toBe('Daily');
  });
});
