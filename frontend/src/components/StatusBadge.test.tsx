import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders the status text', () => {
    render(<StatusBadge status="Loading" />);
    expect(screen.getByText('Loading')).toBeInTheDocument();
  });

  const checkClasses = (status: string, expectedClasses: string[]) => {
    render(<StatusBadge status={status} />);
    const badge = screen.getByText(status);
    expectedClasses.forEach((cls) => {
      expect(badge).toHaveClass(cls);
    });
  };

  describe('Bullish statuses', () => {
    const bullishStatuses = [
      'bullish', 'buy', 'safe', 'active', 'completed', 'passed', 'long', 'connected'
    ];
    const expectedClasses = ['bg-emerald-500/10', 'text-emerald-400', 'border-emerald-500/20'];

    bullishStatuses.forEach((status) => {
      it(`applies bullish classes for "${status}"`, () => {
        checkClasses(status, expectedClasses);
      });

      it(`applies bullish classes for uppercase "${status.toUpperCase()}"`, () => {
        checkClasses(status.toUpperCase(), expectedClasses);
      });
    });
  });

  describe('Bearish statuses', () => {
    const bearishStatuses = [
      'bearish', 'sell', 'warning', 'loss', 'short', 'rejected', 'failed', 'disconnected'
    ];
    const expectedClasses = ['bg-rose-500/10', 'text-rose-400', 'border-rose-500/20'];

    bearishStatuses.forEach((status) => {
      it(`applies bearish classes for "${status}"`, () => {
        checkClasses(status, expectedClasses);
      });

      it(`applies bearish classes for uppercase "${status.toUpperCase()}"`, () => {
        checkClasses(status.toUpperCase(), expectedClasses);
      });
    });
  });

  describe('Blocked statuses', () => {
    const blockedStatuses = ['blocked', 'safe halt', 'inactive'];
    const expectedClasses = ['bg-amber-500/10', 'text-amber-400', 'border-amber-500/20'];

    blockedStatuses.forEach((status) => {
      it(`applies blocked classes for "${status}"`, () => {
        checkClasses(status, expectedClasses);
      });

      it(`applies blocked classes for uppercase "${status.toUpperCase()}"`, () => {
        checkClasses(status.toUpperCase(), expectedClasses);
      });
    });
  });

  describe('Default statuses', () => {
    const defaultStatuses = ['unknown', 'pending', 'loading'];
    const expectedClasses = ['bg-zinc-800', 'text-zinc-300', 'border-zinc-700'];

    defaultStatuses.forEach((status) => {
      it(`applies default classes for "${status}"`, () => {
        checkClasses(status, expectedClasses);
      });

      it(`applies default classes for uppercase "${status.toUpperCase()}"`, () => {
        checkClasses(status.toUpperCase(), expectedClasses);
      });
    });
  });
});
