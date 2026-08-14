import { describe, it, expect, beforeEach } from 'vitest';
import { usePortfolioStore } from './portfolioStore';
import { mockPositions, mockOrders } from '../mock/data';

describe('usePortfolioStore', () => {
  // Reset the store before each test
  beforeEach(() => {
    usePortfolioStore.setState({
      positions: JSON.parse(JSON.stringify(mockPositions)), // deep copy to ensure isolation
      orders: JSON.parse(JSON.stringify(mockOrders)),
      totalPnl: 18450.00,
      todayPnl: 6240.00,
    });
  });

  describe('updatePositionPrice', () => {
    it('should update the LTP and PnL correctly for an existing position (LTP increase)', () => {
      const { updatePositionPrice, positions } = usePortfolioStore.getState();
      const targetPos = positions[0]; // Let's use the first position
      const newLtp = targetPos.ltp + 10;

      const initialTotalPnl = usePortfolioStore.getState().totalPnl;
      const initialTodayPnl = usePortfolioStore.getState().todayPnl;

      // Perform update
      updatePositionPrice(targetPos.id, newLtp);

      const updatedState = usePortfolioStore.getState();
      const updatedPos = updatedState.positions.find(p => p.id === targetPos.id);

      // Verify specific position properties updated
      expect(updatedPos).toBeDefined();
      expect(updatedPos!.ltp).toBe(newLtp);

      // Calculate expected new position PnL: (newLtp - avgPrice) * qty
      const expectedPnl = (newLtp - targetPos.avgPrice) * targetPos.qty;
      expect(updatedPos!.pnl).toBe(expectedPnl);

      // Calculate expected overall PnL change
      const pnlChange = (newLtp - targetPos.ltp) * targetPos.qty;

      // Verify overall PnL updated
      expect(updatedState.todayPnl).toBe(initialTodayPnl + pnlChange);
      expect(updatedState.totalPnl).toBe(initialTotalPnl + pnlChange);
    });

    it('should update the LTP and PnL correctly for an existing position (LTP decrease)', () => {
      const { updatePositionPrice, positions } = usePortfolioStore.getState();
      const targetPos = positions[0];
      const newLtp = targetPos.ltp - 5;

      const initialTotalPnl = usePortfolioStore.getState().totalPnl;
      const initialTodayPnl = usePortfolioStore.getState().todayPnl;

      // Perform update
      updatePositionPrice(targetPos.id, newLtp);

      const updatedState = usePortfolioStore.getState();
      const updatedPos = updatedState.positions.find(p => p.id === targetPos.id);

      // Verify specific position properties updated
      expect(updatedPos).toBeDefined();
      expect(updatedPos!.ltp).toBe(newLtp);

      // Calculate expected new position PnL: (newLtp - avgPrice) * qty
      const expectedPnl = (newLtp - targetPos.avgPrice) * targetPos.qty;
      expect(updatedPos!.pnl).toBe(expectedPnl);

      // Calculate expected overall PnL change (will be negative)
      const pnlChange = (newLtp - targetPos.ltp) * targetPos.qty;

      // Verify overall PnL updated correctly with negative change
      expect(updatedState.todayPnl).toBe(initialTodayPnl + pnlChange);
      expect(updatedState.totalPnl).toBe(initialTotalPnl + pnlChange);
    });

    it('should maintain state isolation (other positions unchanged)', () => {
      const { updatePositionPrice, positions } = usePortfolioStore.getState();
      if (positions.length < 2) {
        throw new Error('Test requires at least 2 positions in mock data');
      }

      const targetPos = positions[0];
      const otherPos = positions[1];
      const newLtp = targetPos.ltp + 20;

      // Perform update
      updatePositionPrice(targetPos.id, newLtp);

      const updatedState = usePortfolioStore.getState();
      const updatedOtherPos = updatedState.positions.find(p => p.id === otherPos.id);

      // Verify the other position is completely untouched
      expect(updatedOtherPos).toEqual(otherPos);
    });

    it('should handle updating a non-existent position ID gracefully', () => {
      const initialState = usePortfolioStore.getState();
      const nonExistentId = 'non-existent-pos-999';
      const newLtp = 500;

      // Perform update
      initialState.updatePositionPrice(nonExistentId, newLtp);

      const updatedState = usePortfolioStore.getState();

      // Verify state remains completely unchanged
      expect(updatedState.positions).toEqual(initialState.positions);
      expect(updatedState.todayPnl).toBe(initialState.todayPnl);
      expect(updatedState.totalPnl).toBe(initialState.totalPnl);
    });
  });
});
