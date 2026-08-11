import { create } from 'zustand';
import type { Decision } from '../mock/interfaces';
import { mockDecisions } from '../mock/data';

interface DecisionState {
  decisions: Decision[];
  setDecisions: (decisions: Decision[]) => void;
}

export const useDecisionStore = create<DecisionState>((set) => ({
  decisions: mockDecisions,
  setDecisions: (decisions) => set({ decisions }),
}));
