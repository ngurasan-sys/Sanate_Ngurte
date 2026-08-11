import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface ErrorStateProps {
  message?: string;
  timestamp?: string;
  onReconnect?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  message = 'Market data feed unavailable',
  timestamp = '10:32:14',
  onReconnect,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 border border-zinc-800 rounded-lg bg-zinc-900 select-none space-y-4">
      <div className="flex items-center gap-2">
        <AlertTriangle size={18} className="text-rose-400" />
        <h4 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">{message}</h4>
      </div>

      <div className="text-center font-mono text-[10px] text-zinc-500">
        <span>LAST HANDSHAKE ATTEMPT: </span>
        <span className="text-zinc-400">{timestamp}</span>
      </div>

      {onReconnect && (
        <button
          onClick={onReconnect}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-750 text-zinc-200 rounded-lg text-xs font-semibold tracking-wider transition-colors border border-zinc-700"
        >
          RECONNECT FEED
        </button>
      )}
    </div>
  );
};

export default ErrorState;
