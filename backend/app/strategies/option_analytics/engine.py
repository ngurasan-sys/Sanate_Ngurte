import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytz

from backend.app.core import upstox_auth
from backend.app.core.event_bus import event_bus
from backend.app.market_data.historical_candles import (
    HistoricalCandleLookupError,
    closes_from_candles,
    fetch_historical_candles,
)
from backend.app.market_data.option_chain_client import (
    OptionChainLookupError,
    fetch_option_chain,
)
from backend.app.strategies.expiry_engine import find_atm_strike

from .analysis import (
    classify_iv_regime,
    classify_pcr_zone,
    classify_skew_bias,
    compute_iv_skew,
    compute_total_pcr,
    detect_pcr_reversal,
    extract_atm_iv,
    iv_signal_for_regime,
    mean,
)
from .models import (
    IvRegimeState,
    OptionAnalyticsConfig,
    OptionAnalyticsSnapshot,
    PcrReversalState,
    SviState,
    VrpState,
)
from .realized_vol import forecast_annualized_vol_from_closes
from .svi import (
    fit_svi,
    extract_smile,
    is_arbitrage_free,
    svi_atm_iv,
    svi_skew_proxy,
    synthetic_forward,
    time_to_expiry_years,
)
from .vrp import classify_vrp, compute_vrp, vrp_signal, vrp_zscore

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


class OptionAnalyticsEngine:
    """Runs four option-chain-derived signals off a single poll:

      1. IV Regime — ATM implied volatility vs its intraday baseline
         (crush => favour selling premium, expansion => buying premium),
         plus put/call IV skew.
      2. PCR Extreme Reversal — Put-Call Ratio reaching an extreme and
         then turning back from it, as a contrarian signal.
      3. SVI Surface Fit — the smile's implied vol/skew, smoothed and
         arbitrage-checked (see svi.py).
      4. Volatility Risk Premium — SVI's implied ATM vol vs a HAR-RV
         forecast of realized vol off daily closes (see vrp.py); the only
         one of the four that needs a second, once-daily-cached network
         call (_get_daily_closes) rather than just the polled option chain.

    IV Regime and PCR Reversal read the same real Upstox option chain, so
    they share one fetch rather than each polling independently — the
    endpoint is rate-limited and both need identical data. SVI and VRP
    build on top of that same chain (plus, for VRP, the daily-closes fetch).
    """

    def __init__(self, config: Optional[OptionAnalyticsConfig] = None):
        self.config = config or OptionAnalyticsConfig()
        self.running = False
        self._task = None

        self._iv_history: deque = deque(maxlen=self.config.iv_history_window)
        self._pcr_history: deque = deque(maxlen=self.config.pcr_history_window)
        self._vrp_history: deque = deque(maxlen=self.config.vrp_history_window)
        self.latest: Optional[OptionAnalyticsSnapshot] = None

        # Daily closes only change once a day, unlike the option chain
        # (polled every few seconds) — cache per IST calendar day rather
        # than re-fetching a full historical-candle range on every poll.
        self._daily_closes_cache: Optional[tuple] = None  # (resolved_on_day, closes)

    def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Option Analytics Engine started (IV regime + PCR reversal)")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Option Analytics Engine stopped")

    async def _fetch_chain(self, token: str) -> List[Dict[str, Any]]:
        """`current_week` legitimately returns zero rows for some
        underlyings/times (verified against the live API), so fall back to
        the next real expiry rather than treating that as an error.
        """
        try:
            return await fetch_option_chain(self.config.underlying_key, token, "current_week")
        except OptionChainLookupError:
            return await fetch_option_chain(self.config.underlying_key, token, "next_week")

    async def _get_daily_closes(self, token: str) -> Optional[List[float]]:
        """Cached per IST calendar day. Returns None (not a raised error)
        when the fetch fails — a missing VRP forecast should degrade that
        one signal, not crash the whole poll loop, same treatment as a
        thin option chain failing the SVI fit.
        """
        today = datetime.now(IST).date()
        if self._daily_closes_cache and self._daily_closes_cache[0] == today:
            return self._daily_closes_cache[1]

        to_date = today
        from_date = today - timedelta(days=self.config.historical_lookback_days)
        try:
            candles = await fetch_historical_candles(
                self.config.underlying_key, token, to_date, from_date
            )
        except HistoricalCandleLookupError as exc:
            logger.warning(f"Option Analytics: historical candle fetch failed: {exc}")
            return None

        closes = closes_from_candles(candles)
        self._daily_closes_cache = (today, closes)
        return closes

    def analyse(
        self,
        chain: List[Dict[str, Any]],
        daily_closes: Optional[List[float]] = None,
    ) -> OptionAnalyticsSnapshot:
        """Pure-ish: derives all four strategies' state from one chain
        snapshot, an optional daily-closes series for the VRP forecast, and
        the engine's rolling history. Separated from the polling loop so it
        can be tested without any network or event bus — `daily_closes` is
        the one input that legitimately comes from a second (once-daily,
        cached) network call, passed in rather than fetched here.
        """
        spot_price = chain[0].get("underlying_spot_price")
        atm_strike = find_atm_strike(chain, spot_price)

        # --- IV regime ---
        atm_iv = extract_atm_iv(chain, atm_strike)
        baseline_iv = mean(list(self._iv_history)) if self._iv_history else None
        regime, change_pct = classify_iv_regime(
            atm_iv, baseline_iv,
            self.config.iv_crush_drop_pct, self.config.iv_expansion_rise_pct,
        )
        skew = compute_iv_skew(chain, atm_strike, self.config.skew_strike_offset)
        skew_bias = classify_skew_bias(skew, self.config.iv_skew_threshold)
        iv_signal = iv_signal_for_regime(regime)

        if atm_iv is None:
            iv_state = IvRegimeState(
                sufficient_data=False,
                reason="No valid ATM implied volatility in the chain yet.",
            )
        elif baseline_iv is None:
            iv_state = IvRegimeState(
                sufficient_data=False,
                reason="Building intraday IV baseline — need more samples.",
                atm_iv=atm_iv, skew=skew, skew_bias=skew_bias,
            )
        else:
            iv_state = IvRegimeState(
                sufficient_data=True,
                atm_iv=atm_iv,
                baseline_iv=baseline_iv,
                iv_change_pct=change_pct,
                regime=regime,
                skew=skew,
                skew_bias=skew_bias,
                signal=iv_signal,
                reasoning=(
                    f"ATM IV {atm_iv:.2f} vs intraday baseline {baseline_iv:.2f} "
                    f"({change_pct:+.1f}%)."
                ),
            )

        # --- PCR reversal ---
        pcr = compute_total_pcr(chain)
        zone = classify_pcr_zone(
            pcr, self.config.pcr_high_extreme, self.config.pcr_low_extreme
        )
        pcr_signal, peak, trough, pcr_reasoning = detect_pcr_reversal(
            pcr, list(self._pcr_history),
            self.config.pcr_high_extreme, self.config.pcr_low_extreme,
            self.config.pcr_reversal_delta,
        )

        if pcr is None:
            pcr_state = PcrReversalState(
                sufficient_data=False,
                reason="Chain had no call OI to compute a PCR from.",
            )
        elif not self._pcr_history:
            pcr_state = PcrReversalState(
                sufficient_data=False,
                reason="Building intraday PCR history — need more samples.",
                pcr=pcr, zone=zone,
            )
        else:
            pcr_state = PcrReversalState(
                sufficient_data=True,
                pcr=pcr,
                pcr_peak=peak,
                pcr_trough=trough,
                zone=zone,
                signal=pcr_signal,
                reasoning=pcr_reasoning,
            )

        # --- SVI surface fit ---
        svi_state = self._fit_svi_state(chain, spot_price)

        # --- Volatility risk premium (needs SVI's implied vol) ---
        vrp_state = self._compute_vrp_state(svi_state, daily_closes)

        # Append AFTER analysing, so the current sample is compared against
        # the prior baseline rather than against itself.
        if atm_iv is not None:
            self._iv_history.append(atm_iv)
        if pcr is not None:
            self._pcr_history.append(pcr)
        if vrp_state.vrp is not None:
            self._vrp_history.append(vrp_state.vrp)

        return OptionAnalyticsSnapshot(
            timestamp=datetime.now(),
            underlying_key=self.config.underlying_key,
            spot_price=spot_price,
            atm_strike=atm_strike,
            iv_regime=iv_state,
            pcr_reversal=pcr_state,
            svi=svi_state,
            vrp=vrp_state,
        )

    def _compute_vrp_state(
        self, svi_state: SviState, daily_closes: Optional[List[float]]
    ) -> VrpState:
        """Combines the SVI fit's implied vol with a HAR-RV forecast off
        daily closes. Degrades independently of both inputs: no SVI fit,
        no closes yet, or too short a close history are each reported by
        name rather than silently producing a zero VRP.
        """
        if not svi_state.sufficient_data or svi_state.atm_iv is None:
            return VrpState(sufficient_data=False, reason="No SVI ATM IV available yet.")

        if not daily_closes:
            return VrpState(
                sufficient_data=False,
                reason="No historical daily closes available for the realized-vol forecast.",
            )

        forecast_vol = forecast_annualized_vol_from_closes(daily_closes)
        if forecast_vol is None:
            return VrpState(
                sufficient_data=False,
                reason=(
                    f"Not enough daily closes ({len(daily_closes)}) for a HAR-RV "
                    "forecast — needs 22-day window plus a few regression rows."
                ),
            )

        vrp = compute_vrp(svi_state.atm_iv, forecast_vol)
        z = vrp_zscore(vrp, list(self._vrp_history))
        classification = classify_vrp(z, self.config.vrp_rich_threshold, self.config.vrp_cheap_threshold)

        return VrpState(
            sufficient_data=True,
            implied_vol=svi_state.atm_iv,
            forecast_vol=forecast_vol,
            vrp=vrp,
            z_score=z,
            classification=classification,
            signal=vrp_signal(classification),
        )

    def _fit_svi_state(
        self, chain: List[Dict[str, Any]], spot_price: Optional[float]
    ) -> SviState:
        """Fits the raw SVI smile for the chain's expiry and reduces it to
        ATM vol / skew / no-arbitrage flag. Kept separate from analyse() so
        a bad or thin chain degrades this one signal, not the whole
        snapshot — IV regime and PCR reversal are unaffected by a fit
        failure here.
        """
        if spot_price is None:
            return SviState(sufficient_data=False, reason="No spot price in chain yet.")

        try:
            tau = time_to_expiry_years(chain)
            forward = synthetic_forward(chain, spot_price)
            x, w = extract_smile(chain, forward, tau)
            params = fit_svi(x, w)
        except ValueError as exc:
            return SviState(sufficient_data=False, reason=str(exc))
        except (KeyError, IndexError) as exc:
            return SviState(
                sufficient_data=False,
                reason=f"Chain missing expected field for SVI fit: {exc}",
            )

        return SviState(
            sufficient_data=True,
            expiry=chain[0].get("expiry"),
            tau_years=tau,
            forward=forward,
            atm_iv=svi_atm_iv(params, tau),
            skew=svi_skew_proxy(params, tau),
            arbitrage_free=is_arbitrage_free(params),
            params={
                "a": params.a, "b": params.b, "rho": params.rho,
                "m": params.m, "sigma": params.sigma,
            },
        )

    async def _poll_loop(self):
        while self.running:
            try:
                token = upstox_auth.load_token()
                if not token:
                    await event_bus.publish("option_analytics", {
                        "sufficient_data": False,
                        "reason": "No saved Upstox token — log in via /api/v1/broker/upstox/login.",
                    })
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue

                chain = await self._fetch_chain(token)
                daily_closes = await self._get_daily_closes(token)
                snapshot = self.analyse(chain, daily_closes)
                self.latest = snapshot
                await event_bus.publish("option_analytics", snapshot.model_dump(mode="json"))

            except asyncio.CancelledError:
                break
            except OptionChainLookupError as exc:
                logger.warning(f"Option Analytics: chain fetch failed: {exc}")
                await event_bus.publish("option_analytics", {
                    "sufficient_data": False,
                    "reason": f"Option chain fetch failed: {exc}",
                })
            except Exception as exc:
                logger.error(f"Error in OptionAnalyticsEngine poll loop: {exc}")

            await asyncio.sleep(self.config.poll_interval_seconds)


option_analytics_engine = OptionAnalyticsEngine()
