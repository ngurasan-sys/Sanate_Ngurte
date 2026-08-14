import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders default style for unknown status', () => {
    render(<StatusBadge status="UNKNOWN_STATUS" />);
    const badge = screen.getByText('UNKNOWN_STATUS');
    expect(badge.className).toContain('bg-zinc-800');
    expect(badge.className).toContain('text-zinc-300');
    expect(badge.className).toContain('border-zinc-700');
  });

  const bullishStatuses = [
    'BULLISH', 'BUY', 'SAFE', 'ACTIVE', 'COMPLETED', 'PASSED', 'LONG', 'CONNECTED',
    'very bullish', 'buy now'
  ];

  bullishStatuses.forEach((status) => {
    it(`renders bullish style for status containing "${status}"`, () => {
      const { container } = render(<StatusBadge status={status} />);
      const span = container.firstChild as HTMLElement;
      expect(span.className).toContain('bg-emerald-500/10');
      expect(span.className).toContain('text-emerald-400');
      expect(span.className).toContain('border-emerald-500/20');
    });
  });

  const bearishStatuses = [
    'BEARISH', 'SELL', 'WARNING', 'LOSS', 'SHORT', 'REJECTED', 'FAILED',
    'big warning', 'sell all'
  ];

  bearishStatuses.forEach((status) => {
    it(`renders bearish style for status containing "${status}"`, () => {
      const { container } = render(<StatusBadge status={status} />);
      const span = container.firstChild as HTMLElement;
      expect(span.className).toContain('bg-rose-500/10');
      expect(span.className).toContain('text-rose-400');
      expect(span.className).toContain('border-rose-500/20');
    });
  });

  const blockedStatuses = [
    'BLOCKED', 'account blocked'
  ];

  blockedStatuses.forEach((status) => {
    it(`renders blocked style for status containing "${status}"`, () => {
      const { container } = render(<StatusBadge status={status} />);
      const span = container.firstChild as HTMLElement;
      expect(span.className).toContain('bg-amber-500/10');
      expect(span.className).toContain('text-amber-400');
      expect(span.className).toContain('border-amber-500/20');
    });
  });

  // These tests document the current overlapping keyword behavior (Bullish > Bearish > Blocked)
  const overlappingStatuses = [
    { status: 'DISCONNECTED', expectedClass: 'bg-emerald-500/10', reason: 'contains CONNECTED (Bullish)' },
    { status: 'SAFE HALT', expectedClass: 'bg-emerald-500/10', reason: 'contains SAFE (Bullish)' },
    { status: 'INACTIVE', expectedClass: 'bg-emerald-500/10', reason: 'contains ACTIVE (Bullish)' },
  ];

  overlappingStatuses.forEach(({ status, expectedClass, reason }) => {
    it(`renders style based on highest priority match for "${status}" (${reason})`, () => {
      const { container } = render(<StatusBadge status={status} />);
      const span = container.firstChild as HTMLElement;
      expect(span.className).toContain(expectedClass);
    });
  });

  it('applies classes based on priority (bullish > bearish > blocked)', () => {
    // If a status contains both 'BULLISH' and 'BEARISH', 'BULLISH' should win based on code structure
    // Since isBullish is checked first in the if-else chain
    const { container } = render(<StatusBadge status="BULLISH BEARISH BLOCKED" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('bg-emerald-500/10');
  });

  it('applies bearish over blocked if both present and no bullish', () => {
    const { container } = render(<StatusBadge status="BEARISH BLOCKED" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('bg-rose-500/10');
  });
});
