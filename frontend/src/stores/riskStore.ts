import { create } from 'zustand';
import type { RiskSummaryData } from '../mock/interfaces';
import { mockRiskSummary } from '../mock/data';

interface RiskState {
  riskSummary: RiskSummaryData;
  setRiskSummary: (riskSummary: RiskSummaryData) => void;
  updateRiskMargin: (availableMargin: number, marginUsed: number) => void;
}

export const useRiskStore = create<RiskState>((set) => ({
  riskSummary: mockRiskSummary,
  setRiskSummary: (riskSummary) => set({ riskSummary }),
  updateRiskMargin: (availableMargin, marginUsed) =>
    set((state) => ({
      riskSummary: {
        ...state.riskSummary,
        availableMargin,
        marginUsed,
      },
    })),
}));
