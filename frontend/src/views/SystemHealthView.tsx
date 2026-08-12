import React from 'react';
import { Wifi, BarChart2, ShieldAlert } from 'lucide-react';

const SystemHealthView: React.FC = () => {
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
};

export default SystemHealthView;
