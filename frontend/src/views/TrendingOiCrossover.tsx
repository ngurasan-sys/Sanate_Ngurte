import React, { useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceArea, ReferenceLine } from 'recharts';
import { useOptionStore } from '../stores/optionStore';
import { Flame, Clock, Navigation, AlertTriangle } from 'lucide-react';
import { formatIndianNumber } from '../utils/format';

const StatusCard: React.FC<{
  title: string;
  icon: React.ReactNode;
  statusText: string;
  subText: string;
  status: 'VALID' | 'BLOCKED' | 'NEUTRAL';
}> = ({ title, icon, statusText, subText, status }) => {
  let colorClass = 'text-zinc-400 border-zinc-800 bg-zinc-900';
  let iconColor = 'text-zinc-500';

  if (status === 'VALID') {
    colorClass = 'border-emerald-500/20 bg-emerald-500/5';
    iconColor = 'text-emerald-400';
  } else if (status === 'BLOCKED') {
    colorClass = 'border-rose-500/20 bg-rose-500/5';
    iconColor = 'text-rose-400';
  }

  return (
    <div className={`p-4 rounded-xl border ${colorClass} flex flex-col gap-2`}>
      <div className="flex items-center gap-2 text-xs font-bold tracking-wider text-zinc-500">
        <span className={iconColor}>{icon}</span>
        {title}
      </div>
      <div className={`text-lg font-bold font-sans ${status === 'VALID' ? 'text-emerald-400' : status === 'BLOCKED' ? 'text-rose-400' : 'text-zinc-300'}`}>
        {statusText}
      </div>
      <div className="text-xs text-zinc-500 font-mono">
        {subText}
      </div>
    </div>
  );
};

export const TrendingOiCrossover: React.FC = () => {
  const { spotTrendingOI, startWsLiveFeed } = useOptionStore();
  const currentSymbol = 'NIFTY';
  const data = spotTrendingOI[currentSymbol] || [];

  useEffect(() => {
    startWsLiveFeed();
  }, [startWsLiveFeed]);

  const latestData = data.length > 0 ? data[0] : null;

  const chartData = useMemo(() => {
    return [...data].reverse().map(d => {
      // Parse time to a comparable number for axis
      const parsedTime = new Date(`1970/01/01 ${d.time}`).getTime();
      return {
        ...d,
        ceOiValue: d.ceOi,
        peOiValue: d.peOi,
        timeNum: isNaN(parsedTime) ? 0 : parsedTime
      };
    });
  }, [data]);

  // Find crossovers for reference dots/lines
  const crossovers = useMemo(() => {
    return chartData.filter(d => d.crossover === 'BULLISH_CROSSOVER' || d.crossover === 'BEARISH_CROSSOVER');
  }, [chartData]);

  // Signal Card state logic
  let activeSignalState = 'WAITING';
  let activeSignalColor = 'text-sky-400 bg-sky-500/10 border-sky-500/20';

  if (latestData) {
    if (!latestData.trade_valid && latestData.time_filter_status === 'BLOCKED') {
      activeSignalState = 'Trading Paused: Post 2:30 PM';
      activeSignalColor = 'text-rose-400 bg-rose-500/10 border-rose-500/20';
    } else if (!latestData.trade_valid && latestData.distance_filter_status === 'BLOCKED') {
      activeSignalState = 'Trading Paused: VWAP and SuperTrend too wide';
      activeSignalColor = 'text-rose-400 bg-rose-500/10 border-rose-500/20';
    } else if (latestData.execution_state && latestData.execution_state !== 'IDLE' && latestData.execution_state !== 'WAITING') {
      activeSignalState = latestData.execution_state.replace(/_/g, ' ');
      if (activeSignalState.includes('FILLED') || activeSignalState.includes('PROFIT')) {
        activeSignalColor = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      } else {
        activeSignalColor = 'text-amber-400 bg-amber-500/10 border-amber-500/20';
      }
    } else if (latestData.trade_valid) {
      activeSignalState = 'Setup Valid — Awaiting Entry';
      activeSignalColor = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
    }
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const dataPoint = payload[0].payload;
      return (
        <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg shadow-xl text-xs font-mono">
          <p className="text-zinc-400 mb-2">{label}</p>
          <div className="flex justify-between gap-4">
            <span className="text-rose-400">Call OI:</span>
            <span className="text-zinc-100">{formatIndianNumber(dataPoint.ceOiValue)}</span>
          </div>
          <div className="flex justify-between gap-4 mt-1">
            <span className="text-emerald-400">Put OI:</span>
            <span className="text-zinc-100">{formatIndianNumber(dataPoint.peOiValue)}</span>
          </div>
          {dataPoint.crossover !== 'NO_CROSSOVER' && dataPoint.crossover && (
            <div className={`mt-2 font-bold ${dataPoint.crossover === 'BULLISH_CROSSOVER' ? 'text-emerald-400' : 'text-rose-400'}`}>
              {dataPoint.crossover.replace('_', ' ')}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="p-6 bg-[#0a0f1c] min-h-screen text-zinc-100 font-sans space-y-8 select-none">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold tracking-wider uppercase text-zinc-100 flex items-center gap-2">
          <Flame className="text-rose-500" size={20} />
          Trending OI Crossover
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Real-time Call vs Put Open Interest Crossover Analysis.</p>
      </div>

      {/* Active Signal Card */}
      <div className={`p-4 rounded-xl border ${activeSignalColor} flex items-center justify-between`}>
        <div className="flex flex-col">
          <span className="text-xs font-bold tracking-widest uppercase opacity-70 mb-1">Market Status / Active Signal</span>
          <span className="text-xl font-bold">{activeSignalState}</span>
        </div>
        <div className="h-10 w-10 rounded-full bg-current opacity-10 animate-pulse"></div>
      </div>

      {/* Main Chart Area */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 h-[400px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <defs>
              <linearGradient id="colorCall" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorPut" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="timeNum" scale="time" type="number" domain={['dataMin', 'dataMax']} stroke="#52525b" fontSize={12} tickMargin={10} tickFormatter={(val) => { const d = new Date(val); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`; }} />
            <YAxis stroke="#52525b" fontSize={12} tickFormatter={(val) => `${(val / 100000).toFixed(1)}L`} domain={['auto', 'auto']} />
            <Tooltip content={<CustomTooltip />} />

            {/* Overlay for post-3:00 PM */}
            <ReferenceArea x1={new Date("1970/01/01 15:00:00").getTime()} x2={new Date("1970/01/01 15:30:00").getTime()} fill="#000000" fillOpacity={0.4} />

            <Area type="monotone" dataKey="ceOiValue" name="Call OI" stroke="#f43f5e" strokeWidth={2} fillOpacity={1} fill="url(#colorCall)" />
            <Area type="monotone" dataKey="peOiValue" name="Put OI" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorPut)" />

            {crossovers.map((c, i) => (
              <ReferenceLine
                key={i}
                x={c.timeNum}
                stroke={c.crossover === 'BULLISH_CROSSOVER' ? '#10b981' : '#f43f5e'}
                strokeDasharray="3 3"
                label={{
                  position: 'top',
                  value: c.crossover === 'BULLISH_CROSSOVER' ? 'BULLISH CROSSOVER' : 'BEARISH CROSSOVER',
                  fill: c.crossover === 'BULLISH_CROSSOVER' ? '#10b981' : '#f43f5e',
                  fontSize: 10,
                  fontWeight: 'bold'
                }}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Filter Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatusCard
          title="TIME FILTER"
          icon={<Clock size={16} />}
          status={latestData?.time_filter_status === 'VALID' ? 'VALID' : 'BLOCKED'}
          statusText={latestData?.time_filter_status === 'VALID' ? '✓ VALID' : 'BLOCKED'}
          subText={latestData?.time_filter_status === 'VALID' ? 'Before 2:30 PM' : 'Post 2:30 PM'}
        />

        <StatusCard
          title="DISTANCE FILTER"
          icon={<Navigation size={16} />}
          status={latestData?.distance_filter_status === 'VALID' ? 'VALID' : 'BLOCKED'}
          statusText={latestData?.distance_filter_status === 'VALID' ? '✓ VALID' : 'BLOCKED'}
          subText={latestData ? `${latestData.vwap_supertrend_distance?.toFixed(1) || 0} pts / 40 pts max` : '--'}
        />

        <StatusCard
          title="LAST CROSSOVER"
          icon={<AlertTriangle size={16} />}
          status={latestData?.crossover !== 'NO_CROSSOVER' && latestData?.crossover ? 'VALID' : 'NEUTRAL'}
          statusText={latestData?.crossover !== 'NO_CROSSOVER' && latestData?.crossover ? latestData.crossover.replace('_CROSSOVER', '') : 'NONE'}
          subText={latestData?.crossover_timestamp || '--'}
        />
      </div>

    </div>
  );
};

export default TrendingOiCrossover;
