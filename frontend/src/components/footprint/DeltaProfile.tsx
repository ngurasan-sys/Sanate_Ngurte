import React from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, ReferenceLine } from 'recharts';
import type { FootprintCandle } from '../../stores/useFootprintStore';

interface DeltaProfileProps {
  candles: FootprintCandle[];
}

export const DeltaProfile: React.FC<DeltaProfileProps> = ({ candles }) => {
  const data = candles.map((c) => ({
    time: new Date(c.open_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
    delta: c.delta,
  }));

  return (
    <div className="h-32 w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
          <XAxis dataKey="time" stroke="#52525b" fontSize={9} tickMargin={6} minTickGap={30} />
          <YAxis stroke="#52525b" fontSize={9} width={40} />
          <ReferenceLine y={0} stroke="#3f3f46" />
          <Tooltip
            contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px' }}
            itemStyle={{ fontSize: '11px' }}
            labelStyle={{ color: '#a1a1aa', fontSize: '11px' }}
            formatter={(value: any) => [String(value), 'Delta']}
          />
          <Bar dataKey="delta" radius={[2, 2, 0, 0]}>
            {data.map((d, idx) => (
              <Cell key={idx} fill={d.delta >= 0 ? '#10b981' : '#f43f5e'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default DeltaProfile;
