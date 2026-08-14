import { describe, it, expect, beforeEach } from 'vitest';
import { useMarketStore } from './marketStore';
import { mockMarketIndices } from '../mock/data';

describe('useMarketStore', () => {
  // Reset the store before each test
  beforeEach(() => {
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
      const state = useMarketStore.getState();
      const newIndices = JSON.parse(JSON.stringify(mockMarketIndices));
      newIndices.NIFTY.spot = 25000;

      state.setIndices(newIndices);

      expect(useMarketStore.getState().indices).toEqual(newIndices);
    });
  });

  describe('setSelectedSymbol', () => {
    it('should update selectedSymbol', () => {
      const state = useMarketStore.getState();
      state.setSelectedSymbol('SENSEX');

      expect(useMarketStore.getState().selectedSymbol).toBe('SENSEX');
    });
  });

  describe('setTimeframe', () => {
    it('should update timeframe', () => {
      const state = useMarketStore.getState();
      state.setTimeframe('1h');

      expect(useMarketStore.getState().timeframe).toBe('1h');
    });
  });

  describe('updateIndexPrice', () => {
    it('should update spot, change, and changePercent for a specific symbol', () => {
      const state = useMarketStore.getState();

      state.updateIndexPrice('NIFTY', 26000, 1500, 6.1);

      const newState = useMarketStore.getState();

      expect(newState.indices.NIFTY.spot).toBe(26000);
      expect(newState.indices.NIFTY.change).toBe(1500);
      expect(newState.indices.NIFTY.changePercent).toBe(6.1);

      // Check that other fields of NIFTY are preserved
      expect(newState.indices.NIFTY.trend).toBe(mockMarketIndices.NIFTY.trend);

      // Check that SENSEX is unaffected
      expect(newState.indices.SENSEX).toEqual(mockMarketIndices.SENSEX);
    });

    it('should maintain immutability for untouched symbols', () => {
      const state = useMarketStore.getState();

      state.updateIndexPrice('NIFTY', 26000, 1500, 6.1);

      const newState = useMarketStore.getState();

      // Should create new reference for state and indices
      expect(newState).not.toBe(state);
      expect(newState.indices).not.toBe(state.indices);

      // Should create new reference for NIFTY
      expect(newState.indices.NIFTY).not.toBe(state.indices.NIFTY);

      // Should preserve reference for SENSEX
      expect(newState.indices.SENSEX).toBe(state.indices.SENSEX);
    });
  });
});
