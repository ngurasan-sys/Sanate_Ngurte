from datetime import datetime, time

def evaluate_two_candle_setup(symbol: str, current_time_str: str, candle_data: list, oi_data: dict) -> dict:
    """
    candle_data should contain the last 3 closed candles (index 0, 1, 2)
    and the current forming candle (index 3). We evaluate on candles 1 and 2.
    """
    current_time = datetime.strptime(current_time_str, "%H:%M").time()

    # 1. Time Filter (9:45 AM to 2:30 PM)
    if not (time(9, 45) <= current_time <= time(14, 30)):
        return {"status": "PAUSED", "signal": "NONE", "reason": "Outside 9:45 - 14:30 Window"}

    # Set Volume Threshold based on index
    vol_threshold = 125000 if symbol == "NIFTY" else 50000

    c1 = candle_data[-2] # The older of the two trigger candles
    c2 = candle_data[-1] # The most recently closed candle

    # 2. Check Volume Requirement (Both must be above threshold)
    if c1['volume'] < vol_threshold or c2['volume'] < vol_threshold:
        return {"status": "MONITORING", "signal": "NONE", "reason": "Volume threshold not met"}

    # 3. Check Long Conditions
    is_long_price = (c2['close'] > c2['vwap'] and
                     c2['close'] > c2['supertrend'] and
                     c2['close'] > c2['vwma'])

    is_long_volume = c1['close'] > c1['open'] and c2['close'] > c2['open'] # Both Green
    is_long_rsi = c2['rsi'] < 80
    is_long_oi = oi_data.get('trend') == "LONG_BUILDUP"

    if is_long_price and is_long_volume and is_long_rsi and is_long_oi:
        return {
            "status": "SIGNAL_ACTIVE",
            "signal": "BUY_CALL",
            "entry_trigger": "OPEN_OF_CURRENT_CANDLE",
            "stop_loss": c1['low'],
            "reason": "2-Candle Bullish Breakout Confirmed"
        }

    # 4. Check Short Conditions
    is_short_price = (c2['close'] < c2['vwap'] and
                      c2['close'] < c2['supertrend'] and
                      c2['close'] < c2['vwma'])

    is_short_volume = c1['close'] < c1['open'] and c2['close'] < c2['open'] # Both Red
    is_short_rsi = c2['rsi'] > 20
    is_short_oi = oi_data.get('trend') == "SHORT_BUILDUP"

    if is_short_price and is_short_volume and is_short_rsi and is_short_oi:
        return {
            "status": "SIGNAL_ACTIVE",
            "signal": "BUY_PUT",
            "entry_trigger": "OPEN_OF_CURRENT_CANDLE",
            "stop_loss": c1['high'],
            "reason": "2-Candle Bearish Breakout Confirmed"
        }

    return {"status": "MONITORING", "signal": "NONE", "reason": "Price/Indicator alignment missing"}
