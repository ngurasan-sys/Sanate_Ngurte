import { describe, it, expect } from 'vitest';
import {
  inferTickSize, priceRange, makePriceToY, tickSizeInPixels,
  heatmapBlendFactor, heatmapIntensity, HEATMAP_ROW_PX, TEXT_ROW_PX,
} from './scale';
import type { FootprintCandle } from '../../stores/useFootprintStore';

function candle(overrides: Partial<FootprintCandle> = {}): FootprintCandle {
  return {
    instrument_key: 'NIFTY FUT', timeframe: '5m', open_time: '2024-10-01T09:15:00Z',
    open: 100, high: 105, low: 95, close: 102, is_closed: true,
    footprint: {}, buy_volume: 0, sell_volume: 0, delta: 0, poc_price: null,
    ...overrides,
  };
}

describe('inferTickSize', () => {
  it('finds the smallest gap between footprint price keys', () => {
    const c = candle({ footprint: { '100': {} as any, '100.05': {} as any, '100.5': {} as any } });
    expect(inferTickSize([c])).toBeCloseTo(0.05);
  });

  it('falls back to 0.05 when there is not enough data', () => {
    expect(inferTickSize([candle({ footprint: {} })])).toBe(0.05);
  });
});

describe('priceRange', () => {
  it('spans the min low and max high across candles', () => {
    const range = priceRange([candle({ low: 95, high: 105 }), candle({ low: 90, high: 110 })]);
    expect(range).toEqual({ min: 90, max: 110 });
  });

  it('pads a degenerate single-price range so it never divides by zero', () => {
    const range = priceRange([candle({ low: 100, high: 100 })]);
    expect(range.min).toBeLessThan(range.max);
  });

  it('defaults to a sane range for an empty candle list', () => {
    const range = priceRange([]);
    expect(range.min).toBeLessThan(range.max);
  });
});

describe('makePriceToY', () => {
  it('maps the max price to the top and min price to the bottom (padded)', () => {
    const priceToY = makePriceToY(100, 200, 500, 20);
    expect(priceToY(200)).toBeCloseTo(20);
    expect(priceToY(100)).toBeCloseTo(480);
  });

  it('maps the midpoint price to the vertical midpoint', () => {
    const priceToY = makePriceToY(100, 200, 500, 0);
    expect(priceToY(150)).toBeCloseTo(250);
  });
});

describe('tickSizeInPixels', () => {
  it('scales proportionally to the usable canvas height', () => {
    // range=100, usable height=500-2*20=460 -> 1 point = 4.6px, tick 0.05 -> 0.23px
    const px = tickSizeInPixels(0.05, 0, 100, 500, 20);
    expect(px).toBeCloseTo(0.23, 2);
  });
});

describe('heatmapBlendFactor', () => {
  it('is fully heatmap at or below the heatmap threshold', () => {
    expect(heatmapBlendFactor(HEATMAP_ROW_PX)).toBe(1);
    expect(heatmapBlendFactor(2)).toBe(1);
  });

  it('is fully text at or above the text threshold', () => {
    expect(heatmapBlendFactor(TEXT_ROW_PX)).toBe(0);
    expect(heatmapBlendFactor(50)).toBe(0);
  });

  it('blends smoothly in between', () => {
    const mid = (HEATMAP_ROW_PX + TEXT_ROW_PX) / 2;
    expect(heatmapBlendFactor(mid)).toBeCloseTo(0.5, 5);
  });
});

describe('heatmapIntensity', () => {
  it('is 0..1 relative to the loudest level', () => {
    expect(heatmapIntensity(50, 100)).toBe(0.5);
    expect(heatmapIntensity(100, 100)).toBe(1);
    expect(heatmapIntensity(0, 100)).toBe(0);
  });

  it('handles a zero max without dividing by zero', () => {
    expect(heatmapIntensity(0, 0)).toBe(0);
  });

  it('clamps values outside 0..1', () => {
    expect(heatmapIntensity(150, 100)).toBe(1);
  });
});
