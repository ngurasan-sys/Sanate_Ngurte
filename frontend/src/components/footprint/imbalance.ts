import type { FootprintCandle, FootprintNode } from '../../stores/useFootprintStore';

export interface AnnotatedNode extends FootprintNode {
  price: number;
  buyImbalance: boolean;
  sellImbalance: boolean;
  stackedZone: 'BUY' | 'SELL' | null;
}

/**
 * Mirrors the backend's check_diagonal_imbalance/check_stacked_imbalance
 * (backend/app/order_flow/analysis.py) exactly, but runs client-side so
 * the Imbalance Ratio Dial is instantly interactive per-viewer — the
 * backend's own imbalance flags reflect whatever ratio the *last* client
 * to POST /api/v1/footprint/imbalance-ratio set globally, which isn't
 * what an individual user dragging their own dial wants.
 *
 * Diagonal imbalance: ask_volume at price level [X] vs bid_volume at
 * price level [X - 1 tick]. ratioPct is a percentage (e.g. 300 = 3x).
 */
export function computeAnnotatedLevels(
  footprint: Record<string, FootprintNode>,
  ratioPct: number,
  stackedMinConsecutive: number = 3,
): AnnotatedNode[] {
  const ratio = ratioPct / 100;
  const sortedPrices = Object.keys(footprint)
    .map(Number)
    .sort((a, b) => a - b);

  const nodes: AnnotatedNode[] = sortedPrices.map((price) => ({
    ...footprint[String(price)],
    price,
    buyImbalance: false,
    sellImbalance: false,
    stackedZone: null,
  }));
  const byPrice = new Map(nodes.map((n) => [n.price, n]));

  for (let i = 0; i < sortedPrices.length - 1; i++) {
    const lower = byPrice.get(sortedPrices[i])!;
    const higher = byPrice.get(sortedPrices[i + 1])!;

    // Buy imbalance: aggressive buying at the higher level dwarfs the
    // resting sell interest one tick below it.
    if (lower.bid_volume > 0 && higher.ask_volume >= ratio * lower.bid_volume) {
      higher.buyImbalance = true;
    }
    // Sell imbalance (mirror image): aggressive selling at the higher
    // level dwarfs the ask interest one tick below it.
    if (lower.ask_volume > 0 && higher.bid_volume >= ratio * lower.ask_volume) {
      higher.sellImbalance = true;
    }
  }

  // Stacked imbalance: min_consecutive-or-more adjacent levels sharing
  // the same imbalance direction get the whole zone flagged.
  let buyStack: AnnotatedNode[] = [];
  let sellStack: AnnotatedNode[] = [];
  const flush = (stack: AnnotatedNode[], zone: 'BUY' | 'SELL') => {
    if (stack.length >= stackedMinConsecutive) {
      stack.forEach((n) => { n.stackedZone = zone; });
    }
  };

  for (const price of sortedPrices) {
    const node = byPrice.get(price)!;
    if (node.buyImbalance) {
      buyStack.push(node);
    } else {
      flush(buyStack, 'BUY');
      buyStack = [];
    }
    if (node.sellImbalance) {
      sellStack.push(node);
    } else {
      flush(sellStack, 'SELL');
      sellStack = [];
    }
  }
  flush(buyStack, 'BUY');
  flush(sellStack, 'SELL');

  // Render top-to-bottom (highest price first) — natural reading order
  // for a footprint column.
  return nodes.slice().reverse();
}

export function computeCandleDelta(candle: Pick<FootprintCandle, 'buy_volume' | 'sell_volume'>): number {
  return candle.buy_volume - candle.sell_volume;
}
