import { create } from 'zustand';
import type { RiskSummaryData } from '../mock/interfaces';

interface RiskState {
  riskSummary: RiskSummaryData | null;
  setRiskSummary: (riskSummary: RiskSummaryData) => void;
  updateRiskMargin: (availableMargin: number, marginUsed: number) => void;
}

export const useRiskStore = create<RiskState>((set) => ({
  riskSummary: null,
  setRiskSummary: (riskSummary) => set({ riskSummary }),
  updateRiskMargin: (availableMargin, marginUsed) =>
    set((state) => {
      if (!state.riskSummary) return {};
      return {
        riskSummary: {
          ...state.riskSummary,
          availableMargin,
          marginUsed,
        },
      };
    }),
}));
