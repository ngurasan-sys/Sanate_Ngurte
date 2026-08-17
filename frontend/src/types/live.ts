export interface LivePosition {
  id: string;
  source: 'MANUAL' | 'CAS';
  instrument: string; // e.g. "NIFTY 25000 CE"
  strike: number;
  optionType: 'CE' | 'PE';
  quantity: number;
  entryPrice: number;
  status: 'PENDING' | 'OPEN' | 'CLOSED';
  createdAt: string;
  closedAt: string | null;
  exitReason: string | null;
}
