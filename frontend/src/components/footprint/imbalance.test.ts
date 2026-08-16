import { describe, it, expect } from 'vitest';
import { computeAnnotatedLevels, computeCandleDelta } from './imbalance';
import type { FootprintNode } from '../../stores/useFootprintStore';

function node(bid: number, ask: number): FootprintNode {
  return { price: 0, bid_volume: bid, ask_volume: ask, delta: ask - bid, total_volume: bid + ask };
}

describe('computeAnnotatedLevels', () => {
  it('flags a buy imbalance when ask volume dwarfs the bid volume one tick below', () => {
    const footprint = {
      '100': node(10, 0),
      '101': node(0, 40), // 40 >= 3x * 10
    };
    const levels = computeAnnotatedLevels(footprint, 300);
    const at101 = levels.find((l) => l.price === 101)!;
    expect(at101.buyImbalance).toBe(true);
  });

  it('does not flag when the ratio is not met', () => {
    const footprint = {
      '100': node(10, 0),
      '101': node(0, 20), // 20 < 3x * 10
    };
    const levels = computeAnnotatedLevels(footprint, 300);
    const at101 = levels.find((l) => l.price === 101)!;
    expect(at101.buyImbalance).toBe(false);
  });

  it('flags a sell imbalance mirroring the buy check', () => {
    const footprint = {
      '100': node(0, 10),
      '101': node(40, 0), // bid(101)=40 >= 3x * ask(100)=10
    };
    const levels = computeAnnotatedLevels(footprint, 300);
    const at101 = levels.find((l) => l.price === 101)!;
    expect(at101.sellImbalance).toBe(true);
  });

  it('raising the ratio can suppress a previously-flagged imbalance', () => {
    const footprint = { '100': node(10, 0), '101': node(0, 25) };
    expect(computeAnnotatedLevels(footprint, 200).find((l) => l.price === 101)!.buyImbalance).toBe(true);
    expect(computeAnnotatedLevels(footprint, 500).find((l) => l.price === 101)!.buyImbalance).toBe(false);
  });

  it('marks a stacked zone across 3+ consecutive buy-imbalanced levels', () => {
    const footprint = {
      '100': node(10, 0),
      '101': node(10, 40),
      '102': node(10, 40),
      '103': node(0, 40),
    };
    const levels = computeAnnotatedLevels(footprint, 300, 3);
    expect(levels.find((l) => l.price === 101)!.stackedZone).toBe('BUY');
    expect(levels.find((l) => l.price === 102)!.stackedZone).toBe('BUY');
    expect(levels.find((l) => l.price === 103)!.stackedZone).toBe('BUY');
    expect(levels.find((l) => l.price === 100)!.stackedZone).toBe(null);
  });

  it('does not mark a stack shorter than the minimum consecutive length', () => {
    const footprint = {
      '100': node(10, 0),
      '101': node(0, 40),
      '102': node(0, 0),
    };
    const levels = computeAnnotatedLevels(footprint, 300, 3);
    expect(levels.find((l) => l.price === 101)!.stackedZone).toBe(null);
  });

  it('returns levels sorted highest price first (top-to-bottom reading order)', () => {
    const footprint = { '100': node(1, 1), '102': node(1, 1), '101': node(1, 1) };
    const levels = computeAnnotatedLevels(footprint, 300);
    expect(levels.map((l) => l.price)).toEqual([102, 101, 100]);
  });

  it('handles an empty footprint without error', () => {
    expect(computeAnnotatedLevels({}, 300)).toEqual([]);
  });
});

describe('computeCandleDelta', () => {
  it('is buy volume minus sell volume', () => {
    expect(computeCandleDelta({ buy_volume: 100, sell_volume: 40 })).toBe(60);
    expect(computeCandleDelta({ buy_volume: 40, sell_volume: 100 })).toBe(-60);
  });
});
