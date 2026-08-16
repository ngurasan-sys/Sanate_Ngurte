import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.app.core.active_broker import active_broker
from backend.app.core.event_bus import event_bus
from backend.app.market_data.option_chain_client import OptionChainLookupError
from backend.app.oi.analysis import calculate_oi_change_pct, classify_buildup

logger = logging.getLogger(__name__)

DEFAULT_UNDERLYING_KEY = "NSE_INDEX|Nifty 50"
DEEP_ITM_STRIKE_COUNT = 3  # how many strikes into-the-money count as "deep ITM"
MACRO_OI_DROP_THRESHOLD_PCT = 15.0
STRIKE_WINDOW = 5
POLL_INTERVAL_SECONDS = 3


# =====================================================================
# Pure logic — unit-testable without the engine, event bus, or network.
# =====================================================================

def classify_strike_sentiment(ltp: float, close_price: float, oi: int, prev_oi: int) -> str:
    """Reuses the same real classification the rest of this codebase
    already uses for OI-based buildup/unwinding — LONG_BUILDUP,
    SHORT_BUILDUP, SHORT_COVERING, LONG_UNWINDING, or NEUTRAL.
    """
    return classify_buildup(ltp, close_price, oi, prev_oi)


def find_atm_strike(chain: List[Dict[str, Any]], spot_price: float) -> float:
    """The strike closest to the current spot price."""
    return min(
        (row["strike_price"] for row in chain),
        key=lambda strike: abs(strike - spot_price),
    )


def select_atm_window(
    chain: List[Dict[str, Any]], spot_price: float, window: int = STRIKE_WINDOW
) -> List[Dict[str, Any]]:
    """`window` strikes above and below the ATM strike, inclusive of ATM."""
    if not chain:
        return []

    sorted_chain = sorted(chain, key=lambda row: row["strike_price"])
    atm_strike = find_atm_strike(sorted_chain, spot_price)
    atm_index = next(
        i for i, row in enumerate(sorted_chain) if row["strike_price"] == atm_strike
    )

    start = max(0, atm_index - window)
    end = min(len(sorted_chain), atm_index + window + 1)
    return sorted_chain[start:end]


def build_strike_payload(row: Dict[str, Any], atm_strike: float) -> Dict[str, Any]:
    """Formats one option-chain row into the strike payload shape the
    frontend renders: strike_price, is_atm, call_data/put_data.
    """
    call_md = row["call_options"]["market_data"]
    put_md = row["put_options"]["market_data"]

    return {
        "strike_price": row["strike_price"],
        "is_atm": row["strike_price"] == atm_strike,
        "call_data": {
            "ltp": call_md["ltp"],
            "oi_total": call_md["oi"],
            "sentiment": classify_strike_sentiment(
                call_md["ltp"], call_md["close_price"], call_md["oi"], call_md["prev_oi"],
            ),
        },
        "put_data": {
            "ltp": put_md["ltp"],
            "oi_total": put_md["oi"],
            "sentiment": classify_strike_sentiment(
                put_md["ltp"], put_md["close_price"], put_md["oi"], put_md["prev_oi"],
            ),
        },
    }


def build_macro_clue(
    chain: List[Dict[str, Any]],
    spot_price: float,
    deep_itm_count: int = DEEP_ITM_STRIKE_COUNT,
    drop_threshold_pct: float = MACRO_OI_DROP_THRESHOLD_PCT,
) -> Optional[str]:
    """B. Compares real prev_oi -> oi for the deepest in-the-money call
    strikes (the ones with strike_price well below spot). Returns an
    honest None when there isn't a real signal — never a placeholder
    string just to have something to show.
    """
    calls_below_spot = sorted(
        (row for row in chain if row["strike_price"] < spot_price),
        key=lambda row: row["strike_price"],
        reverse=True,  # closest-to-spot first, so [:n] below = deepest ITM
    )
    if not calls_below_spot:
        return None

    deep_itm_rows = calls_below_spot[-deep_itm_count:] if len(calls_below_spot) >= deep_itm_count else calls_below_spot

    drops = []
    for row in deep_itm_rows:
        call_md = row["call_options"]["market_data"]
        change_pct = calculate_oi_change_pct(call_md["oi"], call_md["prev_oi"])
        if change_pct < 0:
            drops.append(abs(change_pct))

    if not drops:
        return None

    avg_drop = sum(drops) / len(drops)
    if avg_drop > drop_threshold_pct:
        return (
            "Bullish Setup: Heavy ITM Call Short Covering detected yesterday."
        )
    return None


# =====================================================================
# Engine — polls the real Upstox option chain endpoint and publishes
# the formatted state.
# =====================================================================

class ExpiryOITrackerEngine:
    def __init__(
        self,
        underlying_key: str = DEFAULT_UNDERLYING_KEY,
        poll_interval_seconds: int = POLL_INTERVAL_SECONDS,
    ):
        self.underlying_key = underlying_key
        self.poll_interval_seconds = poll_interval_seconds
        self.running = False
        self._task = None
        self._last_error: Optional[str] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Expiry OI Tracker Engine started")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Expiry OI Tracker Engine stopped")

    async def _fetch_chain_with_fallback(self, provider, token: str) -> List[Dict[str, Any]]:
        """`expiry_date=current_week` can legitimately return zero rows
        (verified against the real API — not every underlying has an
        expiry landing in Upstox's notion of "this week" at all times).
        Fall back to the next real upcoming expiry rather than treating
        that as an error.
        """
        try:
            return await provider.fetch_option_chain(self.underlying_key, token, "current_week")
        except OptionChainLookupError:
            return await provider.fetch_option_chain(self.underlying_key, token, "next_week")

    async def _poll_loop(self):
        while self.running:
            try:
                provider = active_broker.get_active_provider()
                auth = active_broker.get_active_auth_module()
                token = auth.load_token() if auth else None
                if not token or provider is None:
                    await event_bus.publish("expiry_tracker", {
                        "sufficient_data": False,
                        "reason": "No saved Upstox token — log in via /api/v1/broker/upstox/login.",
                    })
                    await asyncio.sleep(self.poll_interval_seconds)
                    continue

                chain = await self._fetch_chain_with_fallback(provider, token)
                spot_price = chain[0]["underlying_spot_price"]

                windowed = select_atm_window(chain, spot_price, STRIKE_WINDOW)
                atm_strike = find_atm_strike(chain, spot_price)

                payload = {
                    "sufficient_data": True,
                    "underlying_key": self.underlying_key,
                    "spot_price": spot_price,
                    "atm_strike": atm_strike,
                    "macro_clue": build_macro_clue(chain, spot_price),
                    "strikes": [
                        build_strike_payload(row, atm_strike) for row in windowed
                    ],
                }
                self._last_error = None
                await event_bus.publish("expiry_tracker", payload)

            except asyncio.CancelledError:
                break
            except OptionChainLookupError as exc:
                self._last_error = str(exc)
                logger.warning(f"Expiry OI Tracker: option chain fetch failed: {exc}")
                await event_bus.publish("expiry_tracker", {
                    "sufficient_data": False,
                    "reason": f"Option chain fetch failed: {exc}",
                })
            except Exception as exc:
                logger.error(f"Error in ExpiryOITrackerEngine poll loop: {exc}")

            await asyncio.sleep(self.poll_interval_seconds)


expiry_oi_tracker_engine = ExpiryOITrackerEngine()
