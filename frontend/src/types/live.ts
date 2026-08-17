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

export interface LiveOrder {
  id: string;
  timestamp: string;
  instrument: string;
  action: string;
  status: string;
}

export interface LiveLevel {
  levelId: string;
  price: number;
  levelType: 'Support' | 'Resistance';
  timeframe: string;
  strength: number;
  touchCount: number;
}
