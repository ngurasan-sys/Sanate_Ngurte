import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.core import upstox_auth
from backend.app.core.event_bus import event_bus
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
)

logger = logging.getLogger(__name__)


class OptionAnalyticsEngine:
    """Runs two option-chain-derived strategies off a single poll:

      1. IV Regime — ATM implied volatility vs its intraday baseline
         (crush => favour selling premium, expansion => buying premium),
         plus put/call IV skew.
      2. PCR Extreme Reversal — Put-Call Ratio reaching an extreme and
         then turning back from it, as a contrarian signal.

    Both read the same real Upstox option chain, so they share one fetch
    rather than each polling independently — the endpoint is rate-limited
    and the two strategies need identical data.
    """

    def __init__(self, config: Optional[OptionAnalyticsConfig] = None):
        self.config = config or OptionAnalyticsConfig()
        self.running = False
        self._task = None

        self._iv_history: deque = deque(maxlen=self.config.iv_history_window)
        self._pcr_history: deque = deque(maxlen=self.config.pcr_history_window)
        self.latest: Optional[OptionAnalyticsSnapshot] = None

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

    def analyse(self, chain: List[Dict[str, Any]]) -> OptionAnalyticsSnapshot:
        """Pure-ish: derives both strategies' state from one chain snapshot
        and the engine's rolling history. Separated from the polling loop so
        it can be tested without any network or event bus.
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

        # Append AFTER analysing, so the current sample is compared against
        # the prior baseline rather than against itself.
        if atm_iv is not None:
            self._iv_history.append(atm_iv)
        if pcr is not None:
            self._pcr_history.append(pcr)

        return OptionAnalyticsSnapshot(
            timestamp=datetime.now(),
            underlying_key=self.config.underlying_key,
            spot_price=spot_price,
            atm_strike=atm_strike,
            iv_regime=iv_state,
            pcr_reversal=pcr_state,
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
                snapshot = self.analyse(chain)
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
