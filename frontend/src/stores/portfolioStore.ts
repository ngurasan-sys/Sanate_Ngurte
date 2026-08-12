import { create } from 'zustand';
import type { Position, Order } from '../mock/interfaces';
import { mockPositions, mockOrders } from '../mock/data';

interface PortfolioState {
  positions: Position[];
  orders: Order[];
  totalPnl: number;
  todayPnl: number;
  setPositions: (positions: Position[]) => void;
  setOrders: (orders: Order[]) => void;
  updatePositionPrice: (id: string, newLtp: number) => void;
  updatePositionPrices: (updates: { id: string; newLtp: number }[]) => void;
  addOrder: (order: Order) => void;
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  positions: mockPositions,
  orders: mockOrders,
  totalPnl: 18450.00,
  todayPnl: 6240.00,
  setPositions: (positions) => set({ positions }),
  setOrders: (orders) => set({ orders }),
  updatePositionPrice: (id, newLtp) =>
    set((state) => {
      let todayDelta = 0;
      const updatedPositions = state.positions.map((pos) => {
        if (pos.id === id) {
          const pnlChange = (newLtp - pos.ltp) * pos.qty;
          todayDelta += pnlChange;
          return {
            ...pos,
            ltp: newLtp,
            pnl: (newLtp - pos.avgPrice) * pos.qty,
          };
        }
        return pos;
      });
      return {
        positions: updatedPositions,
        todayPnl: state.todayPnl + todayDelta,
        totalPnl: state.totalPnl + todayDelta,
      };
    }),
  updatePositionPrices: (updates) =>
    set((state) => {
      let todayDelta = 0;
      const updateMap = new Map(updates.map((u) => [u.id, u.newLtp]));

      const updatedPositions = state.positions.map((pos) => {
        if (updateMap.has(pos.id)) {
          const newLtp = updateMap.get(pos.id)!;
          const pnlChange = (newLtp - pos.ltp) * pos.qty;
          todayDelta += pnlChange;
          return {
            ...pos,
            ltp: newLtp,
            pnl: (newLtp - pos.avgPrice) * pos.qty,
          };
        }
        return pos;
      });

      return {
        positions: updatedPositions,
        todayPnl: state.todayPnl + todayDelta,
        totalPnl: state.totalPnl + todayDelta,
      };
    }),
  addOrder: (order) => set((state) => ({ orders: [order, ...state.orders] })),
}));
