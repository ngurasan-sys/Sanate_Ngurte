import type { FootprintCandle } from '../../stores/useFootprintStore';

/** Smallest positive gap between any two footprint price keys across the
 * visible candles — used as the chart's tick size. Falls back to 0.05
 * (the mock feed's tick size) when there isn't enough data to infer it.
 */
export function inferTickSize(candles: FootprintCandle[]): number {
  const prices = new Set<number>();
  for (const c of candles) {
    for (const key of Object.keys(c.footprint)) prices.add(Number(key));
  }
  const sorted = Array.from(prices).sort((a, b) => a - b);
  let minGap = Infinity;
  for (let i = 1; i < sorted.length; i++) {
    const gap = sorted[i] - sorted[i - 1];
    if (gap > 1e-9 && gap < minGap) minGap = gap;
  }
  return Number.isFinite(minGap) ? minGap : 0.05;
}

export function priceRange(candles: FootprintCandle[]): { min: number; max: number } {
  if (candles.length === 0) return { min: 0, max: 1 };
  let min = Infinity;
  let max = -Infinity;
  for (const c of candles) {
    if (c.low < min) min = c.low;
    if (c.high > max) max = c.high;
  }
  if (min === max) {
    // Degenerate single-price range — pad so priceToY doesn't divide by 0.
    min -= 1;
    max += 1;
  }
  return { min, max };
}

/** price -> y pixel, linear, price increasing upward (canvas y increases downward). */
export function makePriceToY(min: number, max: number, canvasHeight: number, paddingPx: number = 20) {
  const usable = canvasHeight - paddingPx * 2;
  return (price: number) => paddingPx + usable - ((price - min) / (max - min)) * usable;
}

export function tickSizeInPixels(tickSize: number, min: number, max: number, canvasHeight: number, paddingPx: number = 20): number {
  const usable = canvasHeight - paddingPx * 2;
  return (tickSize / (max - min)) * usable;
}

/** Below this row height, individual bid/ask numbers stop being legible
 * and the chart should fall back to a heatmap fill. Above it, plain text.
 * Between the two, blend (0..1) drives a smooth opacity crossfade rather
 * than a hard cut.
 */
export const HEATMAP_ROW_PX = 8;
export const TEXT_ROW_PX = 18;

export function heatmapBlendFactor(rowHeightPx: number): number {
  if (rowHeightPx <= HEATMAP_ROW_PX) return 1;
  if (rowHeightPx >= TEXT_ROW_PX) return 0;
  return 1 - (rowHeightPx - HEATMAP_ROW_PX) / (TEXT_ROW_PX - HEATMAP_ROW_PX);
}

/** 0..1 volume intensity relative to the loudest price level in the candle. */
export function heatmapIntensity(totalVolume: number, maxTotalVolumeInCandle: number): number {
  if (maxTotalVolumeInCandle <= 0) return 0;
  return Math.max(0, Math.min(1, totalVolume / maxTotalVolumeInCandle));
}
