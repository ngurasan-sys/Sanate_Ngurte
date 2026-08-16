import React, { useEffect, useRef } from 'react';
import type { FootprintCandle } from '../../stores/useFootprintStore';
import { computeAnnotatedLevels } from './imbalance';
import {
  inferTickSize, priceRange, makePriceToY, tickSizeInPixels,
  heatmapBlendFactor, heatmapIntensity,
} from './scale';

interface FootprintChartProps {
  candles: FootprintCandle[]; // oldest -> newest, current candle last
  imbalanceRatioPct: number;
}

const COLORS = {
  background: '#0a0f1c',
  grid: '#1e293b',
  axisText: '#64748b',
  bullBorder: '#10b981',
  bearBorder: '#f43f5e',
  bidText: '#94a3b8',
  askText: '#cbd5e1',
  buyImbalanceBg: 'rgba(16, 185, 129, 0.55)',
  sellImbalanceBg: 'rgba(244, 63, 94, 0.55)',
  stackedBuyZone: 'rgba(16, 185, 129, 0.12)',
  stackedSellZone: 'rgba(244, 63, 94, 0.12)',
  poc: 'rgba(250, 204, 21, 0.35)',
};

const PADDING_TOP_BOTTOM = 24;
const CANDLE_GAP = 6;
const LEFT_AXIS_WIDTH = 56;

export const FootprintChart: React.FC<FootprintChartProps> = ({ candles, imbalanceRatioPct }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const width = container.clientWidth;
      const height = container.clientHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = COLORS.background;
      ctx.fillRect(0, 0, width, height);

      if (candles.length === 0) {
        ctx.fillStyle = COLORS.axisText;
        ctx.font = '13px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('Awaiting footprint data...', width / 2, height / 2);
        return;
      }

      const { min, max } = priceRange(candles);
      const priceToY = makePriceToY(min, max, height, PADDING_TOP_BOTTOM);
      const tickSize = inferTickSize(candles);
      const rowPx = tickSizeInPixels(tickSize, min, max, height, PADDING_TOP_BOTTOM);

      // --- Price axis gridlines ---
      ctx.strokeStyle = COLORS.grid;
      ctx.fillStyle = COLORS.axisText;
      ctx.font = '10px monospace';
      ctx.textAlign = 'left';
      const gridLines = 6;
      for (let i = 0; i <= gridLines; i++) {
        const price = min + ((max - min) / gridLines) * i;
        const y = priceToY(price);
        ctx.beginPath();
        ctx.moveTo(LEFT_AXIS_WIDTH, y);
        ctx.lineTo(width, y);
        ctx.globalAlpha = 0.4;
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.fillText(price.toFixed(2), 4, y + 3);
      }

      // --- Candle columns ---
      const plotWidth = width - LEFT_AXIS_WIDTH;
      const colWidth = plotWidth / candles.length;

      candles.forEach((candle, idx) => {
        const colX = LEFT_AXIS_WIDTH + idx * colWidth;
        const colInnerWidth = colWidth - CANDLE_GAP;
        const yHigh = priceToY(candle.high);
        const yLow = priceToY(candle.low);

        const levels = computeAnnotatedLevels(candle.footprint, imbalanceRatioPct);
        const maxTotalVolume = levels.reduce((m, l) => Math.max(m, l.total_volume), 0);

        // Candle direction border
        ctx.strokeStyle = candle.close >= candle.open ? COLORS.bullBorder : COLORS.bearBorder;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(colX, yHigh, colInnerWidth, yLow - yHigh);

        // POC highlight row
        if (candle.poc_price !== null) {
          const pocY = priceToY(candle.poc_price);
          ctx.fillStyle = COLORS.poc;
          ctx.fillRect(colX, pocY - rowPx / 2, colInnerWidth, Math.max(rowPx, 1));
        }

        const blend = heatmapBlendFactor(rowPx);
        const midX = colX + colInnerWidth / 2;

        levels.forEach((level) => {
          const y = priceToY(level.price);
          const rowTop = y - rowPx / 2;

          if (level.stackedZone === 'BUY') {
            ctx.fillStyle = COLORS.stackedBuyZone;
            ctx.fillRect(colX, rowTop, colInnerWidth, rowPx);
          } else if (level.stackedZone === 'SELL') {
            ctx.fillStyle = COLORS.stackedSellZone;
            ctx.fillRect(colX, rowTop, colInnerWidth, rowPx);
          }

          // Heatmap fill (blended in as rows get too small for text)
          if (blend > 0) {
            const intensity = heatmapIntensity(level.total_volume, maxTotalVolume);
            const heatColor = level.delta >= 0
              ? `rgba(16, 185, 129, ${(intensity * 0.6 * blend).toFixed(3)})`
              : `rgba(244, 63, 94, ${(intensity * 0.6 * blend).toFixed(3)})`;
            ctx.fillStyle = heatColor;
            ctx.fillRect(colX, rowTop, colInnerWidth, rowPx);
          }

          // Text (fades out as blend -> 1)
          const textAlpha = 1 - blend;
          if (textAlpha > 0.05 && colInnerWidth > 30) {
            ctx.globalAlpha = textAlpha;
            ctx.font = '9px monospace';

            // Bid volume (left half) — highlighted background if flagged
            if (level.sellImbalance) {
              ctx.fillStyle = COLORS.sellImbalanceBg;
              ctx.fillRect(colX, rowTop, colInnerWidth / 2, rowPx);
            }
            ctx.fillStyle = level.sellImbalance ? '#ffffff' : COLORS.bidText;
            ctx.textAlign = 'right';
            ctx.fillText(String(level.bid_volume), midX - 3, y + 3);

            // Ask volume (right half)
            if (level.buyImbalance) {
              ctx.fillStyle = COLORS.buyImbalanceBg;
              ctx.fillRect(midX, rowTop, colInnerWidth / 2, rowPx);
            }
            ctx.fillStyle = level.buyImbalance ? '#ffffff' : COLORS.askText;
            ctx.textAlign = 'left';
            ctx.fillText(String(level.ask_volume), midX + 3, y + 3);

            ctx.globalAlpha = 1;
          }
        });

        // Center divider line
        ctx.strokeStyle = COLORS.grid;
        ctx.globalAlpha = 0.6;
        ctx.beginPath();
        ctx.moveTo(midX, yHigh);
        ctx.lineTo(midX, yLow);
        ctx.stroke();
        ctx.globalAlpha = 1;
      });
    };

    draw();

    const resizeObserver = new ResizeObserver(draw);
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [candles, imbalanceRatioPct]);

  return (
    <div ref={containerRef} className="w-full h-full">
      <canvas ref={canvasRef} />
    </div>
  );
};

export default FootprintChart;
