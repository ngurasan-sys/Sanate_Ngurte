import { describe, it, expect, beforeEach } from 'vitest';
import { useOFAOStore } from './useOFAOStore';
import type { OFAOSnapshot } from './useOFAOStore';

const snapshot = (overrides: Partial<OFAOSnapshot> = {}): OFAOSnapshot => ({
  instrument_key: 'NIFTY FUT', underlying: 'NIFTY', timestamp: '2024-10-01T10:00:00Z',
  state: 'NO_SETUP', setup_id: null, direction: null, location_price: null,
  location_reason: null, absorption_strength: 0, invalidation_price: null,
  trade_intent: null, last_price: 25000,
  ...overrides,
});

describe('useOFAOStore', () => {
  beforeEach(() => {
    useOFAOStore.setState({ snapshots: {}, config: null, connectionStatus: 'DISCONNECTED' });
  });

  it('applySnapshot stores a snapshot keyed by instrument_key', () => {
    useOFAOStore.getState().applySnapshot(snapshot());
    expect(useOFAOStore.getState().snapshots['NIFTY FUT'].state).toBe('NO_SETUP');
  });

  it('applySnapshot for a different instrument does not overwrite the first', () => {
    useOFAOStore.getState().applySnapshot(snapshot({ instrument_key: 'NIFTY FUT' }));
    useOFAOStore.getState().applySnapshot(snapshot({ instrument_key: 'SENSEX FUT', underlying: 'SENSEX' }));
    const { snapshots } = useOFAOStore.getState();
    expect(Object.keys(snapshots)).toEqual(['NIFTY FUT', 'SENSEX FUT']);
  });

  it('applySnapshot for the same instrument replaces the previous one', () => {
    useOFAOStore.getState().applySnapshot(snapshot({ state: 'NO_SETUP' }));
    useOFAOStore.getState().applySnapshot(snapshot({ state: 'LOCATION_REACHED' }));
    expect(useOFAOStore.getState().snapshots['NIFTY FUT'].state).toBe('LOCATION_REACHED');
  });

  it('setConnectionStatus updates status', () => {
    useOFAOStore.getState().setConnectionStatus('CONNECTED');
    expect(useOFAOStore.getState().connectionStatus).toBe('CONNECTED');
  });

  it('setConfig stores the config', () => {
    useOFAOStore.getState().setConfig({
      enabled: true, underlyings: ['NIFTY'], absorption_strength_threshold: 70,
      imbalance_ratio_pct: 400, risk_reward_min: 1.5, entry_start_time: '09:25',
      entry_cutoff_time: '15:00', lots: 1,
    });
    expect(useOFAOStore.getState().config?.enabled).toBe(true);
  });
});
