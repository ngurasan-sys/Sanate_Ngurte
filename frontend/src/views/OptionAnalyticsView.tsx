import React from 'react';
import { Activity } from 'lucide-react';
import { useOptionAnalyticsStore } from '../stores/optionAnalyticsStore';
import { useOptionAnalyticsWebSocket } from '../hooks/useOptionAnalyticsWebSocket';
import MetricCard from '../components/MetricCard';
import StatusBadge from '../components/StatusBadge';

const fmtPct = (v: number | null, digits = 2) => (v === null ? '--' : `${v.toFixed(digits)}%`);
const fmtNum = (v: number | null, digits = 2) => (v === null ? '--' : v.toFixed(digits));

export const OptionAnalyticsView: React.FC = () => {
  useOptionAnalyticsWebSocket();
  const state = useOptionAnalyticsStore();

  if (!state.timestamp || state.connectionStatus !== 'CONNECTED') {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full bg-[#0a0f1c] text-slate-400 gap-4 min-h-[600px]">
        <Activity className="animate-spin" size={32} />
        <p className="font-mono text-sm tracking-widest uppercase">Awaiting Option Chain & Analytics State...</p>
      </div>
    );
  }

  const { ivRegime, pcrReversal, svi, vrp } = state;

  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Option Analytics</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">
          Live IV regime, PCR reversal, SVI volatility surface & VRP forecast — {state.underlyingKey}
        </p>
      </div>

      {/* Top metric row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
        <MetricCard label="Spot Price" value={state.spotPrice !== null ? `₹${state.spotPrice.toFixed(2)}` : '--'} />
        <MetricCard label="ATM Strike" value={state.atmStrike !== null ? state.atmStrike.toFixed(0) : '--'} />
        <MetricCard
          label="SVI ATM IV"
          value={svi?.atmIv !== null && svi?.atmIv !== undefined ? `${(svi.atmIv * 100).toFixed(2)}%` : '--'}
          subValue={svi?.arbitrageFree === false ? 'Arbitrage check failed' : svi?.arbitrageFree === true ? 'Arbitrage-free fit' : undefined}
          subValueColor={svi?.arbitrageFree === false ? 'bearish' : svi?.arbitrageFree === true ? 'bullish' : 'neutral'}
        />
        <MetricCard
          label="PCR"
          value={fmtNum(pcrReversal?.pcr ?? null)}
          subValue={pcrReversal?.zone}
          subValueColor={pcrReversal?.zone === 'HIGH_EXTREME' ? 'bearish' : pcrReversal?.zone === 'LOW_EXTREME' ? 'bullish' : 'neutral'}
        />
        <MetricCard
          label="Vol Risk Premium"
          value={vrp?.vrp !== null && vrp?.vrp !== undefined ? `${(vrp.vrp * 100).toFixed(2)} pts` : '--'}
          subValue={vrp?.classification}
          subValueColor={vrp?.classification === 'IV_RICH' ? 'bearish' : vrp?.classification === 'IV_CHEAP' ? 'bullish' : 'neutral'}
        />
      </div>

      {/* IV Regime & PCR Reversal */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
          <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">IV Regime</h4>
          {!ivRegime?.sufficientData ? (
            <p className="text-xs text-zinc-500 font-mono">{ivRegime?.reason || 'Insufficient data.'}</p>
          ) : (
            <div className="space-y-2 font-mono text-xs text-zinc-400">
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>ATM IV:</span>
                <span className="text-zinc-100 font-bold">{fmtPct(ivRegime.atmIv)}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Intraday Baseline:</span>
                <span>{fmtPct(ivRegime.baselineIv)}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Change vs Baseline:</span>
                <span className={ivRegime.ivChangePct !== null && ivRegime.ivChangePct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  {ivRegime.ivChangePct !== null ? `${ivRegime.ivChangePct >= 0 ? '+' : ''}${ivRegime.ivChangePct.toFixed(1)}%` : '--'}
                </span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Regime:</span>
                <StatusBadge status={ivRegime.regime} />
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Put/Call Skew:</span>
                <span>{ivRegime.skew !== null ? `${ivRegime.skew.toFixed(2)} (${ivRegime.skewBias})` : '--'}</span>
              </div>
              <div className="flex justify-between pb-1">
                <span>Signal:</span>
                <StatusBadge status={ivRegime.signal} />
              </div>
              {ivRegime.reasoning && (
                <p className="text-[11px] text-zinc-500 pt-2 border-t border-zinc-850">{ivRegime.reasoning}</p>
              )}
            </div>
          )}
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
          <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">PCR Extreme Reversal</h4>
          {!pcrReversal?.sufficientData ? (
            <p className="text-xs text-zinc-500 font-mono">{pcrReversal?.reason || 'Insufficient data.'}</p>
          ) : (
            <div className="space-y-2 font-mono text-xs text-zinc-400">
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>PCR:</span>
                <span className="text-zinc-100 font-bold">{fmtNum(pcrReversal.pcr)}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Session Peak:</span>
                <span>{fmtNum(pcrReversal.pcrPeak)}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Session Trough:</span>
                <span>{fmtNum(pcrReversal.pcrTrough)}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Zone:</span>
                <StatusBadge status={pcrReversal.zone} />
              </div>
              <div className="flex justify-between pb-1">
                <span>Signal:</span>
                <StatusBadge status={pcrReversal.signal} />
              </div>
              {pcrReversal.reasoning && (
                <p className="text-[11px] text-zinc-500 pt-2 border-t border-zinc-850">{pcrReversal.reasoning}</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* SVI Surface Fit */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">SVI Volatility Surface Fit</h4>
        {!svi?.sufficientData ? (
          <p className="text-xs text-zinc-500 font-mono">{svi?.reason || 'Insufficient data.'}</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
            <div className="space-y-2 font-mono text-xs text-zinc-400">
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Expiry:</span>
                <span className="text-zinc-100">{svi.expiry}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Time to Expiry:</span>
                <span>{svi.tauYears !== null ? `${(svi.tauYears * 365).toFixed(1)} days` : '--'}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>Forward Price:</span>
                <span>{svi.forward !== null ? `₹${svi.forward.toFixed(2)}` : '--'}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>ATM IV:</span>
                <span className="text-zinc-100 font-bold">{svi.atmIv !== null ? `${(svi.atmIv * 100).toFixed(2)}%` : '--'}</span>
              </div>
              <div className="flex justify-between pb-1">
                <span>Skew Proxy (put - call):</span>
                <span>{svi.skew !== null ? `${(svi.skew * 100).toFixed(2)} vol pts` : '--'}</span>
              </div>
            </div>

            <div className="space-y-2 font-mono text-xs text-zinc-400">
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>No-Arbitrage Check:</span>
                <StatusBadge status={svi.arbitrageFree ? 'PASSED' : 'FAILED'} />
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>a:</span>
                <span>{svi.params ? svi.params.a.toFixed(5) : '--'}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>b:</span>
                <span>{svi.params ? svi.params.b.toFixed(5) : '--'}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-850 pb-2">
                <span>rho:</span>
                <span>{svi.params ? svi.params.rho.toFixed(3) : '--'}</span>
              </div>
              <div className="flex justify-between pb-1">
                <span>m / sigma:</span>
                <span>{svi.params ? `${svi.params.m.toFixed(3)} / ${svi.params.sigma.toFixed(3)}` : '--'}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Volatility Risk Premium */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Volatility Risk Premium (SVI IV vs HAR-RV Forecast)</h4>
        {!vrp?.sufficientData ? (
          <p className="text-xs text-zinc-500 font-mono">{vrp?.reason || 'Insufficient data.'}</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Implied Vol (SVI)</span>
              <span className="font-mono tabular-nums text-xl font-semibold text-zinc-100">
                {vrp.impliedVol !== null ? `${(vrp.impliedVol * 100).toFixed(2)}%` : '--'}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Forecast Vol (HAR-RV)</span>
              <span className="font-mono tabular-nums text-xl font-semibold text-zinc-100">
                {vrp.forecastVol !== null ? `${(vrp.forecastVol * 100).toFixed(2)}%` : '--'}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">VRP</span>
              <span className={`font-mono tabular-nums text-xl font-semibold ${vrp.vrp !== null && vrp.vrp >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {vrp.vrp !== null ? `${vrp.vrp >= 0 ? '+' : ''}${(vrp.vrp * 100).toFixed(2)} pts` : '--'}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Z-Score</span>
              <span className="font-mono tabular-nums text-xl font-semibold text-zinc-100">
                {vrp.zScore !== null ? vrp.zScore.toFixed(2) : '--'}
              </span>
            </div>
            <div className="flex flex-col gap-2">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Classification / Signal</span>
              <div className="flex items-center gap-2">
                <StatusBadge status={vrp.classification} />
                <StatusBadge status={vrp.signal} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default OptionAnalyticsView;
