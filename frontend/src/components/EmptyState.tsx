import React from 'react';
import { HelpCircle } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  description?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No active records',
  description = 'Your system or active strategies have not generated matching records today.',
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 border border-zinc-800 rounded-lg bg-zinc-900 select-none">
      <HelpCircle size={28} className="text-zinc-600 mb-2" />
      <h4 className="text-zinc-300 font-sans font-bold text-xs uppercase tracking-wider">{title}</h4>
      <p className="text-xs text-zinc-500 font-sans mt-1 text-center max-w-sm">{description}</p>
    </div>
  );
};

export default EmptyState;
