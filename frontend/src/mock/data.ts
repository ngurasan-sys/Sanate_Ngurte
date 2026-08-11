import type {
  MarketIndex,
  OptionChainData,
  SpotTrendingOIItem,
  FutureTrendingOIItem,
  Strategy,
  Position,
  Order,
  Decision,
  RiskSummaryData,
  BrokerageStatus
} from './interfaces';

export const mockMarketIndices: Record<'NIFTY' | 'SENSEX', MarketIndex> = {
  NIFTY: {
    symbol: 'NIFTY',
    spot: 24500.20,
    change: 82.40,
    changePercent: 0.34,
    trend: 'BULLISH',
    vwap: 24460.50,
    support: 24400.00,
    resistance: 24600.00,
    oiSentiment: 'BULLISH',
    iv: 14.20,
    expectedMove: 120.50
  },
  SENSEX: {
    symbol: 'SENSEX',
    spot: 80240.15,
    change: -112.30,
    changePercent: -0.14,
    trend: 'BEARISH',
    vwap: 80310.20,
    support: 80000.00,
    resistance: 80500.00,
    oiSentiment: 'NEUTRAL',
    iv: 15.10,
    expectedMove: 410.00
  }
};

export const mockOptionChains: Record<'NIFTY' | 'SENSEX', OptionChainData[]> = {
  NIFTY: [
    {
      symbol: 'NIFTY',
      expiry: '2026-08-20',
      strikes: [
        {
          strike: 24300,
          atm: false,
          ce: { ltp: 242.10, oi: 15400, iv: 13.80, delta: 0.81, volume: 82000, gamma: 0.0002, theta: -12.40, vega: 18.50, bid: 241.80, ask: 242.40 },
          pe: { ltp: 41.50, oi: 45000, iv: 14.50, delta: -0.19, volume: 154000, gamma: 0.0002, theta: -8.10, vega: 10.20, bid: 41.20, ask: 41.80 }
        },
        {
          strike: 24400,
          atm: false,
          ce: { ltp: 172.40, oi: 28900, iv: 14.00, delta: 0.68, volume: 110000, gamma: 0.0003, theta: -13.50, vega: 20.10, bid: 172.10, ask: 172.70 },
          pe: { ltp: 68.30, oi: 59000, iv: 14.20, delta: -0.32, volume: 198000, gamma: 0.0003, theta: -9.40, vega: 12.80, bid: 68.10, ask: 68.50 }
        },
        {
          strike: 24500,
          atm: true,
          ce: { ltp: 112.50, oi: 65000, iv: 14.20, delta: 0.52, volume: 320000, gamma: 0.0004, theta: -14.80, vega: 21.40, bid: 112.30, ask: 112.70 },
          pe: { ltp: 108.20, oi: 61000, iv: 14.10, delta: -0.48, volume: 290000, gamma: 0.0004, theta: -14.20, vega: 21.10, bid: 108.00, ask: 108.40 }
        },
        {
          strike: 24600,
          atm: false,
          ce: { ltp: 68.10, oi: 88000, iv: 14.50, delta: 0.35, volume: 210000, gamma: 0.0003, theta: -13.10, vega: 18.90, bid: 67.90, ask: 68.30 },
          pe: { ltp: 164.50, oi: 32000, iv: 14.30, delta: -0.65, volume: 120000, gamma: 0.0003, theta: -10.50, vega: 14.10, bid: 164.20, ask: 164.80 }
        },
        {
          strike: 24700,
          atm: false,
          ce: { ltp: 38.50, oi: 94000, iv: 14.80, delta: 0.21, volume: 165000, gamma: 0.0002, theta: -10.20, vega: 13.50, bid: 38.30, ask: 38.70 },
          pe: { ltp: 232.00, oi: 12000, iv: 14.60, delta: -0.79, volume: 45000, gamma: 0.0002, theta: -7.20, vega: 9.80, bid: 231.50, ask: 232.50 }
        }
      ]
    }
  ],
  SENSEX: [
    {
      symbol: 'SENSEX',
      expiry: '2026-08-21',
      strikes: [
        {
          strike: 80000,
          atm: false,
          ce: { ltp: 410.20, oi: 8500, iv: 14.80, delta: 0.72, volume: 24000, gamma: 0.0001, theta: -45.20, vega: 52.10, bid: 409.00, ask: 411.40 },
          pe: { ltp: 172.50, oi: 19500, iv: 15.40, delta: -0.28, volume: 42000, gamma: 0.0001, theta: -32.10, vega: 35.40, bid: 171.80, ask: 173.20 }
        },
        {
          strike: 80100,
          atm: false,
          ce: { ltp: 335.50, oi: 12400, iv: 14.95, delta: 0.63, volume: 38000, gamma: 0.0001, theta: -46.80, vega: 55.40, bid: 334.80, ask: 336.20 },
          pe: { ltp: 202.10, oi: 14800, iv: 15.30, delta: -0.37, volume: 39000, gamma: 0.0001, theta: -34.80, vega: 38.20, bid: 201.50, ask: 202.70 }
        },
        {
          strike: 80200,
          atm: true,
          ce: { ltp: 268.40, oi: 22000, iv: 15.10, delta: 0.51, volume: 85000, gamma: 0.0001, theta: -48.10, vega: 58.00, bid: 267.80, ask: 269.00 },
          pe: { ltp: 248.60, oi: 21500, iv: 15.10, delta: -0.49, volume: 82000, gamma: 0.0001, theta: -47.50, vega: 57.60, bid: 248.00, ask: 249.20 }
        },
        {
          strike: 80300,
          atm: false,
          ce: { ltp: 208.30, oi: 25400, iv: 15.20, delta: 0.39, volume: 62000, gamma: 0.0001, theta: -45.50, vega: 54.20, bid: 207.80, ask: 208.80 },
          pe: { ltp: 312.40, oi: 11200, iv: 15.00, delta: -0.61, volume: 29000, gamma: 0.0001, theta: -36.50, vega: 40.50, bid: 311.80, ask: 313.00 }
        },
        {
          strike: 80400,
          atm: false,
          ce: { ltp: 154.20, oi: 34000, iv: 15.35, delta: 0.29, volume: 49000, gamma: 0.0001, theta: -42.10, vega: 48.90, bid: 153.60, ask: 154.80 },
          pe: { ltp: 388.90, oi: 7800, iv: 14.90, delta: -0.71, volume: 18000, gamma: 0.0001, theta: -30.20, vega: 32.80, bid: 388.00, ask: 389.80 }
        }
      ]
    }
  ]
};

export const mockSpotTrendingOI: Record<'NIFTY' | 'SENSEX', SpotTrendingOIItem[]> = {
  NIFTY: [
    { time: '14:30:00', differenceOi: 1450000, strength: 82, direction: 'BULLISH', directionPercent: 82.4, sentiment: 'EXTREMELY BULLISH', ceOi: 4200000, peOi: 5650000, changeCeOi: -150000, changePeOi: 480000 },
    { time: '14:15:00', differenceOi: 1120000, strength: 78, direction: 'BULLISH', directionPercent: 78.2, sentiment: 'BULLISH', ceOi: 4350000, peOi: 5470000, changeCeOi: -100000, changePeOi: 350000 },
    { time: '14:00:00', differenceOi: 870000, strength: 71, direction: 'BULLISH', directionPercent: 71.5, sentiment: 'BULLISH', ceOi: 4450000, peOi: 5320000, changeCeOi: -50000, changePeOi: 220000 },
    { time: '13:45:00', differenceOi: 700000, strength: 65, direction: 'BULLISH', directionPercent: 65.0, sentiment: 'MODERATELY BULLISH', ceOi: 4500000, peOi: 5200000, changeCeOi: -20000, changePeOi: 180000 },
    { time: '13:30:00', differenceOi: 540000, strength: 58, direction: 'BULLISH', directionPercent: 58.1, sentiment: 'NEUTRAL-BULLISH', ceOi: 4520000, peOi: 5060000, changeCeOi: 10000, changePeOi: 120000 }
  ],
  SENSEX: [
    { time: '14:30:00', differenceOi: -240000, strength: 54, direction: 'BEARISH', directionPercent: 54.0, sentiment: 'MODERATELY BEARISH', ceOi: 1850000, peOi: 1610000, changeCeOi: 85000, changePeOi: -24000 },
    { time: '14:15:00', differenceOi: -180000, strength: 51, direction: 'BEARISH', directionPercent: 51.5, sentiment: 'NEUTRAL-BEARISH', ceOi: 1765000, peOi: 1585000, changeCeOi: 62000, changePeOi: -10000 },
    { time: '14:00:00', differenceOi: -110000, strength: 48, direction: 'NEUTRAL', directionPercent: 48.2, sentiment: 'NEUTRAL', ceOi: 1703000, peOi: 1593000, changeCeOi: 31000, changePeOi: 5000 },
    { time: '13:45:00', differenceOi: -130000, strength: 49, direction: 'NEUTRAL', directionPercent: 49.1, sentiment: 'NEUTRAL', ceOi: 1672000, peOi: 1542000, changeCeOi: 25000, changePeOi: -15000 },
    { time: '13:30:00', differenceOi: -150000, strength: 50, direction: 'NEUTRAL', directionPercent: 50.0, sentiment: 'NEUTRAL', ceOi: 1647000, peOi: 1497000, changeCeOi: 12000, changePeOi: -8000 }
  ]
};

export const mockFutureTrendingOI: Record<'NIFTY' | 'SENSEX', FutureTrendingOIItem[]> = {
  NIFTY: [
    { time: '14:30:00', futurePrice: 24535.10, oiChange: 124000, oiChangePercent: 1.15, priceChange: 14.20, classification: 'LONG BUILDUP', futureOi: 10924000, volume: 840000, basis: 34.90, basisChange: 2.10 },
    { time: '14:15:00', futurePrice: 24520.90, oiChange: 98000, oiChangePercent: 0.91, priceChange: 18.50, classification: 'LONG BUILDUP', futureOi: 10800000, volume: 720000, basis: 32.80, basisChange: 1.80 },
    { time: '14:00:00', futurePrice: 24502.40, oiChange: 45000, oiChangePercent: 0.42, priceChange: -8.10, classification: 'LONG UNWINDING', futureOi: 10702000, volume: 540000, basis: 31.00, basisChange: -1.20 },
    { time: '13:45:00', futurePrice: 24510.50, oiChange: -25000, oiChangePercent: -0.23, priceChange: 11.40, classification: 'SHORT COVERING', futureOi: 10657000, volume: 490000, basis: 32.20, basisChange: 2.50 },
    { time: '13:30:00', futurePrice: 24499.10, oiChange: 85000, oiChangePercent: 0.81, priceChange: -14.60, classification: 'SHORT BUILDUP', futureOi: 10682000, volume: 610000, basis: 29.70, basisChange: -3.40 }
  ],
  SENSEX: [
    { time: '14:30:00', futurePrice: 80315.00, oiChange: -12500, oiChangePercent: -0.32, priceChange: -34.50, classification: 'LONG UNWINDING', futureOi: 3890000, volume: 115000, basis: 74.85, basisChange: -12.40 },
    { time: '14:15:00', futurePrice: 80349.50, oiChange: 8400, oiChangePercent: 0.22, priceChange: -52.10, classification: 'SHORT BUILDUP', futureOi: 3902500, volume: 98000, basis: 87.25, basisChange: -8.50 },
    { time: '14:00:00', futurePrice: 80401.60, oiChange: 15400, oiChangePercent: 0.40, priceChange: 84.10, classification: 'LONG BUILDUP', futureOi: 3894100, volume: 142000, basis: 95.75, basisChange: 15.30 },
    { time: '13:45:00', futurePrice: 80317.50, oiChange: -28000, oiChangePercent: -0.71, priceChange: -12.40, classification: 'LONG UNWINDING', futureOi: 3878700, volume: 88000, basis: 80.45, basisChange: -4.10 },
    { time: '13:30:00', futurePrice: 80329.90, oiChange: 3500, oiChangePercent: 0.09, priceChange: -21.40, classification: 'SHORT BUILDUP', futureOi: 3906700, volume: 72000, basis: 84.55, basisChange: -3.80 }
  ]
};

export const mockStrategies: Strategy[] = [
  {
    id: 'strat-15m-breakout',
    name: '15-Min Breakout',
    status: 'ACTIVE',
    signal: 'BUY CE',
    confidence: 78,
    pnl: 12450.00,
    parameters: { timeFrame: '15m', strikeSelection: 'ATM', bufferPoints: 5, rangeHigh: 24480, rangeLow: 24420 },
    indicators: { VWAP: 24460.50, RSI: 62.4, MACD: 'BULLISH_CROSS' },
    levels: { support: [24400, 24420], resistance: [24500, 24600] },
    oi: 'CE unwinding, PE addition at 24400-24500 strikes',
    historicalStats: { winRate: 64.5, totalTrades: 124 }
  },
  {
    id: 'strat-mean-reversion',
    name: 'Mean Reversion (Bollinger)',
    status: 'ACTIVE',
    signal: 'HOLD',
    confidence: 42,
    pnl: -3200.00,
    parameters: { period: 20, deviation: 2, strikeSelection: 'OTM1' },
    indicators: { lowerBand: 24390, upperBand: 24510, currentVal: 24500 },
    levels: { support: [24380], resistance: [24520] },
    oi: 'Neutral concentration',
    historicalStats: { winRate: 58.2, totalTrades: 95 }
  },
  {
    id: 'strat-scalper',
    name: 'Order Flow Scalper',
    status: 'PAUSED',
    signal: 'HOLD',
    confidence: 0,
    pnl: 4850.00,
    parameters: { imbalanceRatio: 3.0, minVolume: 10000 },
    indicators: { deltaImbalance: 1.2, cumulativeDelta: 145000 },
    levels: { support: [24450], resistance: [24495] },
    oi: 'High volume short coverage',
    historicalStats: { winRate: 71.1, totalTrades: 420 }
  }
];

export const mockPositions: Position[] = [
  {
    id: 'pos-1',
    instrument: 'NIFTY 24500 CE',
    qty: 150,
    ltp: 112.50,
    entry: 80.15,
    avgPrice: 80.15,
    pnl: 4852.50, // (112.50 - 80.15) * 150
    status: 'ACTIVE',
    delta: 0.52,
    gamma: 0.0004,
    theta: -14.80,
    vega: 21.40,
    iv: 14.20,
    oi: 65000,
    stopLoss: 65.00,
    target: 150.00,
    strategy: '15-Min Breakout'
  },
  {
    id: 'pos-2',
    instrument: 'NIFTY 24400 PE',
    qty: 100,
    ltp: 68.30,
    entry: 78.45,
    avgPrice: 78.45,
    pnl: -1015.00, // (68.30 - 78.45) * 100
    status: 'ACTIVE',
    delta: -0.32,
    gamma: 0.0003,
    theta: -9.40,
    vega: 12.80,
    iv: 14.20,
    oi: 59000,
    stopLoss: 110.00,
    target: 30.00,
    strategy: 'Mean Reversion (Bollinger)'
  }
];

export const mockOrders: Order[] = [
  {
    id: 'ord-1',
    time: '14:21:05',
    instrument: 'NIFTY 24500 CE',
    side: 'BUY',
    quantity: 150,
    price: 80.15,
    status: 'COMPLETED',
    brokerOrderId: '984712039',
    strategy: '15-Min Breakout',
    decision: 'Breakout above range resistance 24480',
    risk: 'Within daily draw down limits. Total capital allocated: 1.2%.',
    executionDetails: 'Smart routing via Upstox API. Executed immediately with 2ms slip.'
  },
  {
    id: 'ord-2',
    time: '14:02:11',
    instrument: 'NIFTY 24400 PE',
    side: 'BUY',
    quantity: 100,
    price: 78.45,
    status: 'COMPLETED',
    brokerOrderId: '984711854',
    strategy: 'Mean Reversion (Bollinger)',
    decision: 'Bounce from lower standard deviation band',
    risk: 'Passed risk matrix.',
    executionDetails: 'Executed on NSE. Limit order matched.'
  },
  {
    id: 'ord-3',
    time: '14:28:44',
    instrument: 'NIFTY 24600 CE',
    side: 'SELL',
    quantity: 150,
    price: 68.10,
    status: 'PENDING',
    brokerOrderId: '984712550',
    strategy: '15-Min Breakout',
    decision: 'Hedge position trigger near R1',
    risk: 'Hedge limits verified.',
    executionDetails: 'Placed in NSE Orderbook. Waiting for execution.'
  }
];

export const mockDecisions: Decision[] = [
  {
    id: 'dec-1',
    instrument: 'BUY NIFTY CE',
    confidence: 78,
    expectedValue: 420,
    conflictScore: 12,
    regime: 'TRENDING',
    action: 'BUY CE (ATM strike 24500)',
    supportingFactors: [
      'OI indicates strong PE writing at 24400',
      'Spot price trading cleanly above VWAP',
      '15-Min Range High resistance breakout',
      'Strong institutional positive order flow block'
    ],
    conflictingFactors: [
      'Immediate horizontal resistance at 24600 nearby',
      'VIX slightly elevated (+1.4%)'
    ],
    risk: 'PASSED'
  }
];

export const mockRiskSummary: RiskSummaryData = {
  availableCapital: 1000000.00,
  availableMargin: 482500.00,
  marginUsed: 124500.00,
  dailyPnl: 6240.00,
  dailyLossLimit: -25000.00,
  exposure: 235000.00,
  openPositions: 2,
  riskStatus: 'SAFE',
  detailedCalculations: {
    varValue: 14500.00,
    stressTestResult: 'PASSED - Resilient up to -2.5% market drop',
    leverageRatio: 1.2
  }
};

export const mockBrokerageStatus: BrokerageStatus = {
  brokerName: 'Upstox',
  isConnected: true,
  wsStatus: 'CONNECTED',
  wsLatency: 12,
  marketStatus: 'MARKET OPEN',
  tradingStatus: 'LIVE',
  account: {
    clientId: 'UPS71829',
    name: 'Executive Alpha Trading',
    authStatus: 'AUTHENTICATED'
  }
};
