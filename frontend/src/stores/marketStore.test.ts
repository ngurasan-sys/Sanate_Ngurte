import { describe, it, expect, beforeEach } from 'vitest';
import { useMarketStore } from './marketStore';
import { mockMarketIndices } from '../mock/data';

describe('useMarketStore', () => {
  beforeEach(() => {
    // Reset the store before each test
    useMarketStore.setState({
      indices: JSON.parse(JSON.stringify(mockMarketIndices)),
      selectedSymbol: 'NIFTY',
      timeframe: '15m',
    });
  });

  describe('initial state', () => {
    it('should have the correct initial state', () => {
      const state = useMarketStore.getState();

      expect(state.indices).toEqual(mockMarketIndices);
      expect(state.selectedSymbol).toBe('NIFTY');
      expect(state.timeframe).toBe('15m');
    });
  });

  describe('setIndices', () => {
    it('should update indices', () => {
      const newIndices = JSON.parse(JSON.stringify(mockMarketIndices));
      newIndices.NIFTY.spot = 25000;

      useMarketStore.getState().setIndices(newIndices);

      expect(useMarketStore.getState().indices).toEqual(newIndices);
    });
  });

  describe('setSelectedSymbol', () => {
    it('should update selectedSymbol', () => {
      useMarketStore.getState().setSelectedSymbol('SENSEX');

      expect(useMarketStore.getState().selectedSymbol).toBe('SENSEX');

      useMarketStore.getState().setSelectedSymbol('NIFTY');

      expect(useMarketStore.getState().selectedSymbol).toBe('NIFTY');
    });
  });

  describe('setTimeframe', () => {
    it('should update timeframe', () => {
      useMarketStore.getState().setTimeframe('1h');

      expect(useMarketStore.getState().timeframe).toBe('1h');

      useMarketStore.getState().setTimeframe('5m');

      expect(useMarketStore.getState().timeframe).toBe('5m');
    });
  });

  describe('updateIndexPrice', () => {
    it('should update spot, change, and changePercent for a specific symbol', () => {
      useMarketStore
        .getState()
        .updateIndexPrice('NIFTY', 26000, 1500, 6.1);

      const newState = useMarketStore.getState();
      const nifty = newState.indices.NIFTY;

      expect(nifty.spot).toBe(26000);
      expect(nifty.change).toBe(1500);
      expect(nifty.changePercent).toBe(6.1);

      // Other fields should remain unchanged
      expect(nifty.trend).toBe(mockMarketIndices.NIFTY.trend);

      // Other indices should remain unchanged
      expect(newState.indices.SENSEX).toEqual(
        mockMarketIndices.SENSEX
      );
    });

    it('should maintain immutability for untouched symbols', () => {
      const state = useMarketStore.getState();

      state.updateIndexPrice('NIFTY', 26000, 1500, 6.1);

      const newState = useMarketStore.getState();

      // New state object
      expect(newState).not.toBe(state);

      // New indices object
      expect(newState.indices).not.toBe(state.indices);

      // Updated symbol gets a new reference
      expect(newState.indices.NIFTY).not.toBe(
        state.indices.NIFTY
      );

      // Untouched symbol preserves its reference
      expect(newState.indices.SENSEX).toBe(
        state.indices.SENSEX
      );
    });
  });
});