// TypeScript interfaces for our institutional trading workstation data models.

export interface MarketIndex {
  symbol: 'NIFTY' | 'SENSEX';
  spot: number;
  change: number;
  changePercent: number;
  trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  vwap: number;
  support: number;
  resistance: number;
  oiSentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  iv: number;
  expectedMove: number;
}

export interface OptionStrike {
  strike: number;
  atm: boolean;
  ce: {
    ltp: number;
    oi: number;
    iv: number;
    delta: number;
    volume: number;
    gamma: number;
    theta: number;
    vega: number;
    bid: number;
    ask: number;
  };
  pe: {
    ltp: number;
    oi: number;
    iv: number;
    delta: number;
    volume: number;
    gamma: number;
    theta: number;
    vega: number;
    bid: number;
    ask: number;
  };
}

export interface OptionChainData {
  symbol: 'NIFTY' | 'SENSEX';
  expiry: string;
  strikes: OptionStrike[];
}

export interface SpotTrendingOIItem {
  time: string;
  differenceOi: number;
  strength: number; // 0-100
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  directionPercent: number;
  sentiment: string;
  ceOi: number;
  peOi: number;
  changeCeOi: number;
  changePeOi: number;
}

export interface FutureTrendingOIItem {
  time: string;
  futurePrice: number;
  oiChange: number;
  oiChangePercent: number;
  priceChange: number;
  classification: 'LONG BUILDUP' | 'SHORT BUILDUP' | 'LONG UNWINDING' | 'SHORT COVERING';
  futureOi: number;
  volume: number;
  basis: number;
  basisChange: number;
}

export interface Strategy {
  id: string;
  name: string;
  status: 'ACTIVE' | 'INACTIVE' | 'PAUSED';
  signal: 'BUY CE' | 'SELL CE' | 'BUY PE' | 'SELL PE' | 'HOLD';
  confidence: number;
  pnl: number;
  parameters: Record<string, string | number>;
  indicators: Record<string, number | string>;
  levels: { support: number[]; resistance: number[] };
  oi: string;
  historicalStats: { winRate: number; totalTrades: number };
}

export interface Position {
  id: string;
  instrument: string;
  qty: number;
  ltp: number;
  entry: number;
  avgPrice: number;
  pnl: number;
  status: 'ACTIVE' | 'CLOSED';
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  iv: number;
  oi: number;
  stopLoss: number;
  target: number;
  strategy: string;
}

export interface Order {
  id: string;
  time: string;
  instrument: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  status: 'COMPLETED' | 'PENDING' | 'REJECTED' | 'CANCELLED';
  brokerOrderId: string;
  strategy: string;
  decision: string;
  risk: string;
  executionDetails: string;
}

export interface Decision {
  id: string;
  instrument: string;
  confidence: number;
  expectedValue: number;
  conflictScore: number;
  regime: 'TRENDING' | 'RANGING' | 'VOLATILE';
  action: string;
  supportingFactors: string[];
  conflictingFactors: string[];
  risk: 'PASSED' | 'FAILED' | 'WARNING';
}

export interface RiskSummaryData {
  availableCapital: number;
  availableMargin: number;
  marginUsed: number;
  dailyPnl: number;
  dailyLossLimit: number;
  exposure: number;
  openPositions: number;
  riskStatus: 'SAFE' | 'WARNING' | 'BLOCKED' | 'SAFE HALT';
  detailedCalculations: {
    varValue: number;
    stressTestResult: string;
    leverageRatio: number;
  };
}

export interface BrokerageStatus {
  brokerName: string;
  isConnected: boolean;
  wsStatus: 'CONNECTED' | 'DISCONNECTED' | 'STALE' | 'RECONNECTING';
  wsLatency: number;
  marketStatus: 'MARKET OPEN' | 'MARKET CLOSED';
  tradingStatus: 'LIVE' | 'PAPER' | 'SAFE HALT';
  account: {
    clientId: string;
    name: string;
    authStatus: 'AUTHENTICATED' | 'AUTHENTICATION REQUIRED';
  };
}
