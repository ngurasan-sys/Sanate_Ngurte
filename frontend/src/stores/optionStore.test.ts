import { describe, it, expect, beforeEach } from 'vitest';
import { useOptionStore } from './optionStore';
import { mockOptionChains } from '../mock/data';

describe('useOptionStore', () => {
  // Reset the store before each test
  beforeEach(() => {
    useOptionStore.setState({
      optionChains: JSON.parse(JSON.stringify(mockOptionChains)), // deep copy to ensure isolation
    });
  });

  describe('updateLtp', () => {
    it('should update the LTP of a Call Option (CE) for a specific strike in the NIFTY chain', () => {
      const { updateLtp, optionChains } = useOptionStore.getState();
      const symbol = 'NIFTY';
      const targetStrike = 24400; // Assuming this strike exists in mock data
      const newLtp = 150.5;

      // Find initial state for assertions
      const initialChain = optionChains[symbol][0];
      const initialStrikeData = initialChain.strikes.find(s => s.strike === targetStrike);
      expect(initialStrikeData).toBeDefined();

      // Perform update
      updateLtp(symbol, targetStrike, 'ce', newLtp);

      const updatedState = useOptionStore.getState();
      const updatedChain = updatedState.optionChains[symbol][0];
      const updatedStrikeData = updatedChain.strikes.find(s => s.strike === targetStrike);

      // Verify only target strike CE LTP changed
      expect(updatedStrikeData!.ce.ltp).toBe(newLtp);

      // Verify other fields remain unchanged
      expect(updatedStrikeData!.pe.ltp).toBe(initialStrikeData!.pe.ltp);

      // Verify other strikes remain unchanged
      const otherStrike = updatedChain.strikes.find(s => s.strike !== targetStrike);
      const initialOtherStrike = initialChain.strikes.find(s => s.strike === otherStrike!.strike);
      expect(otherStrike).toEqual(initialOtherStrike);
    });

    it('should update the LTP of a Put Option (PE) for a specific strike in the SENSEX chain', () => {
      const { updateLtp, optionChains } = useOptionStore.getState();
      const symbol = 'SENSEX';
      const targetStrike = 80100; // Assuming this strike exists in mock data
      const newLtp = 300.25;

      // Find initial state for assertions
      const initialChain = optionChains[symbol][0];
      const initialStrikeData = initialChain.strikes.find(s => s.strike === targetStrike);
      expect(initialStrikeData).toBeDefined();

      // Perform update
      updateLtp(symbol, targetStrike, 'pe', newLtp);

      const updatedState = useOptionStore.getState();
      const updatedChain = updatedState.optionChains[symbol][0];
      const updatedStrikeData = updatedChain.strikes.find(s => s.strike === targetStrike);

      // Verify only target strike PE LTP changed
      expect(updatedStrikeData!.pe.ltp).toBe(newLtp);

      // Verify CE remains unchanged
      expect(updatedStrikeData!.ce.ltp).toBe(initialStrikeData!.ce.ltp);
    });

    it('should handle updating a non-existent strike gracefully (no state change)', () => {
      const initialState = useOptionStore.getState();
      const { updateLtp } = initialState;
      const symbol = 'NIFTY';
      const nonExistentStrike = 999999;
      const newLtp = 100;

      updateLtp(symbol, nonExistentStrike, 'ce', newLtp);

      const updatedState = useOptionStore.getState();

      // Option chain should be structurally equal
      expect(updatedState.optionChains).toEqual(initialState.optionChains);
    });

    it('should maintain immutability for unchanged data and create new references for changed data', () => {
      const initialState = useOptionStore.getState();
      const { updateLtp } = initialState;
      const symbol = 'NIFTY';
      const targetStrike = 24400;
      const newLtp = 150.5;

      updateLtp(symbol, targetStrike, 'ce', newLtp);

      const updatedState = useOptionStore.getState();

      // Top level object reference should change
      expect(updatedState).not.toBe(initialState);

      // optionChains reference should change
      expect(updatedState.optionChains).not.toBe(initialState.optionChains);

      // The symbol's chain list reference should change
      expect(updatedState.optionChains[symbol]).not.toBe(initialState.optionChains[symbol]);

      // The other symbol's chain list reference should NOT change
      expect(updatedState.optionChains['SENSEX']).toBe(initialState.optionChains['SENSEX']);

      const initialNiftyChain = initialState.optionChains[symbol][0];
      const updatedNiftyChain = updatedState.optionChains[symbol][0];

      // The specific chain reference should change
      expect(updatedNiftyChain).not.toBe(initialNiftyChain);

      // The strikes array reference should change
      expect(updatedNiftyChain.strikes).not.toBe(initialNiftyChain.strikes);

      // The specific strike object reference should change
      const initialStrikeObj = initialNiftyChain.strikes.find(s => s.strike === targetStrike);
      const updatedStrikeObj = updatedNiftyChain.strikes.find(s => s.strike === targetStrike);
      expect(updatedStrikeObj).not.toBe(initialStrikeObj);

      // The 'ce' object reference should change since we updated it
      expect(updatedStrikeObj!.ce).not.toBe(initialStrikeObj!.ce);

      // The 'pe' object reference should NOT change since we didn't update it
      expect(updatedStrikeObj!.pe).toBe(initialStrikeObj!.pe);

      // Other strike objects should NOT change references
      const otherStrikeValue = initialNiftyChain.strikes.find(s => s.strike !== targetStrike)!.strike;
      const initialOtherStrikeObj = initialNiftyChain.strikes.find(s => s.strike === otherStrikeValue);
      const updatedOtherStrikeObj = updatedNiftyChain.strikes.find(s => s.strike === otherStrikeValue);

      expect(updatedOtherStrikeObj).toBe(initialOtherStrikeObj);
    });
  });
});
