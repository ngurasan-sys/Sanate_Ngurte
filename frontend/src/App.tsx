import React, { useState } from 'react';
import AppShell from './components/AppShell';
import { useUiStore } from './stores/uiStore';
import { useMarketStore } from './stores/marketStore';
import { usePortfolioStore } from './stores/portfolioStore';
import { useLiveFeedSimulator } from './stores/useLiveFeedSimulator';
import { mockOptionChains } from './mock/data';

// Reusable / specific view panels
import MetricCard from './components/MetricCard';
import StatusBadge from './components/StatusBadge';
import OIPanel from './components/OIPanel';
import FutureTrendingOIPanel from './components/FutureTrendingOIPanel';
import OptionChainPanel from './components/OptionChainPanel';
import GreeksPanel from './components/GreeksPanel';
import LevelPanel from './components/LevelPanel';
import StrategyPanel from './components/StrategyPanel';
import DecisionPanel from './components/DecisionPanel';
import DetailDrawer from './components/DetailDrawer';
import RiskPanel from './components/RiskPanel';
import PositionPanel from './components/PositionPanel';
import OrderPanel from './components/OrderPanel';
import BrokeragePanel from './components/BrokeragePanel';
import EmptyState from './components/EmptyState';

import { Activity, BarChart2, ShieldAlert, Wifi } from 'lucide-react';

export const App: React.FC = () => {
  // Start simulated WebSocket/LTP stream updates
  useLiveFeedSimulator();

  const { activePage } = useUiStore();
  const { indices } = useMarketStore();
  const { totalPnl, todayPnl, positions } = usePortfolioStore();

  // Control for Decision Detail Drawer
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);

  // Expiry dates helper
  const nifty = indices.NIFTY;
  const sensex = indices.SENSEX;

  // Active NIFTY chain helper for live log updates
  const niftyChains = mockOptionChains['NIFTY'];
  const activeChain = niftyChains && niftyChains[0];

  // Render a generic summary block helper
  const renderIndexDetailCard = (symbol: 'NIFTY' | 'SENSEX') => {
    const data = indices[symbol];
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <span className="font-sans font-bold text-sm tracking-wider uppercase text-zinc-100">{symbol} Summary</span>
          <StatusBadge status={data.trend} />
        </div>
        <div className="grid grid-cols-2 gap-4 font-mono text-xs text-zinc-400">
          <div>
            <span className="text-zinc-500 block">Spot:</span>
            <span className="text-sm font-semibold text-zinc-100">₹{data.spot.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">VWAP:</span>
            <span className="text-sm font-semibold text-zinc-100">₹{data.vwap.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Support:</span>
            <span className="text-sm font-semibold text-emerald-400">₹{data.support.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Resistance:</span>
            <span className="text-sm font-semibold text-rose-400">₹{data.resistance.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">IV %:</span>
            <span className="text-sm font-semibold text-zinc-100">{data.iv}%</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Expected Move:</span>
            <span className="text-sm font-semibold text-zinc-100">±{data.expectedMove}</span>
          </div>
        </div>
      </div>
    );
  };

  // Render Router based on Active Page State
  const renderPageContent = () => {
    switch (activePage) {
      case 'DASHBOARD':
        return (
          <div className="space-y-8 select-none">
            {/* Header / Intro */}
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Trading Workstation Dashboard</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Minimalist, spacious overview of systems, strategies, decision score and risk controls.</p>
            </div>

            {/* Top Index Tickers Summary */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {renderIndexDetailCard('NIFTY')}
              {renderIndexDetailCard('SENSEX')}
            </div>

            {/* Portfolio Summary */}
            <div className="space-y-4">
              <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Portfolio & Margin Summary</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                <MetricCard
                  label="Total Realized P&L"
                  value={`${totalPnl >= 0 ? '+' : ''}₹${totalPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
                  subValueColor={totalPnl >= 0 ? 'bullish' : 'bearish'}
                  subValue="All-time compiled"
                />
                <MetricCard
                  label="Today's P&L"
                  value={`${todayPnl >= 0 ? '+' : ''}₹${todayPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
                  subValueColor={todayPnl >= 0 ? 'bullish' : 'bearish'}
                  subValue="Live MTM ticks"
                />
                <MetricCard
                  label="Active Positions"
                  value={positions.filter(p => p.status === 'ACTIVE').length}
                  subValue="Working on market"
                />
                <MetricCard
                  label="Available Margin"
                  value="₹4,82,500"
                  subValue="Margin used: ₹1,24,500"
                />
              </div>
            </div>

            {/* Strategic Overview Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Left Column: Decision Intel */}
              <div className="space-y-4">
                <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Executive Decision Intelligence</h3>
                <DecisionPanel onOpenDrawer={(id) => setSelectedDecisionId(id)} />
              </div>

              {/* Right Column: Strategy overview */}
              <div className="space-y-4">
                <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Top Performing Strategy</h3>
                <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm text-zinc-200">15-Min Breakout</span>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-sans font-bold">
                      ACTIVE
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                    <div>
                      <span className="text-zinc-500">Live Signal:</span>
                      <p className="text-zinc-100 font-bold mt-0.5">BUY CE</p>
                    </div>
                    <div>
                      <span className="text-zinc-500">Confidence Score:</span>
                      <p className="text-emerald-400 font-bold mt-0.5">78%</p>
                    </div>
                    <div>
                      <span className="text-zinc-500">Parameters:</span>
                      <p className="text-zinc-400 mt-0.5">Strike: ATM | TF: 15m</p>
                    </div>
                    <div>
                      <span className="text-zinc-500">Historical win-rate:</span>
                      <p className="text-zinc-100 font-bold mt-0.5">64.5% (124 trades)</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );

      case 'MARKET_NIFTY':
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">NIFTY index levels & overview</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Comprehensive Spot and derivatives risk analytics</p>
            </div>
            {renderIndexDetailCard('NIFTY')}
            <LevelPanel />
          </div>
        );

      case 'MARKET_SENSEX':
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">SENSEX index levels & overview</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Comprehensive Spot and derivatives risk analytics</p>
            </div>
            {renderIndexDetailCard('SENSEX')}
            <LevelPanel />
          </div>
        );

      case 'SPOT_OI':
        return <OIPanel />;

      case 'FUTURE_OI':
        return <FutureTrendingOIPanel />;

      case 'OPTION_CHAIN':
        return <OptionChainPanel />;

      case 'GREEKS':
        return <GreeksPanel />;

      case 'LEVELS':
        return <LevelPanel />;

      case 'TECHNICAL':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Technical Indicator Matrix</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Configurable indicator filters including EMA, SMA, VWAP, RSI, MACD, Bollinger Bands, ATR and Supertrend.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[
                { name: 'Exponential Moving Average (EMA)', value: '24,482.10', status: 'Above (Bullish)', valColor: 'text-emerald-400' },
                { name: 'Relative Strength Index (RSI)', value: '62.40', status: 'Moderate (Neutral)', valColor: 'text-zinc-200' },
                { name: 'MACD Hist', value: '+14.50', status: 'Bullish Crossover', valColor: 'text-emerald-400' },
                { name: 'Average True Range (ATR)', value: '185.20', status: 'High Volatility', valColor: 'text-rose-400' },
                { name: 'Supertrend (7, 3)', value: '24,390.00', status: 'BUY Triggered', valColor: 'text-emerald-400' },
                { name: 'Bollinger Bands (20, 2)', value: '24,510 - 24,390', status: 'Nearing Upper Dev', valColor: 'text-zinc-200' },
              ].map((ind, idx) => (
                <div key={idx} className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-3 font-mono text-xs">
                  <p className="font-sans font-semibold text-zinc-400">{ind.name}</p>
                  <p className={`text-xl font-bold ${ind.valColor}`}>{ind.value}</p>
                  <div className="flex justify-between text-[11px] text-zinc-500">
                    <span>STATE ASSESSMENT:</span>
                    <span className="font-sans font-bold uppercase">{ind.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );

      case 'ORDER_FLOW':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Real-time Order Flow Analytics</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Aggressive buying blocks and cumulative volume delta (CVD) tracking.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              <MetricCard label="Cumulative Volume Delta" value="+1,45,000" subValue="Aggressive buying surge" subValueColor="bullish" />
              <MetricCard label="Bid/Ask Imbalance" value="3.4x Buying" subValue="High institutional demand" subValueColor="bullish" />
              <MetricCard label="Consolidated Spread" value="0.05" subValue="Ultra-liquid optimal entry" subValueColor="neutral" />
            </div>

            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 font-sans text-xs text-zinc-400 space-y-4">
              <h4 className="font-bold text-zinc-100 uppercase tracking-wider">Subtle order flow imbalance logs</h4>
              <div className="space-y-2 font-mono">
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                  <span className="text-zinc-500">14:29:58 - Imbalance CE Strike 24500:</span>
                  <span className="text-emerald-400">BUY Block 85,000 qty @ 112.10</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                  <span className="text-zinc-500">14:29:12 - Spread execution:</span>
                  <span className="text-zinc-300">Smart route routing via Upstox optimal book match</span>
                </div>
                <div className="flex justify-between pb-1">
                  <span className="text-zinc-500">14:28:44 - Imbalance PE Strike 24400:</span>
                  <span className="text-rose-400">SELL Block 45,000 qty @ 78.45</span>
                </div>
              </div>
            </div>
          </div>
        );

      case 'QUANT':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Deterministic Quant Research</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Real-time returns distribution, Z-scores and probability matrices.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              <MetricCard label="Volatility Z-Score" value="1.14" subValue="Slightly above normal" subValueColor="neutral" />
              <MetricCard label="Expected Move Prob" value="68% within 24,620" subValue="Gaussian Distribution" subValueColor="neutral" />
              <MetricCard label="Signal Noise Ratio (SNR)" value="4.20" subValue="Clear breakout pattern" subValueColor="bullish" />
            </div>

            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4 font-mono text-xs text-zinc-400">
              <h4 className="font-sans font-bold text-zinc-100 uppercase tracking-wider">Model feature scoring metadata</h4>
              <div className="space-y-2">
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                  <span>Chronological Split walk-forward validation:</span>
                  <span className="text-emerald-400 font-semibold">PASSED</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                  <span>Sharpe Ratio (Annualized):</span>
                  <span className="text-zinc-200">2.42</span>
                </div>
                <div className="flex justify-between pb-1">
                  <span>Sortino Ratio (Downside variance):</span>
                  <span className="text-zinc-200">3.15</span>
                </div>
              </div>
            </div>
          </div>
        );

      case 'STRATEGY_MONITOR':
        return <StrategyPanel />;

      case 'LIVE_SIGNALS':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Real-time Signals Audit Stream</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Live trigger logs with complete confidence tracking and entry buffer criteria.</p>
            </div>

            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-emerald-400" />
                <h4 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">Intraday Strategy Triggers</h4>
              </div>

              <div className="space-y-3 font-mono text-xs text-zinc-300">
                {[
                  { time: '14:21:05', strategy: '15-Min Breakout', action: 'BUY CE', status: 'FILLED', conf: '78%' },
                  { time: '14:02:11', strategy: 'Mean Reversion (Bollinger)', action: 'BUY PE', status: 'FILLED', conf: '42%' },
                  { time: '13:30:00', strategy: 'Order Flow Scalper', action: 'HOLD', status: 'TRIGGERED', conf: '55%' },
                ].map((sig, idx) => (
                  <div key={idx} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
                    <div className="flex items-center gap-3">
                      <span className="text-zinc-500">{sig.time}</span>
                      <span className="font-bold text-zinc-100">{sig.strategy}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-emerald-400 font-semibold">{sig.action}</span>
                      <span className="text-zinc-400">Confidence: {sig.conf}</span>
                      <StatusBadge status={sig.status} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );

      case 'BACKTEST':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Quantitative Historical Backtest reports</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Robust parameter optimization preventing future look-ahead and overlap contamination.</p>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <MetricCard label="CAGR %" value="42.5%" />
              <MetricCard label="Profit Factor" value="1.84" />
              <MetricCard label="Max Drawdown" value="-8.42%" subValueColor="bearish" />
              <MetricCard label="Sharpe Ratio" value="2.45" />
            </div>

            {/* Backtest table summary */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
              <h4 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">Strategy Backtest runs</h4>
              <div className="space-y-3 text-xs font-mono text-zinc-400">
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                  <span className="font-sans text-zinc-300 font-bold">15-Min Range breakout model:</span>
                  <span className="text-emerald-400 font-semibold">PASSED (CAGR: 45.1%, Sharpe: 2.6)</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                  <span className="font-sans text-zinc-300 font-bold">Bollinger Bands Mean Reversion:</span>
                  <span className="text-zinc-300">PASSED (CAGR: 28.2%, Sharpe: 1.8)</span>
                </div>
                <div className="flex justify-between pb-1">
                  <span>Slippage and latency assumptions model:</span>
                  <span className="text-zinc-500">1.2ms avg network delay calculated</span>
                </div>
              </div>
            </div>
          </div>
        );

      case 'DECISION_INTEL':
        return <DecisionPanel onOpenDrawer={(id) => setSelectedDecisionId(id)} />;

      case 'POSITIONS':
        return <PositionPanel />;

      case 'ORDERS':
        return <OrderPanel />;

      case 'PNL':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Workstation Compiled P&L tracking</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Dynamic mark-to-market returns ledger.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              <MetricCard label="Realized MTM" value="+₹18,450" subValueColor="bullish" />
              <MetricCard label="Unrealized MTM" value="+₹4,852.50" subValueColor="bullish" />
              <MetricCard label="Total Charges" value="₹340.00" subValueColor="bearish" />
              <MetricCard label="Net Return %" value="+4.85%" subValueColor="bullish" />
            </div>

            <PositionPanel />
          </div>
        );

      case 'RISK':
        return <RiskPanel />;

      case 'UPSTOX':
        return <BrokeragePanel />;

      case 'SYSTEM_HEALTH':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">System Health & Telemetry Logs</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Secure local-first execution status logs.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
                <div className="flex items-center gap-2">
                  <Wifi className="text-emerald-400" size={16} />
                  <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Networking Logs</h4>
                </div>
                <div className="space-y-2 font-mono text-xs text-zinc-400">
                  <div className="flex justify-between">
                    <span>WebSocket Endpoint:</span>
                    <span className="text-emerald-400">ONLINE</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Handshake Latency:</span>
                    <span>12ms</span>
                  </div>
                </div>
              </div>

              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
                <div className="flex items-center gap-2">
                  <BarChart2 className="text-sky-400" size={16} />
                  <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Database Status</h4>
                </div>
                <div className="space-y-2 font-mono text-xs text-zinc-400">
                  <div className="flex justify-between">
                    <span>DuckDB Session:</span>
                    <span className="text-emerald-400">CONNECTED</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Parquet engine:</span>
                    <span>ACTIVE</span>
                  </div>
                </div>
              </div>

              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="text-amber-400" size={16} />
                  <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Core Guardrails</h4>
                </div>
                <div className="space-y-2 font-mono text-xs text-zinc-400">
                  <div className="flex justify-between">
                    <span>Risk Guard Guardrails:</span>
                    <span className="text-emerald-400">PASSED</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Session lock:</span>
                    <span>SAFE</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );

      case 'DATA_FEED':
        return (
          <div className="space-y-6 select-none">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">WebSockets Live Normalizer Feed</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Incremental feed status with zero layout jitter.</p>
            </div>

            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-sky-400" />
                <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Normalization Streams logs</h4>
              </div>
              <div className="space-y-2 font-mono text-xs text-zinc-400">
                <div className="p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
                  <span className="text-zinc-500">14:29:58 -</span> Normalizer mapped tick: NIFTY Spot: <span className="text-zinc-100">{nifty.spot.toFixed(2)}</span>, Change: <span className={nifty.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{nifty.change.toFixed(2)}</span>
                </div>
                <div className="p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
                  <span className="text-zinc-500">14:29:58 -</span> Normalizer mapped tick: SENSEX Spot: <span className="text-zinc-100">{sensex.spot.toFixed(2)}</span>, Change: <span className={sensex.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{sensex.change.toFixed(2)}</span>
                </div>
                <div className="p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
                  <span className="text-zinc-500">14:29:58 -</span> Option normalizer snapshot: CE strike 24500 ltp updated to <span className="text-emerald-400">₹{activeChain?.strikes.find((s) => s.strike === 24500)?.ce.ltp}</span>
                </div>
              </div>
            </div>
          </div>
        );

      default:
        return <EmptyState title="Page Not Found" />;
    }
  };

  return (
    <AppShell>
      {renderPageContent()}

      {/* Slide-out detail drawer for decisions */}
      <DetailDrawer
        decisionId={selectedDecisionId}
        onClose={() => setSelectedDecisionId(null)}
      />
    </AppShell>
  );
};

export default App;
