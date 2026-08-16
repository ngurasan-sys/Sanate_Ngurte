"""Orchestrates a backtest for whichever strategy strategies_catalog.py
resolves the request to: load data -> pick daily ATM strikes -> build the
strategy's tradable premium series -> generate entry/forced-exit signals
-> run through vectorbt (which handles the actual SL/TP triggering) ->
reduce to a BacktestResult.

Runs synchronously and can take real wall-clock time for a multi-month
range (the OI-buildup data is 1-minute granularity) — the API layer
(jobs.py) is what makes this non-blocking for callers, not this module.

IMPORTANT — read before trusting any result this produces, for every
strategy in strategies_catalog.py, buying or selling:
Entries and exits execute at the option's `close` price for that bar, not
a real bid/ask, because the OI-buildup export only has OHLC of the
option, no depth. Entering "at close" and exiting "at close" is
optimistic by construction — a real fill crosses the spread both ways,
whichever side you're on. Verified against the actual NIFTY data with
SHORT_STRADDLE: a 6-month backtest showed ~461% return, Sharpe ~29, 93%
win rate over 120 trades — numbers that don't survive contact with real
execution costs, and the fact that they hold up over 120 trades (not
just a lucky handful) points at this close-price assumption, not a
genuinely-that-good edge. The same assumption applies to the buying
strategies (LONG_STRADDLE, LONG_CE_MOMENTUM, LONG_PE_MOMENTUM) — a real
buy fills at the ask, not the last close, so their results are
optimistic in the same direction. Do not treat this engine's output as
investable performance without either real bid/ask data or a
deliberately conservative slippage haircut layered on top, and FEES
below is a placeholder (10bps), not calibrated to real NSE STT/stamp
duty/brokerage.
"""

from datetime import date, datetime
from typing import List

import numpy as np
import pandas as pd
import vectorbt as vbt

from backend.app.market_data.lot_sizes import get_lot_size

from .data_loader import load_daily_spot, load_oi_data
from .models import BacktestRequest, BacktestResult, EquityPoint, Trade
from .strategies_catalog import prepare_strategy

INIT_CASH = 100_000.0
FEES = 0.001  # 10 bps per side — a placeholder, not calibrated to real NSE F&O costs


def _classify_exit_reason(entry_price: float, exit_price: float, sl_pct: float, tp_pct: float, direction: str) -> str:
    """vectorbt's trade records don't label *why* a position closed (SL
    vs TP vs the forced time-exit signal) — approximated here by checking
    how close the realized exit price is to the SL/TP thresholds computed
    from the entry price. A trade that closes near neither threshold is
    the forced daily time-exit.

    SL/TP are on opposite sides of the entry price depending on
    direction: a short position loses when the premium rises and wins
    when it falls; a long position is the mirror image.
    """
    if direction == "shortonly":
        sl_price = entry_price * (1 + sl_pct / 100)
        tp_price = entry_price * (1 - tp_pct / 100)
        if exit_price >= sl_price * 0.98:
            return "STOP_LOSS"
        if exit_price <= tp_price * 1.02:
            return "TARGET"
        return "TIME_EXIT"

    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)
    if exit_price <= sl_price * 1.02:
        return "STOP_LOSS"
    if exit_price >= tp_price * 0.98:
        return "TARGET"
    return "TIME_EXIT"


def run_backtest(request: BacktestRequest) -> BacktestResult:
    oi_df = load_oi_data(request.underlying, request.date_from, request.date_to)
    spot_df = load_daily_spot(request.underlying, request.date_from, request.date_to)

    price_df, entries, exits, meta = prepare_strategy(
        request.strategy, oi_df, spot_df, request.entry_minutes_after_open, request.exit_minutes_before_close,
    )
    if price_df.empty:
        raise ValueError(
            f"No tradable {meta.label} days found for {request.underlying} between "
            f"{request.date_from} and {request.date_to} — check the date range overlaps "
            f"both the OI export and the daily spot export."
        )

    price = pd.Series(price_df[meta.price_column].values, index=pd.DatetimeIndex(price_df["timestamp"]))
    entries.index = price.index
    exits.index = price.index

    # Real contract quantity, not vectorbt's default (which sizes each
    # entry off 100% of available cash — meaningless for an options
    # position and produces wildly inflated PnL/Sharpe if left unset,
    # confirmed against the real NIFTY data during development).
    quantity = request.lots * get_lot_size(request.underlying)

    pf = vbt.Portfolio.from_signals(
        price, entries, exits,
        direction=meta.direction,
        size=quantity,
        size_type="amount",
        sl_stop=request.stop_loss_pct / 100.0,
        tp_stop=request.target_pct / 100.0,
        init_cash=INIT_CASH,
        fees=FEES,
        freq="1min",
    )

    trades_df = pf.trades.records_readable
    trades: List[Trade] = []
    for _, row in trades_df.iterrows():
        entry_price = float(row["Avg Entry Price"])
        exit_price = float(row["Avg Exit Price"])
        trades.append(Trade(
            entry_time=row["Entry Timestamp"],
            exit_time=row["Exit Timestamp"],
            strike=0.0,  # populated below via timestamp lookup
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=float(row["PnL"]),
            exit_reason=_classify_exit_reason(entry_price, exit_price, request.stop_loss_pct, request.target_pct, meta.direction),
        ))

    # Attach the actual strike traded that day (price_df has it; trade
    # records don't) by matching each trade's entry day.
    strike_by_day = price_df.drop_duplicates("day").set_index("day")["strike"].to_dict()
    for trade in trades:
        trade.strike = float(strike_by_day.get(trade.entry_time.date(), 0.0))

    equity = pf.value()
    equity_curve = [EquityPoint(timestamp=ts, equity=float(v)) for ts, v in equity.items()]

    sharpe = pf.sharpe_ratio()
    max_dd = pf.max_drawdown()
    win_rate = pf.trades.win_rate() if len(trades) > 0 else None

    return BacktestResult(
        underlying=request.underlying,
        date_from=request.date_from,
        date_to=request.date_to,
        initial_cash=INIT_CASH,
        final_equity=float(equity.iloc[-1]) if len(equity) else INIT_CASH,
        total_return_pct=float(pf.total_return()) * 100.0,
        sharpe_ratio=float(sharpe) if sharpe is not None and not np.isnan(sharpe) else None,
        max_drawdown_pct=float(max_dd) * 100.0 if max_dd is not None and not np.isnan(max_dd) else None,
        win_rate_pct=float(win_rate) * 100.0 if win_rate is not None and not np.isnan(win_rate) else None,
        total_trades=len(trades),
        trades=trades,
        equity_curve=equity_curve,
    )
