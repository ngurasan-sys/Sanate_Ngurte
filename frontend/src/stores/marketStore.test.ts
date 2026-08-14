import { describe, it, expect, beforeEach } from 'vitest';
import { useMarketStore } from './marketStore';
import { mockMarketIndices } from '../mock/data';

describe('useMarketStore', () => {
  beforeEach(() => {
    // Reset the store to its initial state before each test
    const store = useMarketStore.getState();
    store.setIndices(mockMarketIndices);
    store.setSelectedSymbol('NIFTY');
    store.setTimeframe('15m');
  });

  it('should initialize with correct default values', () => {
    const state = useMarketStore.getState();
    expect(state.indices).toEqual(mockMarketIndices);
    expect(state.selectedSymbol).toBe('NIFTY');
    expect(state.timeframe).toBe('15m');
  });

  it('should update indices with setIndices', () => {
    const newIndices = {
      ...mockMarketIndices,
      NIFTY: {
        ...mockMarketIndices.NIFTY,
        spot: 25000,
      }
    };
    useMarketStore.getState().setIndices(newIndices);

    expect(useMarketStore.getState().indices.NIFTY.spot).toBe(25000);
  });

  it('should update specific index price with updateIndexPrice', () => {
    useMarketStore.getState().updateIndexPrice('NIFTY', 25100, 150, 0.6);

    const nifty = useMarketStore.getState().indices.NIFTY;
    expect(nifty.spot).toBe(25100);
    expect(nifty.change).toBe(150);
    expect(nifty.changePercent).toBe(0.6);

    // Ensure other indices are not affected
    expect(useMarketStore.getState().indices.SENSEX).toEqual(mockMarketIndices.SENSEX);
  });

  it('should change selected symbol with setSelectedSymbol', () => {
    useMarketStore.getState().setSelectedSymbol('SENSEX');
    expect(useMarketStore.getState().selectedSymbol).toBe('SENSEX');

    useMarketStore.getState().setSelectedSymbol('NIFTY');
    expect(useMarketStore.getState().selectedSymbol).toBe('NIFTY');
  });

  it('should change timeframe with setTimeframe', () => {
    useMarketStore.getState().setTimeframe('1h');
    expect(useMarketStore.getState().timeframe).toBe('1h');

    useMarketStore.getState().setTimeframe('5m');
    expect(useMarketStore.getState().timeframe).toBe('5m');
  });
});
