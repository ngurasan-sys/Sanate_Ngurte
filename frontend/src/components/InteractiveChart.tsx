import React, { useEffect, useRef, useState } from 'react';
import { createChart, CrosshairMode, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, LineWidth, Time } from 'lightweight-charts';
import { MousePointer2, Minus, Square, Divide, Trash2, Settings2, Activity, BarChart2 } from 'lucide-react';
import useChartWebSocket from '../hooks/useChartWebSocket';

interface InteractiveChartProps {
  symbol?: string;
}

export type DrawingTool = 'cursor' | 'trendline' | 'horizontal' | 'rectangle' | 'fibonacci';

interface DrawingInfo {
  type: DrawingTool;
  startX?: number;
  startY?: number;
  endX?: number;
  endY?: number;
  price?: number;
  color?: string;
  id: string;
}

const InteractiveChart: React.FC<InteractiveChartProps> = ({ symbol = 'NIFTY' }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const oiLineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const oiHistogramSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const smartTrendSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  const [timeframe, setTimeframe] = useState('1m');
  const [activeTool, setActiveTool] = useState<DrawingTool>('cursor');
  const [drawings, setDrawings] = useState<DrawingInfo[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [currentDrawing, setCurrentDrawing] = useState<Partial<DrawingInfo> | null>(null);
  const [historyData, setHistoryData] = useState<any[]>([]);

  // Toggles
  const [showSmartTrend, setShowSmartTrend] = useState(true);
  const [showHFTFlow, setShowHFTFlow] = useState(false);
  const [showOIPane, setShowOIPane] = useState(true);

  // Load history data
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await fetch(`http://127.0.0.1:8000/api/v1/chart/history?symbol=${symbol}&timeframe=${timeframe}`);
        const data = await response.json();

        const formattedCandles = data.map((d: any) => ({
          time: d.time as Time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close
        }));

        const formattedVolume = data.map((d: any) => ({
          time: d.time as Time,
          value: d.volume,
          color: d.close > d.open ? 'rgba(8, 153, 129, 0.5)' : 'rgba(242, 54, 69, 0.5)'
        }));

        const formattedOI = data.map((d: any) => ({
          time: d.time as Time,
          value: d.oi
        }));

        setHistoryData(formattedCandles);

        if (candlestickSeriesRef.current) candlestickSeriesRef.current.setData(formattedCandles);
        if (volumeSeriesRef.current) volumeSeriesRef.current.setData(formattedVolume);
        if (oiLineSeriesRef.current) oiLineSeriesRef.current.setData(formattedOI);
        if (oiHistogramSeriesRef.current) {
            // Calculate mock OI change
            const oiChange = data.map((d: any, i: number) => {
                if (i === 0) return { time: d.time as Time, value: 0, color: 'rgba(8, 153, 129, 0.5)' };
                const diff = d.oi - data[i-1].oi;
                return {
                    time: d.time as Time,
                    value: diff,
                    color: diff >= 0 ? 'rgba(8, 153, 129, 0.5)' : 'rgba(242, 54, 69, 0.5)'
                };
            });
            oiHistogramSeriesRef.current.setData(oiChange);
        }

        if (smartTrendSeriesRef.current) {
            const stData = data.map((d: any) => ({
                time: d.time as Time,
                value: d.low - 10
            }));
            smartTrendSeriesRef.current.setData(stData);
        }

      } catch (err) {
        console.error("Failed to fetch historical chart data", err);
      }
    };
    fetchHistory();
  }, [symbol, timeframe]);

  // Hook for websocket
  const { isConnected, latestCandle, latestVolume, latestOI } = useChartWebSocket(symbol, timeframe, historyData);

  useEffect(() => {
    if (latestCandle && candlestickSeriesRef.current) {
        candlestickSeriesRef.current.update(latestCandle);
    }
    if (latestVolume && volumeSeriesRef.current) {
        volumeSeriesRef.current.update({
            time: latestCandle?.time as Time,
            value: latestVolume,
            color: latestCandle && latestCandle.close > latestCandle.open ? 'rgba(8, 153, 129, 0.5)' : 'rgba(242, 54, 69, 0.5)'
        });
    }
    if (latestOI && oiLineSeriesRef.current) {
        oiLineSeriesRef.current.update({ time: latestCandle?.time as Time, value: latestOI });
    }
  }, [latestCandle, latestVolume, latestOI]);


  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#131722' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#2B2B43' },
        horzLines: { color: '#2B2B43' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: '#2B2B43',
      },
      timeScale: {
        borderColor: '#2B2B43',
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartContainerRef.current.clientWidth,
      height: 500, // Fixed height or resize observer
    });

    chartRef.current = chart;

    candlestickSeriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: '#089981',
      downColor: '#f23645',
      borderVisible: false,
      wickUpColor: '#089981',
      wickDownColor: '#f23645',
    });

    volumeSeriesRef.current = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '',
    });
    volumeSeriesRef.current?.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    if (showSmartTrend) {
        smartTrendSeriesRef.current = chart.addSeries(LineSeries, {
            color: '#f59e0b',
            lineWidth: 2 as LineWidth,
            lineStyle: 2,
        });
    }

    if (showOIPane) {
        // Add separate OI scale
        oiLineSeriesRef.current = chart.addSeries(LineSeries, {
            color: '#8b5cf6',
            lineWidth: 2 as LineWidth,
            priceScaleId: 'oi_scale',
        });

        oiHistogramSeriesRef.current = chart.addSeries(HistogramSeries, {
            priceScaleId: 'oi_scale',
        });

        chart.priceScale('oi_scale').applyOptions({
            scaleMargins: {
                top: 0.7,
                bottom: 0,
            },
        });
    }

    // Set background color for HFT Flow
    if (showHFTFlow) {
        chart.applyOptions({
            layout: {
                background: { color: 'rgba(8, 153, 129, 0.1)' } // Bullish tint
            }
        });
    }

    const resizeObserver = new ResizeObserver((entries) => {
      const newWidth = entries[0].contentRect.width;
      const newHeight = entries[0].contentRect.height;
      chart.applyOptions({ width: newWidth, height: newHeight });

      // Update canvas size
      if (canvasRef.current) {
          canvasRef.current.width = newWidth;
          canvasRef.current.height = newHeight;
          redrawCanvas();
      }
    });

    resizeObserver.observe(chartContainerRef.current);

    // Synchronize drawings on chart events
    chart.timeScale().subscribeVisibleTimeRangeChange(() => {
        redrawCanvas();
    });

    const handleCrosshairMove = (param: any) => {
        if (!param.point) return;

        if (isDrawing && activeTool !== 'cursor' && currentDrawing) {
            setCurrentDrawing({
                ...currentDrawing,
                endX: param.point.x,
                endY: param.point.y
            });
            redrawCanvas(param.point.x, param.point.y);
        }
    };

    chart.subscribeCrosshairMove(handleCrosshairMove);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSmartTrend, showOIPane, showHFTFlow]);

  const handleChartClick = (e: React.MouseEvent<HTMLDivElement>) => {
      if (activeTool === 'cursor') return;

      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      if (!isDrawing) {
          setIsDrawing(true);
          setCurrentDrawing({
              type: activeTool,
              startX: x,
              startY: y,
              endX: x,
              endY: y,
              id: Date.now().toString(),
              color: '#3b82f6'
          });
      } else {
          if (currentDrawing) {
              setDrawings([...drawings, {
                  ...currentDrawing,
                  endX: x,
                  endY: y
              } as DrawingInfo]);
          }
          setIsDrawing(false);
          setCurrentDrawing(null);
      }
  };

  const redrawCanvas = (currX?: number, currY?: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const allDrawings = [...drawings];
      if (currentDrawing && isDrawing) {
          allDrawings.push(currentDrawing as DrawingInfo);
      }

      allDrawings.forEach(d => {
          ctx.beginPath();
          ctx.strokeStyle = d.color || '#3b82f6';
          ctx.lineWidth = 2;

          if (d.type === 'trendline' && d.startX !== undefined && d.startY !== undefined) {
              ctx.moveTo(d.startX, d.startY);
              ctx.lineTo(d.endX || (currX || 0), d.endY || (currY || 0));
              ctx.stroke();
          } else if (d.type === 'horizontal' && d.startY !== undefined) {
              ctx.moveTo(0, d.startY);
              ctx.lineTo(canvas.width, d.startY);
              ctx.stroke();
          } else if (d.type === 'rectangle' && d.startX !== undefined && d.startY !== undefined) {
              const width = (d.endX || (currX || 0)) - d.startX;
              const height = (d.endY || (currY || 0)) - d.startY;
              ctx.fillStyle = 'rgba(59, 130, 246, 0.2)';
              ctx.fillRect(d.startX, d.startY, width, height);
              ctx.strokeRect(d.startX, d.startY, width, height);
          } else if (d.type === 'fibonacci' && d.startX !== undefined && d.startY !== undefined) {
              ctx.moveTo(d.startX, d.startY);
              ctx.lineTo(d.endX || (currX || 0), d.endY || (currY || 0));
              ctx.stroke();

              // Draw fib levels
              const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
              const dy = (d.endY || (currY || 0)) - d.startY;

              levels.forEach(level => {
                  const y = d.startY! + dy * level;
                  ctx.beginPath();
                  ctx.strokeStyle = `rgba(59, 130, 246, ${1 - level/2})`;
                  ctx.moveTo(d.startX!, y);
                  ctx.lineTo(d.endX || (currX || 0), y);
                  ctx.stroke();
                  ctx.fillStyle = '#94a3b8';
                  ctx.font = '10px Arial';
                  ctx.fillText(`${level * 100}%`, (d.endX || (currX || 0)) + 5, y + 3);
              });
          }
      });
  };

  useEffect(() => {
      redrawCanvas();
      // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawings, currentDrawing]);

  return (
    <div className="flex flex-col w-full bg-[#131722] rounded-lg overflow-hidden border border-zinc-800">

      {/* Top Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#1e222d] border-b border-[#2B2B43] select-none">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 font-mono font-bold text-zinc-100">
             <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-rose-500'}`} />
             {symbol}
          </div>

          <div className="flex items-center gap-1 bg-[#131722] p-1 rounded-md">
            {['1m', '3m', '5m', '15m', '1h', '1D'].map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${
                  timeframe === tf
                    ? 'bg-slate-700 text-emerald-400 border-b-2 border-emerald-500'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
            <button
                onClick={() => setShowSmartTrend(!showSmartTrend)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border ${
                    showSmartTrend ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' : 'bg-[#131722] text-zinc-400 border-transparent hover:border-zinc-700'
                }`}
            >
                <Activity size={14} /> SmartTrend SL
            </button>
            <button
                onClick={() => setShowHFTFlow(!showHFTFlow)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border ${
                    showHFTFlow ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : 'bg-[#131722] text-zinc-400 border-transparent hover:border-zinc-700'
                }`}
            >
                <BarChart2 size={14} /> HFT Flow
            </button>
            <button
                onClick={() => setShowOIPane(!showOIPane)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border ${
                    showOIPane ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' : 'bg-[#131722] text-zinc-400 border-transparent hover:border-zinc-700'
                }`}
            >
                <Settings2 size={14} /> OI Pane
            </button>
        </div>
      </div>

      <div className="flex flex-1 h-[600px]">
        {/* Left Drawing Sidebar */}
        <div className="w-12 bg-[#1e222d] border-r border-[#2B2B43] flex flex-col items-center py-2 gap-2">
            {[
                { id: 'cursor', icon: MousePointer2 },
                { id: 'trendline', icon: Minus },
                { id: 'horizontal', icon: Minus },
                { id: 'rectangle', icon: Square },
                { id: 'fibonacci', icon: Divide },
            ].map(tool => {
                const Icon = tool.icon;
                return (
                    <button
                        key={tool.id}
                        onClick={() => setActiveTool(tool.id as DrawingTool)}
                        className={`p-2 rounded hover:bg-zinc-800 transition-colors ${activeTool === tool.id ? 'text-blue-500 bg-blue-500/10' : 'text-zinc-400'}`}
                        title={tool.id}
                    >
                        <Icon size={18} className={tool.id === 'horizontal' ? 'rotate-180 font-bold' : ''} />
                    </button>
                )
            })}

            <div className="w-8 h-px bg-zinc-800 my-2" />

            <button
                onClick={() => setDrawings([])}
                className="p-2 rounded text-zinc-400 hover:text-rose-500 hover:bg-rose-500/10 transition-colors"
                title="Clear All Drawings"
            >
                <Trash2 size={18} />
            </button>
        </div>

        {/* Chart Container */}
        <div className="flex-1 relative" onClick={handleChartClick}>
          <div ref={chartContainerRef} className="w-full h-full absolute inset-0" />
          <canvas
              ref={canvasRef}
              className="absolute inset-0 pointer-events-none z-10"
          />
        </div>
      </div>
    </div>
  );
};

export default InteractiveChart;
