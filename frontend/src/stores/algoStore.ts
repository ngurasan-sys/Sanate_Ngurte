import { create } from 'zustand';

export type AlgoEngineStatus = 'STOPPED' | 'STARTING' | 'RUNNING' | 'PAUSED' | 'STOPPING' | 'ERROR';
export type ExecutionMode = 'DATA_ONLY' | 'PAPER' | 'LIVE';
// Who decides the trade — the strategy engines (AUTO) or the trader
// placing orders directly through the Manual Trading panel (MANUAL).
// Independent of ExecutionMode, which controls how an order executes.
export type TradingMode = 'AUTO' | 'MANUAL';

export interface Signal {
  id: string;
  timestamp: string;
  strategy: string;
  instrument: string;
  direction: 'CALL' | 'PUT';
  strike: string;
  optionType: 'CE' | 'PE';
  entry: string;
  stopLoss: string;
  target: string;
  confidence: number;
  reason: string;
  riskStatus: 'APPROVED' | 'REJECTED' | 'PENDING';
  executionStatus: string;
}

export interface StrategyMeta {
  strategy_id: string;
  name: string;
  description: string;
  instrument_types: string[];
  timeframes: string[];
  enabled: boolean;
  status: 'ACTIVE' | 'INACTIVE' | 'ERROR';
  parameters: Record<string, any>;
  risk_profile: string;
  lastSignal?: string;
  trades?: number;
  winRate?: string;
  pnl?: string;
}

export interface PipelineMetrics {
  ticksProcessed: number;
  signalsGenerated: number;
  signalsConfirmed: number;
  signalsRejected: number;
  riskRejections: number;
  executionRequests: number;
}

export interface RiskMetrics {
  dailyPnl: number;
  maxDailyLoss: number;
  currentExposure: number;
  maxExposure: number;
  openPositions: number;
  openOrders: number;
  riskUtilization: number;
  drawdown: number;
  consecutiveLosses: number;
  positionSizeLimit: number;
  perTradeRisk: number;
  status: 'HEALTHY' | 'WARNING' | 'BLOCKED';
}

interface AlgoState {
  algoEngineStatus: AlgoEngineStatus;
  executionMode: ExecutionMode;
  tradingMode: TradingMode;
  // Real LIVE arm state (execution_runtime_state.is_armed(), via
  // GET /api/v1/execution/status) — the "Global Trading ON/OFF" header
  // display reads this rather than introducing a second kill switch.
  armed: boolean;
  strategies: StrategyMeta[];
  signals: Signal[];
  pipelineMetrics: PipelineMetrics;
  riskMetrics: RiskMetrics;

  setAlgoEngineStatus: (status: AlgoEngineStatus) => void;
  setExecutionMode: (mode: ExecutionMode) => void;
  setTradingMode: (mode: TradingMode) => void;
  setArmed: (armed: boolean) => void;
  setStrategies: (strategies: StrategyMeta[]) => void;
  addSignal: (signal: Signal) => void;
  updatePipelineMetrics: (metrics: Partial<PipelineMetrics>) => void;
  setRiskMetrics: (metrics: RiskMetrics) => void;
}

export const useAlgoStore = create<AlgoState>((set) => ({
  algoEngineStatus: 'STOPPED',
  executionMode: 'DATA_ONLY',
  tradingMode: 'AUTO',
  armed: false,
  strategies: [],
  signals: [],
  pipelineMetrics: {
    ticksProcessed: 0,
    signalsGenerated: 0,
    signalsConfirmed: 0,
    signalsRejected: 0,
    riskRejections: 0,
    executionRequests: 0
  },
  riskMetrics: {
    dailyPnl: 0,
    maxDailyLoss: 0,
    currentExposure: 0,
    maxExposure: 0,
    openPositions: 0,
    openOrders: 0,
    riskUtilization: 0,
    drawdown: 0,
    consecutiveLosses: 0,
    positionSizeLimit: 0,
    perTradeRisk: 0,
    status: 'HEALTHY'
  },

  setAlgoEngineStatus: (status) => set({ algoEngineStatus: status }),
  setExecutionMode: (mode) => set({ executionMode: mode }),
  setTradingMode: (mode) => set({ tradingMode: mode }),
  setArmed: (armed) => set({ armed }),
  setStrategies: (strategies) => set({ strategies }),
  addSignal: (signal) => set((state) => ({
    signals: [signal, ...state.signals].slice(0, 100) // Keep last 100 signals
  })),
  updatePipelineMetrics: (metrics) => set((state) => ({
    pipelineMetrics: { ...state.pipelineMetrics, ...metrics }
  })),
  setRiskMetrics: (metrics) => set({ riskMetrics: metrics })
}));
