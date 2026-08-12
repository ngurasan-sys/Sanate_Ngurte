import React from 'react';
import { render, screen } from '@testing-library/react';
import { MetricCard } from './MetricCard';

describe('MetricCard', () => {
  it('renders label and value', () => {
    render(<MetricCard label="Total Profit" value="$10,000" />);

    expect(screen.getByText('Total Profit')).toBeInTheDocument();
    expect(screen.getByText('$10,000')).toBeInTheDocument();
  });

  it('renders subValue with default neutral color when subValueColor is not provided', () => {
    render(<MetricCard label="Volume" value="500" subValue="Neutral" />);

    const subValueElement = screen.getByText('Neutral');
    expect(subValueElement).toBeInTheDocument();
    expect(subValueElement).toHaveClass('text-zinc-400');
  });

  it('renders subValue with bullish color', () => {
    render(<MetricCard label="Volume" value="500" subValue="+5%" subValueColor="bullish" />);

    const subValueElement = screen.getByText('+5%');
    expect(subValueElement).toBeInTheDocument();
    expect(subValueElement).toHaveClass('text-emerald-400');
  });

  it('renders subValue with bearish color', () => {
    render(<MetricCard label="Volume" value="500" subValue="-5%" subValueColor="bearish" />);

    const subValueElement = screen.getByText('-5%');
    expect(subValueElement).toBeInTheDocument();
    expect(subValueElement).toHaveClass('text-rose-400');
  });

  it('renders subValue with muted color', () => {
    render(<MetricCard label="Volume" value="500" subValue="Unchanged" subValueColor="muted" />);

    const subValueElement = screen.getByText('Unchanged');
    expect(subValueElement).toBeInTheDocument();
    expect(subValueElement).toHaveClass('text-zinc-500');
  });

  it('does not render subValue when it is not provided', () => {
    const { container } = render(<MetricCard label="Volume" value="500" />);

    // It should not render the subValue span element
    const spans = container.querySelectorAll('span');
    expect(spans).toHaveLength(2); // One for label, one for value
  });
});
