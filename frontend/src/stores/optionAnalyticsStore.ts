import { create } from 'zustand';

export interface IvRegimeState {
  sufficientData: boolean;
  reason: string | null;
  atmIv: number | null;
  baselineIv: number | null;
  ivChangePct: number | null;
  regime: string; // IV_CRUSH | IV_EXPANSION | IV_STABLE | UNKNOWN
  skew: number | null;
  skewBias: string; // PUT_SKEW | CALL_SKEW | NEUTRAL
  signal: string; // SELL_PREMIUM | BUY_PREMIUM | NONE
  reasoning: string | null;
}

export interface PcrReversalState {
  sufficientData: boolean;
  reason: string | null;
  pcr: number | null;
  pcrPeak: number | null;
  pcrTrough: number | null;
  zone: string; // HIGH_EXTREME | LOW_EXTREME | NEUTRAL
  signal: string; // CONTRARIAN_BULLISH | CONTRARIAN_BEARISH | NONE
  reasoning: string | null;
}

export interface SviParams {
  a: number;
  b: number;
  rho: number;
  m: number;
  sigma: number;
}

export interface SviState {
  sufficientData: boolean;
  reason: string | null;
  expiry: string | null;
  tauYears: number | null;
  forward: number | null;
  atmIv: number | null;
  skew: number | null;
  arbitrageFree: boolean | null;
  params: SviParams | null;
}

export interface VrpState {
  sufficientData: boolean;
  reason: string | null;
  impliedVol: number | null;   // SVI ATM IV
  forecastVol: number | null;  // HAR-RV one-step-ahead annualized vol
  vrp: number | null;          // impliedVol - forecastVol, in vol points
  zScore: number | null;
  classification: string; // IV_RICH | IV_CHEAP | NEUTRAL | UNKNOWN
  signal: string;          // SELL_VOLATILITY | BUY_VOLATILITY | NONE
}

interface OptionAnalyticsState {
  connectionStatus: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';
  timestamp: string | null;
  underlyingKey: string | null;
  spotPrice: number | null;
  atmStrike: number | null;
  ivRegime: IvRegimeState | null;
  pcrReversal: PcrReversalState | null;
  svi: SviState | null;
  vrp: VrpState | null;

  updateState: (data: Partial<OptionAnalyticsState>) => void;
  setConnectionStatus: (status: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING') => void;
}

export const useOptionAnalyticsStore = create<OptionAnalyticsState>((set) => ({
  connectionStatus: 'DISCONNECTED',
  timestamp: null,
  underlyingKey: null,
  spotPrice: null,
  atmStrike: null,
  ivRegime: null,
  pcrReversal: null,
  svi: null,
  vrp: null,

  updateState: (data) => set((state) => ({ ...state, ...data })),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
}));
