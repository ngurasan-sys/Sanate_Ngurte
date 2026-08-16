import React, { useCallback, useEffect, useState } from 'react';
import StatusBadge from '../components/StatusBadge';
import { Link2, ShieldCheck, Info } from 'lucide-react';

interface BrokerField {
  name: string;
  label: string;
  secret: boolean;
}

interface BrokerMeta {
  id: string;
  display_name: string;
  auth_type: 'oauth_redirect' | 'manual_token';
  fields: BrokerField[];
  notes: string;
  connected: boolean;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const BrokerConnectionsView: React.FC = () => {
  const [brokers, setBrokers] = useState<BrokerMeta[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeBrokerId, setActiveBrokerId] = useState<string | null>(null);

  const fetchActiveBroker = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/brokers/active`);
      if (!res.ok) return;
      const data = await res.json();
      setActiveBrokerId(data.broker_id);
    } catch {
      // non-fatal — the connections list still renders without this
    }
  }, []);

  useEffect(() => {
    fetchActiveBroker();
  }, [fetchActiveBroker]);

  const fetchBrokers = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/brokers`);
      if (!res.ok) throw new Error(`Failed to load brokers (${res.status})`);
      const data: BrokerMeta[] = await res.json();
      setBrokers(data);
      if (!selected && data.length > 0) setSelected(data[0].id);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reach backend');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchBrokers();
  }, [fetchBrokers]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== API_BASE && API_BASE.startsWith('http')) return;
      if (event.data?.type === 'BROKER_AUTH_COMPLETE') {
        if (event.data.status === 'CONNECTED') {
          setNotice(`${event.data.broker} connected.`);
          fetchBrokers();
        } else {
          setError(`${event.data.broker} connection failed.`);
        }
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [fetchBrokers]);

  const active = brokers.find((b) => b.id === selected) || null;

  const setField = (name: string, value: string) =>
    setFormValues((prev) => ({ ...prev, [name]: value }));

  const handleSaveOAuthCredentials = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/brokers/${active.id}/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields: formValues }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save credentials');
      setNotice('Credentials saved. Click Connect to complete login.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save credentials');
    } finally {
      setBusy(false);
    }
  };

  const handleConnectOAuth = () => {
    if (!active) return;
    const width = 600;
    const height = 700;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    window.open(
      `${API_BASE}/api/v1/brokers/${active.id}/login`,
      `${active.display_name} Login`,
      `width=${width},height=${height},left=${left},top=${top}`
    );
  };

  const handleSaveDhanToken = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/brokers/dhan/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: formValues.client_id || '',
          access_token: formValues.access_token || '',
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Token rejected by Dhan');
      setNotice('Dhan token verified and saved.');
      fetchBrokers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to verify token');
    } finally {
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    if (!active) return;
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/v1/brokers/${active.id}/credentials`, { method: 'DELETE' });
      setFormValues({});
      setNotice(`${active.display_name} disconnected.`);
      fetchBrokers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to disconnect');
    } finally {
      setBusy(false);
    }
  };

  const handleMakeActive = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/brokers/active`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker_id: active.id }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to activate broker');
      setNotice(`${active.display_name} is now the active broker.`);
      setActiveBrokerId(active.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to activate broker');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 select-none pb-12">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">
          Broker Connections
        </h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">
          Enter your own API credentials per broker and authenticate directly. Whichever broker
          is marked ACTIVE drives live data and order execution for the whole platform — connect
          a broker, then make it active.
        </p>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono px-4 py-3 rounded-lg">
          {error}
        </div>
      )}
      {notice && !error && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono px-4 py-3 rounded-lg">
          {notice}
        </div>
      )}

      <div className="flex gap-2 border-b border-zinc-800 pb-3">
        {brokers.map((b) => (
          <button
            key={b.id}
            onClick={() => {
              setSelected(b.id);
              setFormValues({});
              setError(null);
              setNotice(null);
            }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-colors ${
              selected === b.id
                ? 'bg-zinc-800 text-zinc-100 border border-zinc-700'
                : 'bg-zinc-900 text-zinc-500 border border-zinc-850 hover:text-zinc-300'
            }`}
          >
            <Link2 size={14} className={b.connected ? 'text-emerald-400' : 'text-zinc-600'} />
            {b.display_name}
            <StatusBadge status={b.connected ? 'CONNECTED' : 'DISCONNECTED'} />
            {activeBrokerId === b.id && (
              <span className="text-[9px] font-bold text-amber-400 border border-amber-400/30 rounded px-1.5 py-0.5">
                ACTIVE
              </span>
            )}
          </button>
        ))}
      </div>

      {active && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-sky-400" />
                <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">
                  {active.display_name} Credentials
                </h3>
              </div>
              <StatusBadge status={active.connected ? 'CONNECTED' : 'DISCONNECTED'} />
            </div>

            <div className="flex items-start gap-2 bg-zinc-950/50 border border-zinc-850 rounded-lg p-3">
              <Info size={14} className="text-zinc-500 shrink-0 mt-0.5" />
              <p className="text-[11px] text-zinc-500 leading-relaxed">{active.notes}</p>
            </div>

            <div className="space-y-2">
              {active.fields.map((f) => (
                <div key={f.name}>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">
                    {f.label}
                  </label>
                  <input
                    type={f.secret ? 'password' : 'text'}
                    value={formValues[f.name] || ''}
                    onChange={(e) => setField(f.name, e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono text-xs rounded px-3 py-2 outline-none focus:border-sky-500/50"
                    autoComplete="off"
                  />
                </div>
              ))}
            </div>

            <div className="flex gap-2 pt-2">
              {active.auth_type === 'oauth_redirect' ? (
                <>
                  <button
                    onClick={handleSaveOAuthCredentials}
                    disabled={busy}
                    className="flex-1 py-2 px-3 bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded hover:bg-sky-500/20 disabled:opacity-40 transition-colors text-xs font-bold"
                  >
                    SAVE CREDENTIALS
                  </button>
                  <button
                    onClick={handleConnectOAuth}
                    disabled={busy}
                    className="flex-1 py-2 px-3 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded hover:bg-emerald-500/20 disabled:opacity-40 transition-colors text-xs font-bold"
                  >
                    CONNECT
                  </button>
                </>
              ) : (
                <button
                  onClick={handleSaveDhanToken}
                  disabled={busy}
                  className="flex-1 py-2 px-3 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded hover:bg-emerald-500/20 disabled:opacity-40 transition-colors text-xs font-bold"
                >
                  SAVE & VERIFY
                </button>
              )}
              {active.connected && activeBrokerId !== active.id && (
                <button
                  onClick={handleMakeActive}
                  disabled={busy}
                  className="flex-1 py-2 px-3 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded hover:bg-amber-500/20 disabled:opacity-40 transition-colors text-xs font-bold"
                >
                  MAKE ACTIVE
                </button>
              )}
              {active.connected && (
                <button
                  onClick={handleDisconnect}
                  disabled={busy}
                  className="flex-1 py-2 px-3 bg-rose-500/10 text-rose-400 border border-rose-500/20 rounded hover:bg-rose-500/20 disabled:opacity-40 transition-colors text-xs font-bold"
                >
                  DISCONNECT
                </button>
              )}
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-3">
            <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">
              How This Broker Connects
            </h3>
            {active.auth_type === 'oauth_redirect' ? (
              <ol className="text-xs text-zinc-400 space-y-2 list-decimal list-inside font-mono">
                <li>Save your API key/secret (and redirect URI for Upstox) on the left.</li>
                <li>Click Connect — a popup opens the broker's real login page.</li>
                <li>Log in with your broker credentials; the popup closes itself on success.</li>
                <li>This page updates to CONNECTED once the token is saved.</li>
              </ol>
            ) : (
              <ol className="text-xs text-zinc-400 space-y-2 list-decimal list-inside font-mono">
                <li>Log into web.dhan.co and open "Access DhanHQ APIs".</li>
                <li>Generate an access token (valid 24 hours).</li>
                <li>Paste your Client ID and the token on the left, then Save & Verify.</li>
                <li>The token is checked against Dhan's API before being stored.</li>
              </ol>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default BrokerConnectionsView;
