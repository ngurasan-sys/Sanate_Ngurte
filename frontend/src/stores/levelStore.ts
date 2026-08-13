import { create } from 'zustand';

interface Level {
  level_id: string;
  instrument: string;
  price: number;
  level_type: string;
}

interface LevelState {
  levels: Level[];
  fetchLevels: () => Promise<void>;
}

export const useLevelStore = create<LevelState>((set) => ({
  levels: [],
  fetchLevels: async () => {
    try {
      const response = await fetch('http://localhost:8000/api/v1/levels');
      const data = await response.json();
      const allLevels = Object.values(data).flat() as Level[];
      set({ levels: allLevels });
    } catch (e) {
      console.error('Failed to fetch levels', e);
    }
  },
}));
