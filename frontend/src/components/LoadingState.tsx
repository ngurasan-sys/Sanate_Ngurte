import React, { memo } from 'react';

/**
 * ⚡ Bolt Optimization: Wrapped in React.memo()
 * Impact: Prevents unnecessary re-renders of this pure stateless leaf component.
 */
export const LoadingState: React.FC = memo(() => {
  return (
    <div className="flex flex-col items-center justify-center p-12 space-y-4 select-none">
      <div className="flex items-center gap-1.5 font-mono text-zinc-500 text-xs">
        <span>LOADING TICK ENGINE...</span>
        <span className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce delay-100" />
        <span className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce delay-200" />
        <span className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce delay-300" />
      </div>

      <div className="w-full max-w-sm space-y-2">
        <div className="h-4 bg-zinc-900 border border-zinc-850 rounded animate-pulse" />
        <div className="h-3 bg-zinc-900/60 border border-zinc-850/60 rounded animate-pulse w-3/4" />
      </div>
    </div>
  );
});

export default LoadingState;
