import React from 'react';
import { useEffect } from 'react';
import { useSystemStore } from '../stores/systemStore';
import StatusBadge from './StatusBadge';
import { Link2, ShieldCheck, Lock } from 'lucide-react';

export const BrokeragePanel: React.FC = () => {
  const { brokerageStatus, connectBroker, disconnectBroker } = useSystemStore();


  const handleToggle = () => {
    if (brokerageStatus.isConnected) {
      disconnectBroker();
    } else {
      // Open Upstox OAuth login in a new tab/window
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;

      window.open(
        (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api/v1/broker/upstox/login',
        'Upstox Login',
        `width=${width},height=${height},left=${left},top=${top}`
      );
    }
  };

    useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Securely check origin
      const expectedOrigin = import.meta.env.VITE_API_URL || 'http://localhost:8000';

      // Strict origin matching
      if (event.origin !== expectedOrigin && expectedOrigin.startsWith('http')) {
        console.warn('Broker Auth: Received message from unauthorized origin:', event.origin);
        return;
      }

      if (event.data?.type === 'BROKER_AUTH_COMPLETE' && event.data?.broker === 'UPSTOX') {
        if (event.data.status === 'CONNECTED') {
          connectBroker();
        }
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [connectBroker]);


  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Brokerage Authentication & Settings
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Secure sandbox environment connection control and auth handshake</p>
        </div>

        <button
          onClick={handleToggle}
          className={`px-4 py-2 text-xs font-semibold tracking-wider rounded-lg border transition-all ${
            brokerageStatus.isConnected
              ? 'bg-rose-500/10 border-rose-500/20 text-rose-400 hover:bg-rose-500/20'
              : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20'
          }`}
        >
          {brokerageStatus.isConnected ? 'DISCONNECT' : 'CONNECT'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Connection status card */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4 select-none">
          <div className="flex items-center gap-3">
            <Link2 className={brokerageStatus.isConnected ? 'text-emerald-400' : 'text-zinc-500'} size={20} />
            <h4 className="text-zinc-200 font-sans font-bold text-sm uppercase tracking-wider">Handshake Matrix</h4>
          </div>

          <div className="space-y-3 font-mono text-xs">
            <div className="flex justify-between border-b border-zinc-850 pb-2">
              <span className="text-zinc-500 uppercase">Broker Name</span>
              <span className="text-zinc-200">{brokerageStatus.brokerName}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-2">
              <span className="text-zinc-500 uppercase">Handshake Status</span>
              <StatusBadge status={brokerageStatus.isConnected ? 'CONNECTED' : 'DISCONNECTED'} />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-2">
              <span className="text-zinc-500 uppercase">WS Endpoint</span>
              <StatusBadge status={brokerageStatus.wsStatus} />
            </div>
            <div className="flex justify-between pb-1">
              <span className="text-zinc-500 uppercase">WebSocket Ping Latency</span>
              <span className="text-zinc-200">{brokerageStatus.isConnected ? `${brokerageStatus.wsLatency}ms` : 'OFFLINE'}</span>
            </div>
          </div>
        </div>

        {/* Account information card */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4 select-none">
          <div className="flex items-center gap-3">
            <ShieldCheck className="text-sky-400" size={20} />
            <h4 className="text-zinc-200 font-sans font-bold text-sm uppercase tracking-wider">Account Credentials</h4>
          </div>

          <div className="space-y-3 font-mono text-xs">
            <div className="flex justify-between border-b border-zinc-850 pb-2">
              <span className="text-zinc-500 uppercase">Client ID</span>
              <span className="text-zinc-200">{brokerageStatus.account.clientId}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-2">
              <span className="text-zinc-500 uppercase">Owner Name</span>
              <span className="text-zinc-200">{brokerageStatus.account.name}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-2">
              <span className="text-zinc-500 uppercase">Handshake Auth</span>
              <StatusBadge status={brokerageStatus.account.authStatus} />
            </div>
            <div className="flex justify-between pb-1">
              <span className="text-zinc-500 uppercase">Routing Engine Mode</span>
              <StatusBadge status={brokerageStatus.tradingStatus} />
            </div>
          </div>
        </div>

        {/* Secure Secret Safeguard declaration */}
        <div className="md:col-span-2 bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex items-start gap-4 select-none">
          <div className="p-2 bg-sky-500/10 text-sky-400 rounded-lg border border-sky-500/20 shrink-0">
            <Lock size={18} />
          </div>
          <div className="space-y-1">
            <h5 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">Privacy & Security Safeguards</h5>
            <p className="text-xs text-zinc-500 leading-relaxed font-sans max-w-2xl">
              This terminal strict cryptographic sandbox design ensures secrets, auth codes, client credentials, access tokens and secret parameters are never logged, stored or compiled inside frontend static assets.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BrokeragePanel;
