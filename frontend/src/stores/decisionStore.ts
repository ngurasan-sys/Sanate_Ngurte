import { create } from 'zustand';
import type { Decision } from '../mock/interfaces';

interface DecisionState {
  decisions: Decision[];
  setDecisions: (decisions: Decision[]) => void;
}

export const useDecisionStore = create<DecisionState>((set) => ({
  decisions: [],
  setDecisions: (decisions) => set({ decisions }),
}));
