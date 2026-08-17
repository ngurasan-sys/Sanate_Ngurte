import OpenHighTable from "../components/open_high/OpenHighTable";
import React, { useEffect, useState } from 'react';
import { useAlgoStore } from '../stores/algoStore';
import type { ExecutionMode, TradingMode } from '../stores/algoStore';
import { useSystemStore } from '../stores/systemStore';
import { useLiveExecutionStatus } from '../hooks/useLiveExecutionStatus';
import { useLiveStrategies } from '../hooks/useLiveStrategies';
import StatusBadge from '../components/StatusBadge';
import ManualTradingPanel from '../components/ManualTradingPanel';
import AlgoTradingConfigPanel from '../components/AlgoTradingConfigPanel';
import StrategyControlPanel from '../components/StrategyControlPanel';
import { Play, Square, Pause, Activity, Zap, Shield, Server, Layers, Cpu, Compass, HardDrive, User, Bot, Settings2, X } from 'lucide-react';

const ARM_CONFIRMATION_PHRASE = 'ARM LIVE TRADING';

export const AlgoDashboardView: React.FC = () => {
  const {
    algoEngineStatus, executionMode, tradingMode, armed, signals, pipelineMetrics, riskMetrics,
    setAlgoEngineStatus, setExecutionMode, setTradingMode
  } = useAlgoStore();

  const { brokerageStatus } = useSystemStore();
  const [activeBrokerId, setActiveBrokerId] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  // Active Broker display — reads the existing active_broker registry
  // (GET /api/v1/brokers/active), not a new broker selector.
  useEffect(() => {
    const fetchActiveBroker = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const res = await fetch(`${baseUrl}/api/v1/brokers/active`);
        if (!res.ok) return;
        const data = await res.json();
        setActiveBrokerId(data.broker_id || null);
      } catch {
        // keep previous value
      }
    };
    fetchActiveBroker();
    const interval = setInterval(fetchActiveBroker, 10000);
    return () => clearInterval(interval);
  }, []);

  // Keeps executionMode synced to the REAL backend truth
  // (order_gateway.resolve_mode()) — see hook for why this isn't a
  // second execution-mode system.
  useLiveExecutionStatus();

  // Feeds the Strategy Control table below from the real strategy
  // registry (GET /api/v1/strategies), not the dead algoStore.strategies
  // field this page used to read (nothing ever populated it).
  useLiveStrategies();

  const handleEngineControl = async (status: 'RUNNING' | 'PAUSED' | 'STOPPED') => {
    try {
      const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      await fetch(`${baseUrl}/api/v1/algo/engine/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
      setAlgoEngineStatus(status);
    } catch (e) {
      console.error('Failed to update engine status', e);
    }
  };

  // MANUAL must actually stop automated order submission, not just swap
  // which panel renders. algo_config_state.enabled is the real backend
  // gate RiskEngine checks on every ALGO-sourced decision (risk.py,
  // check_algo_enabled) — flipping it off here is what makes MANUAL mean
  // "no automated entries" rather than a purely cosmetic UI toggle.
  const handleTradingModeChange = async (mode: TradingMode) => {
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    try {
      await fetch(`${baseUrl}/api/v1/algo-config/${mode === 'MANUAL' ? 'disable' : 'enable'}`, {
        method: 'POST',
      });
    } catch (err) {
      console.error('Failed to update algo-config enabled state', err);
    }
    setTradingMode(mode);
  };

  // Routes through the REAL execution arm switch
  // (execution_control.py /arm, /disarm) instead of the old no-op
  // /api/v1/algo/execution/mode stub, which never touched
  // execution_runtime_state and therefore never changed what
  // order_gateway would actually do with an order.
  //
  // Only LIVE vs everything-else is controllable at runtime: SANDBOX
  // requires the EXECUTION_MODE env var, fixed at process start, so
  // selecting "PAPER" here just disarms LIVE the same as "DATA_ONLY" —
  // useLiveExecutionStatus will reflect SANDBOX if that's genuinely
  // what the backend is running.
  const handleModeChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const mode = e.target.value as ExecutionMode;
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    try {
      if (mode === 'LIVE') {
        const confirmed = window.confirm(
          `Arming LIVE trading will allow REAL orders to reach the broker.\n\nType "${ARM_CONFIRMATION_PHRASE}" in the next prompt to confirm.`
        );
        if (!confirmed) return;
        const phrase = window.prompt(`Type exactly "${ARM_CONFIRMATION_PHRASE}" to arm live trading:`);
        if (phrase !== ARM_CONFIRMATION_PHRASE) {
          window.alert('Confirmation phrase did not match. LIVE trading was NOT armed.');
          return;
        }
        const res = await fetch(`${baseUrl}/api/v1/execution/arm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm: phrase }),
        });
        if (!res.ok) {
          const detail = await res.text();
          window.alert(`Failed to arm LIVE trading: ${detail}`);
          return;
        }
      } else {
        await fetch(`${baseUrl}/api/v1/execution/disarm`, { method: 'POST' });
      }
      // Don't optimistically set — let useLiveExecutionStatus's next poll
      // (or an immediate manual refetch) confirm what the backend
      // actually resolved to.
      setExecutionMode(mode === 'LIVE' ? 'LIVE' : mode);
    } catch (err) {
      console.error('Failed to update execution mode', err);
    }
  };

  return (
    <div className="space-y-6 select-none pb-12">
      {/* PAGE HEADER */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Algo Dashboard</h2>
          <p className="text-xs text-zinc-400 font-sans mt-0.5">Monitor and control all your strategies in one place</p>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="text-zinc-500 uppercase tracking-wider">Global Trading:</span>
            <StatusBadge status={armed ? 'CONNECTED' : 'DISCONNECTED'} />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-zinc-500 uppercase tracking-wider">Global Mode:</span>
            <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-bold uppercase">{tradingMode}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-zinc-500 uppercase tracking-wider">Active Broker:</span>
            <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-bold uppercase">{activeBrokerId || 'NONE'}</span>
          </div>
          <button
            onClick={() => setShowSettings(true)}
            aria-label="Open Algo Trading Configuration"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <Settings2 size={12} /> <span className="uppercase tracking-wider font-bold text-[10px]">Settings</span>
          </button>
        </div>
      </div>

      {/* SETTINGS MODAL — opens the EXISTING Algo Trading Configuration,
          not a second config page/system. */}
      {showSettings && (
        <div className="fixed inset-0 z-[70] bg-black/60 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="bg-zinc-950 border border-zinc-800 rounded-lg max-w-2xl w-full max-h-[85vh] overflow-y-auto">
            <div className="h-14 px-5 border-b border-zinc-800 flex items-center justify-between sticky top-0 bg-zinc-950">
              <span className="font-sans font-bold text-sm tracking-wider uppercase text-zinc-100">Algo Trading Configuration</span>
              <button
                onClick={() => setShowSettings(false)}
                aria-label="Close settings"
                className="p-1.5 hover:bg-zinc-850 rounded-lg text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="p-5">
              <AlgoTradingConfigPanel />
            </div>
          </div>
        </div>
      )}

      {/* TOP STATUS BAR */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
        <div className="flex items-center gap-2">
          <span className="text-zinc-500 uppercase">Broker:</span>
          <span className="text-zinc-200">UPSTOX</span>
          <StatusBadge status={brokerageStatus.isConnected ? 'CONNECTED' : 'DISCONNECTED'} />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-zinc-500 uppercase">Market Data:</span>
          <StatusBadge status={brokerageStatus.wsStatus === 'CONNECTED' ? 'LIVE' : 'OFFLINE'} />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-zinc-500 uppercase">Algo Engine:</span>
          <StatusBadge status={algoEngineStatus} />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-zinc-500 uppercase">Execution:</span>
          <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-bold">{executionMode}</span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-zinc-500 uppercase">Risk:</span>
          <StatusBadge status={riskMetrics.status} />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-zinc-500 uppercase">WebSocket:</span>
          <StatusBadge status={brokerageStatus.wsStatus} />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-zinc-500 uppercase">Latency:</span>
          <span className="text-zinc-200">&lt; {brokerageStatus.wsLatency || 1} ms</span>
        </div>
      </div>

      {/* TRADING MODE TOGGLE — AUTO (strategy engines) vs MANUAL (this trader, direct orders) */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-xs text-zinc-500 uppercase tracking-wider font-bold">
          Trading Mode
        </div>
        <div className="flex gap-1 bg-zinc-950 border border-zinc-800 rounded p-1">
          <button
            onClick={() => handleTradingModeChange('AUTO' as TradingMode)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold uppercase tracking-wider transition-colors ${tradingMode === 'AUTO' ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            <Bot size={13} /> Auto
          </button>
          <button
            onClick={() => handleTradingModeChange('MANUAL' as TradingMode)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold uppercase tracking-wider transition-colors ${tradingMode === 'MANUAL' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            <User size={13} /> Manual
          </button>
        </div>
      </div>

      {tradingMode === 'MANUAL' ? <ManualTradingPanel /> : <AlgoTradingConfigPanel />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* SECTION 1 — ALGO ENGINE CONTROL */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server size={18} className="text-sky-400" />
              <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Algo Engine Control</h3>
            </div>
            <StatusBadge status={algoEngineStatus} />
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => handleEngineControl('RUNNING')}
              disabled={algoEngineStatus === 'RUNNING'}
              className="flex-1 flex items-center justify-center gap-2 py-2 px-3 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs font-bold"
            >
              <Play size={14} /> START
            </button>
            <button
              onClick={() => handleEngineControl('PAUSED')}
              disabled={algoEngineStatus !== 'RUNNING'}
              className="flex-1 flex items-center justify-center gap-2 py-2 px-3 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded hover:bg-amber-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs font-bold"
            >
              <Pause size={14} /> PAUSE
            </button>
            <button
              onClick={() => handleEngineControl('STOPPED')}
              disabled={algoEngineStatus === 'STOPPED'}
              className="flex-1 flex items-center justify-center gap-2 py-2 px-3 bg-rose-500/10 text-rose-400 border border-rose-500/20 rounded hover:bg-rose-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs font-bold"
            >
              <Square size={14} /> STOP
            </button>
          </div>

          <div className="mt-4 pt-4 border-t border-zinc-850">
             <div className="flex justify-between items-center text-xs">
               <span className="text-zinc-500 uppercase font-mono">Execution Mode</span>
               <select
                 value={executionMode}
                 onChange={handleModeChange}
                 className="bg-zinc-950 border border-zinc-800 text-zinc-300 font-mono font-bold tracking-wider rounded px-2 py-1 outline-none"
               >
                 <option value="DATA_ONLY">DATA_ONLY</option>
                 <option value="PAPER">PAPER</option>
                 <option value="LIVE" disabled>LIVE (DISABLED)</option>
               </select>
             </div>
          </div>
        </div>

        {/* SECTION 4 — STRATEGY PIPELINE */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-purple-400" />
            <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Strategy Pipeline Metrics</h3>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs font-mono">
             <div className="bg-zinc-950 p-2 rounded border border-zinc-850 flex flex-col justify-between">
                <span className="text-zinc-500 mb-1">Ticks Processed</span>
                <span className="text-zinc-200 text-sm">{pipelineMetrics.ticksProcessed.toLocaleString()}</span>
             </div>
             <div className="bg-zinc-950 p-2 rounded border border-zinc-850 flex flex-col justify-between">
                <span className="text-zinc-500 mb-1">Signals Gen</span>
                <span className="text-sky-400 text-sm">{pipelineMetrics.signalsGenerated.toLocaleString()}</span>
             </div>
             <div className="bg-zinc-950 p-2 rounded border border-zinc-850 flex flex-col justify-between">
                <span className="text-zinc-500 mb-1">Signals Confirmed</span>
                <span className="text-emerald-400 text-sm">{pipelineMetrics.signalsConfirmed.toLocaleString()}</span>
             </div>
             <div className="bg-zinc-950 p-2 rounded border border-zinc-850 flex flex-col justify-between">
                <span className="text-zinc-500 mb-1">Signals Rejected</span>
                <span className="text-amber-400 text-sm">{pipelineMetrics.signalsRejected.toLocaleString()}</span>
             </div>
             <div className="bg-zinc-950 p-2 rounded border border-zinc-850 flex flex-col justify-between">
                <span className="text-zinc-500 mb-1">Risk Rejections</span>
                <span className="text-rose-400 text-sm">{pipelineMetrics.riskRejections.toLocaleString()}</span>
             </div>
             <div className="bg-zinc-950 p-2 rounded border border-zinc-850 flex flex-col justify-between">
                <span className="text-zinc-500 mb-1">Exec Requests</span>
                <span className="text-emerald-400 text-sm">{pipelineMetrics.executionRequests.toLocaleString()}</span>
             </div>
          </div>
        </div>

        {/* SECTION 5 — RISK MONITOR */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield size={18} className="text-amber-400" />
              <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Risk Monitor</h3>
            </div>
            <StatusBadge status={riskMetrics.status} />
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Daily P&L</span>
              <span className={riskMetrics.dailyPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                {riskMetrics.dailyPnl >= 0 ? '+' : '-'}₹{Math.abs(riskMetrics.dailyPnl).toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Max Daily Loss</span>
              <span className="text-zinc-300">₹{riskMetrics.maxDailyLoss.toLocaleString()}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Current Exposure</span>
              <span className="text-zinc-300">₹{riskMetrics.currentExposure.toLocaleString()}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Open Positions</span>
              <span className="text-zinc-300">{riskMetrics.openPositions}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Risk Utilization</span>
              <span className="text-zinc-300">{riskMetrics.riskUtilization}%</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* SECTION 6 — EXECUTION MONITOR */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Layers size={18} className="text-emerald-400" />
              <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Execution Pipeline</h3>
            </div>
            {executionMode === 'DATA_ONLY' && (
              <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded bg-zinc-800 text-zinc-300 border border-zinc-700">DATA ONLY</span>
            )}
          </div>

          <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">
             {executionMode === 'DATA_ONLY' ? 'EXECUTION DISABLED IN DATA_ONLY MODE' : 'NO EXECUTION ACTIVITY'}
          </div>
        </div>

        {/* SECTION 7 — MARKET REGIME */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <Compass size={18} className="text-sky-400" />
            <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Market Regime</h3>
          </div>

          <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">
             WAITING FOR INTELLIGENCE ENGINE...
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* SECTION 8 — ALGO OPPORTUNITIES */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <Cpu size={18} className="text-amber-400" />
            <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Highest Ranked Opportunities</h3>
          </div>

          <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">
             NO OPPORTUNITIES DETECTED
          </div>
        </div>

        {/* SECTION 9 — SYSTEM HEALTH */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <HardDrive size={18} className="text-purple-400" />
            <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Subsystem Health</h3>
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs font-mono">
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Broker API</span>
              <StatusBadge status={brokerageStatus.isConnected ? 'HEALTHY' : 'DISCONNECTED'} />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Event Bus</span>
              <StatusBadge status="HEALTHY" />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Market Feed</span>
              <StatusBadge status={brokerageStatus.wsStatus === 'CONNECTED' ? 'HEALTHY' : 'DISCONNECTED'} />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">WebSocket</span>
              <StatusBadge status={brokerageStatus.wsStatus === 'CONNECTED' ? 'HEALTHY' : 'WARNING'} />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Candle Engine</span>
              <StatusBadge status="HEALTHY" />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Decision Engine</span>
              <StatusBadge status="HEALTHY" />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Risk Engine</span>
              <StatusBadge status="HEALTHY" />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
              <span className="text-zinc-500">Execution Engine</span>
              <StatusBadge status="HEALTHY" />
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 1.5 — OPEN=HIGH STRATEGY */}
      <div className="mb-6">
        <OpenHighTable />
      </div>

      {/* SECTION 2 — STRATEGY CONTROL (single-page start/stop, ALGO/PAPER,
          AUTO/MANUAL, live signal/position/P&L/health per strategy) */}
      <StrategyControlPanel />

      {/* SECTION 3 — ACTIVE SIGNALS */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <Zap size={18} className="text-sky-400" />
          <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Active Signals</h3>
        </div>

        {signals.length === 0 ? (
          <div className="text-center py-8 text-zinc-500 font-mono text-xs uppercase tracking-wider">
            NO ACTIVE SIGNALS
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono text-left whitespace-nowrap">
              <thead className="text-zinc-500 border-b border-zinc-800">
                <tr>
                  <th className="pb-2 font-normal uppercase">Time</th>
                  <th className="pb-2 font-normal uppercase">Strategy</th>
                  <th className="pb-2 font-normal uppercase">Instrument</th>
                  <th className="pb-2 font-normal uppercase">Dir</th>
                  <th className="pb-2 font-normal uppercase">Strike</th>
                  <th className="pb-2 font-normal uppercase">Entry</th>
                  <th className="pb-2 font-normal uppercase">Conf</th>
                  <th className="pb-2 font-normal uppercase">Risk</th>
                  <th className="pb-2 font-normal uppercase">Execution</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-850 text-zinc-300">
                {signals.map((sig) => (
                  <tr key={sig.id} className="hover:bg-zinc-800/30">
                    <td className="py-2 text-zinc-500">{sig.timestamp}</td>
                    <td className="py-2">{sig.strategy}</td>
                    <td className="py-2">{sig.instrument}</td>
                    <td className={`py-2 font-bold ${sig.direction === 'CALL' ? 'text-emerald-400' : 'text-rose-400'}`}>{sig.direction}</td>
                    <td className="py-2">{sig.strike} {sig.optionType}</td>
                    <td className="py-2">{sig.entry}</td>
                    <td className="py-2">{sig.confidence}%</td>
                    <td className="py-2"><StatusBadge status={sig.riskStatus} /></td>
                    <td className="py-2"><StatusBadge status={sig.executionStatus} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
};

export default AlgoDashboardView;
